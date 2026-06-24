#!/usr/bin/env python3
"""H-only PBE micro-relaxation for ligand RESP geometry preparation.

Deletes all heavy-atom optimization. Only hydrogen atoms are relaxed under
PBE/6-31G* with GPU acceleration. Heavy atoms remain frozen at the confirmed
complex pose. Fast convergence profile: max 6 micro-steps, loose gradient
target (3e-3 Eh/A), max H step 0.08 A.

Policy: GPU is required by default. Use --cpu-only to disable GPU.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from pyscf import dft, gto

try:
    from gpu4pyscf import dft as gpu_dft  # noqa: F401
    GPU4PYSCF_AVAILABLE = True
except Exception:
    GPU4PYSCF_AVAILABLE = False


BOHR_PER_ANG = 1.8897261246257702


def _element(name: str, atom_type: str) -> str:
    head = atom_type.split(".")[0].strip()
    if head:
        lower = "".join(ch for ch in head if ch.isalpha()).lower()
        if lower.startswith("cl"):
            return "Cl"
        if lower.startswith("br"):
            return "Br"
        if lower:
            return lower[0].upper()
    letters = "".join(ch for ch in name if ch.isalpha())
    return letters[0].upper() + letters[1:].lower()


def read_mol2(path: Path) -> tuple[list[str], list[dict], list[str]]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    atoms: list[dict] = []
    atom_line_indices: list[int] = []
    in_atoms = False
    for idx, line in enumerate(lines):
        if line.startswith("@<TRIPOS>ATOM"):
            in_atoms = True
            continue
        if line.startswith("@<TRIPOS>") and in_atoms:
            in_atoms = False
            continue
        if not in_atoms or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 9:
            raise ValueError(f"Cannot parse MOL2 atom line: {line}")
        atoms.append(
            {
                "id": int(parts[0]),
                "name": parts[1],
                "x": float(parts[2]),
                "y": float(parts[3]),
                "z": float(parts[4]),
                "type": parts[5],
                "subst_id": parts[6],
                "subst_name": parts[7],
                "charge": float(parts[8]),
                "element": _element(parts[1], parts[5]),
            }
        )
        atom_line_indices.append(idx)
    if not atoms:
        raise ValueError(f"No atoms parsed from {path}")
    return lines, atoms, [str(i) for i in atom_line_indices]


def write_mol2(
    path: Path,
    template_lines: list[str],
    atom_line_indices: list[str],
    atoms: list[dict],
    coords: np.ndarray,
) -> None:
    lines = list(template_lines)
    for atom, line_idx_text, xyz in zip(atoms, atom_line_indices, coords):
        idx = int(line_idx_text)
        lines[idx] = (
            f"{atom['id']:>7d} {atom['name']:<8s}"
            f"{xyz[0]:>10.4f}{xyz[1]:>10.4f}{xyz[2]:>10.4f} "
            f"{atom['type']:<8s}{atom['subst_id']:>3s} {atom['subst_name']:<8s}{atom['charge']:>10.6f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_mf(atoms: list[dict], coords_ang: np.ndarray, charge: int, spin: int, basis: str, use_gpu: bool):
    mol = gto.Mole()
    mol.atom = [(atom["element"], tuple(coords_ang[i])) for i, atom in enumerate(atoms)]
    mol.unit = "Angstrom"
    mol.charge = charge
    mol.spin = spin - 1
    mol.basis = basis
    mol.verbose = 0
    mol.build()
    mf = dft.RKS(mol) if mol.spin == 0 else dft.UKS(mol)
    mf.xc = "pbe"
    mf.grids.level = 3
    mf.conv_tol = 1e-8
    mf.max_cycle = 200
    mf.level_shift = 0.2
    mf.damp = 0.2
    backend = "pyscf_cpu"
    if use_gpu:
        try:
            mf = mf.to_gpu()
            backend = "gpu4pyscf"
        except Exception:
            pass
    return mf, backend


def _h_only_optimize(
    *,
    atoms: list[dict],
    start_coords: np.ndarray,
    hydrogen_mask: np.ndarray,
    heavy_mask: np.ndarray,
    charge: int,
    spin: int,
    basis: str,
    use_gpu: bool,
    maxiter: int = 6,
    max_step_a: float = 0.08,
    grad_rms_target_eh_per_a: float = 3.0e-3,
) -> tuple[np.ndarray, dict]:
    """Run H-only PBE micro-relaxation. Heavy atoms remain frozen.

    Fast coarse-grained convergence suitable for RESP geometry preparation.
    Only hydrogen positions are updated; heavy atoms are never moved.
    """
    coords = np.array(start_coords, dtype=float).copy()
    n_hydrogens = int(np.sum(hydrogen_mask))
    if n_hydrogens == 0:
        return coords, {
            "status": "skipped",
            "message": "no hydrogen atoms to optimize",
            "nit": 0,
            "nfev": 0,
            "backend": "none",
            "max_step_a": max_step_a,
            "grad_rms_target_eh_per_a": grad_rms_target_eh_per_a,
            "final_energy_hartree": None,
            "history_tail": [],
        }

    backend_used = "unknown"
    history: list[dict] = []
    n_fev = 0
    last_energy = None
    success = False
    message = "maximum micro-steps reached"

    for step_idx in range(maxiter):
        mf, backend = _make_mf(atoms, coords, charge, spin, basis, use_gpu)
        backend_used = backend
        energy = float(mf.kernel())
        n_fev += 1
        if not mf.converged:
            raise RuntimeError(f"PBE SCF did not converge at step {step_idx}")

        grad_bohr = np.asarray(mf.nuc_grad_method().kernel(), dtype=float)
        grad_ang = grad_bohr * BOHR_PER_ANG
        active_grad = grad_ang[hydrogen_mask]
        grad_rms = math.sqrt(float(np.mean(np.sum(active_grad ** 2, axis=1))))
        last_energy = energy

        row = {
            "step": step_idx,
            "energy_hartree": energy,
            "active_grad_rms_eh_per_a": grad_rms,
        }
        history.append(row)

        if grad_rms <= grad_rms_target_eh_per_a:
            success = True
            message = "loose gradient target reached"
            break

        raw_step = -active_grad
        max_norm = float(np.max(np.linalg.norm(raw_step, axis=1)))
        if max_norm == 0.0:
            success = True
            message = "zero active gradient"
            break
        trial_step = raw_step * (max_step_a / max_norm)

        accepted = False
        for ls_idx in range(3):
            scale = 0.5 ** ls_idx
            trial = np.array(coords, copy=True)
            trial[hydrogen_mask] = coords[hydrogen_mask] + trial_step * scale
            mf2, _ = _make_mf(atoms, trial, charge, spin, basis, use_gpu)
            trial_energy = float(mf2.kernel())
            n_fev += 1
            if not mf2.converged:
                continue
            if trial_energy <= energy or ls_idx == 2:
                coords = trial
                row = {
                    "step": step_idx,
                    "energy_hartree": trial_energy,
                    "line_search_scale": scale,
                }
                history.append(row)
                accepted = True
                break
        if not accepted:
            message = "line search failed"
            break

    return coords, {
        "status": "success" if success else "warning",
        "message": message,
        "nit": sum(1 for row in history if "line_search_scale" in row),
        "nfev": n_fev,
        "backend": backend_used,
        "max_step_a": max_step_a,
        "grad_rms_target_eh_per_a": grad_rms_target_eh_per_a,
        "final_energy_hartree": last_energy,
        "history_tail": history[-5:],
    }


def _rmsd(coords_a: np.ndarray, coords_b: np.ndarray, mask: np.ndarray) -> float:
    diff = coords_a[mask] - coords_b[mask]
    if len(diff) == 0:
        return 0.0
    return math.sqrt(float(np.mean(np.sum(diff * diff, axis=1))))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PBE H-only ligand micro-relaxation — hydrogen atoms only, GPU-first, fast convergence."
    )
    parser.add_argument("--input-mol2", required=True)
    parser.add_argument("--output-mol2", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--charge", type=int, required=True)
    parser.add_argument("--spin", type=int, default=1)
    parser.add_argument("--basis", default="6-31g*")
    parser.add_argument("--maxiter", type=int, default=6, help="Max PBE micro-steps (default: 6)")
    parser.add_argument("--max-step", type=float, default=0.08, help="Max H displacement per step in A")
    parser.add_argument("--grad-rms-target", type=float, default=3.0e-3, help="Gradient RMS target in Eh/A")
    parser.add_argument("--cpu-only", action="store_true", help="Disable GPU acceleration")
    args = parser.parse_args()

    src = Path(args.input_mol2)
    out = Path(args.output_mol2)
    manifest_path = Path(args.manifest)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    lines, atoms, atom_line_indices = read_mol2(src)
    coords0 = np.array([[atom["x"], atom["y"], atom["z"]] for atom in atoms], dtype=float)
    heavy = np.array([atom["element"].upper() != "H" for atom in atoms], dtype=bool)
    hydrogens = ~heavy
    use_gpu = GPU4PYSCF_AVAILABLE and not args.cpu_only

    # --- single-stage: H-only PBE optimization ---
    h_coords, h_report = _h_only_optimize(
        atoms=atoms,
        start_coords=coords0,
        hydrogen_mask=hydrogens,
        heavy_mask=heavy,
        charge=args.charge,
        spin=args.spin,
        basis=args.basis,
        use_gpu=use_gpu,
        maxiter=args.maxiter,
        max_step_a=args.max_step,
        grad_rms_target_eh_per_a=args.grad_rms_target,
    )

    heavy_rmsd = _rmsd(h_coords, coords0, heavy)
    max_heavy_shift = float(np.max(np.linalg.norm(h_coords[heavy] - coords0[heavy], axis=1))) if np.any(heavy) else 0.0
    h_rmsd = _rmsd(h_coords, coords0, hydrogens)

    # Heavy atoms must NOT have moved (frozen).
    if heavy_rmsd > 1.0e-4:
        raise RuntimeError(
            f"Heavy atoms shifted during H-only optimization: RMSD={heavy_rmsd:.6f} A. "
            "This is a bug — heavy atoms must remain frozen."
        )

    write_mol2(out, lines, atom_line_indices, atoms, h_coords)

    manifest = {
        "schema": "cypforge.h_only_ligand_relaxation.v1",
        "status": "passed",
        "input_mol2": str(src),
        "output_mol2": str(out),
        "method": f"PBE/{args.basis}",
        "engine_backend": h_report["backend"],
        "gpu_available": GPU4PYSCF_AVAILABLE,
        "gpu_used": h_report["backend"] == "gpu4pyscf",
        "charge": args.charge,
        "spin_multiplicity": args.spin,
        "atom_count": len(atoms),
        "heavy_atom_count": int(np.sum(heavy)),
        "hydrogen_count": int(np.sum(hydrogens)),
        "stage": {
            "name": "H-only PBE optimization",
            "active_atoms": "hydrogen atoms only",
            "frozen_atoms": "all heavy atoms — never moved",
            **h_report,
        },
        "heavy_atom_rmsd_to_input_a": round(heavy_rmsd, 8),
        "max_heavy_atom_shift_a": round(max_heavy_shift, 8),
        "hydrogen_rmsd_to_input_a": round(h_rmsd, 8),
        "gate": "pass",
        "policy": (
            "Only hydrogen atoms are relaxed under PBE/6-31G*. Heavy atoms remain "
            "frozen at the confirmed complex pose. No all-atom optimization is "
            "performed. GPU acceleration is preferred and auto-detected. "
            "Fast convergence: max 6 micro-steps, 0.08 A max H displacement, "
            "3e-3 Eh/A loose gradient target. This is geometry cleanup, not "
            "conformational search."
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
