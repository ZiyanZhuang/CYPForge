#!/usr/bin/env python3
"""Convert a closed-shell PySCF Molden wavefunction into Amber RESP ``esp.dat``.

The output uses Amber RESP's fixed-width ESP convention: atom/grid coordinates
in bohr and electrostatic potentials in atomic units.  Supply the QM method as
metadata because Molden files do not reliably retain a reproducible method label.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from pyscf import df, gto
from pyscf.tools import molden


BONDI_RADII_ANGSTROM = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80}
BOHR_PER_ANGSTROM = 1.8897261254578281
SHELL_SCALES = (1.4, 1.6, 1.8, 2.0)


def _fibonacci_sphere(point_count: int) -> np.ndarray:
    """Return approximately uniform directions without an external grid file."""
    indices = np.arange(point_count, dtype=float)
    z = 1.0 - 2.0 * (indices + 0.5) / point_count
    phi = np.pi * (1.0 + 5.0**0.5) * indices
    radial = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    return np.column_stack((radial * np.cos(phi), radial * np.sin(phi), z))


def _build_grid(coords_bohr: np.ndarray, symbols: list[str], points_per_shell: int) -> np.ndarray:
    """Create MK-style shells and reject points within another atom's inner shell."""
    radii = np.array([BONDI_RADII_ANGSTROM.get(symbol, 1.70) * BOHR_PER_ANGSTROM for symbol in symbols])
    directions = _fibonacci_sphere(points_per_shell)
    accepted: list[np.ndarray] = []
    for center, radius in zip(coords_bohr, radii):
        for scale in SHELL_SCALES:
            candidates = center + directions * (scale * radius)
            distances = np.linalg.norm(candidates[:, None, :] - coords_bohr[None, :, :], axis=2)
            accepted.append(candidates[np.all(distances >= (SHELL_SCALES[0] * radii)[None, :], axis=1)])
    grid = np.vstack(accepted)
    if len(grid) < 1000:
        raise RuntimeError(f"ESP grid too small after occlusion filtering: {len(grid)}")
    return grid


def _electrostatic_potential(molecule, density: np.ndarray, grid_bohr: np.ndarray, chunk_size: int) -> np.ndarray:
    """Evaluate nuclear plus electronic ESP in chunks to bound memory consumption."""
    potential = np.empty(len(grid_bohr), dtype=float)
    nuclear = np.zeros(len(grid_bohr), dtype=float)
    for atom_index in range(molecule.natm):
        nuclear += molecule.atom_charge(atom_index) / np.linalg.norm(grid_bohr - molecule.atom_coord(atom_index), axis=1)
    for start in range(0, len(grid_bohr), chunk_size):
        stop = min(start + chunk_size, len(grid_bohr))
        fake_molecule = gto.fakemol_for_charges(grid_bohr[start:stop])
        integrals = df.incore.aux_e2(molecule, fake_molecule)
        potential[start:stop] = nuclear[start:stop] - np.einsum("ijp,ij->p", integrals, density)
    return potential


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("molden", type=Path, help="Converged closed-shell PySCF Molden wavefunction")
    parser.add_argument("--out", type=Path, required=True, help="Output Amber esp.dat path")
    parser.add_argument("--formal-charge", type=int, required=True)
    parser.add_argument("--multiplicity", type=int, required=True, help="Only singlet (1) is supported")
    parser.add_argument("--qm-method", required=True, help="Recorded verbatim in the provenance JSON")
    parser.add_argument("--points-per-shell", type=int, default=80)
    parser.add_argument("--chunk-size", type=int, default=250)
    args = parser.parse_args()
    if args.multiplicity != 1:
        raise ValueError("Only closed-shell singlet Molden wavefunctions are supported")
    if args.points_per_shell < 1 or args.chunk_size < 1:
        raise ValueError("points-per-shell and chunk-size must be positive")

    molecule, _, coefficients, occupations, *_ = molden.load(str(args.molden))
    electron_count = int(round(np.sum(occupations)))
    wavefunction_charge = int(round(sum(molecule.atom_charge(i) for i in range(molecule.natm)) - electron_count))
    if wavefunction_charge != args.formal_charge:
        raise RuntimeError(f"Wavefunction charge {wavefunction_charge} != required {args.formal_charge}")
    if electron_count % 2:
        raise RuntimeError(f"Odd occupied-electron count ({electron_count}); not a closed-shell singlet")

    density = (coefficients * occupations) @ coefficients.T
    coordinates = np.array([molecule.atom_coord(i) for i in range(molecule.natm)])
    symbols = [molecule.atom_symbol(i) for i in range(molecule.natm)]
    grid = _build_grid(coordinates, symbols, args.points_per_shell)
    esp = _electrostatic_potential(molecule, density, grid, args.chunk_size)
    if not np.all(np.isfinite(esp)) or np.max(np.abs(esp)) > 10.0:
        raise RuntimeError("ESP values are non-finite or implausibly large")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="ascii") as handle:
        # Amber resp reads I5 and E16.7 fixed-width fields, not free-format text.
        handle.write(f"{molecule.natm:5d}{len(grid):5d}{args.formal_charge:5d}\n")
        for atom_index in range(molecule.natm):
            x, y, z = coordinates[atom_index]
            handle.write(f"{'':17s}{x:16.7E}{y:16.7E}{z:16.7E}{molecule.atom_charge(atom_index):4d}  {symbols[atom_index]}\n")
        for value, (x, y, z) in zip(esp, grid):
            handle.write(f"{value:16.7E}{x:16.7E}{y:16.7E}{z:16.7E}\n")
    report = {
        "status": "PASS", "source_molden": str(args.molden.resolve()), "qm_method": args.qm_method,
        "formal_charge": args.formal_charge, "multiplicity": args.multiplicity,
        "wavefunction_charge_from_electron_count": wavefunction_charge,
        "occupied_electrons": electron_count, "atom_count": molecule.natm, "grid_count": len(grid),
        "grid_shell_scales_bondi": list(SHELL_SCALES), "points_per_shell": args.points_per_shell,
        "esp_min_au": float(esp.min()), "esp_max_au": float(esp.max()),
    }
    args.out.with_suffix(args.out.suffix + ".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
