from __future__ import annotations

import atexit
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from .io import parse_frcmod_sections, sha256_file, write_json

VALID_STATES = ("IC6", "DIOXY", "CPDI")

_HEME_ROOT_CACHE: Path | None = None
_HEME_RESOURCE_STACK: ExitStack | None = None


def _default_heme_root() -> Path:
    """Locate the bundled heme parameter directory.

    Two lookup paths in order:

    1. Source / editable install fast path — the sibling ``cypforge`` package
       layout (``src/cypforge/data/heme_params``) is a real on-disk directory
       in this repo, so checking the obvious parent path lets dev work proceed
       without importlib overhead.
    2. Installed-wheel fallback via :func:`importlib.resources.files`. For
       zipped distributions ``as_file`` extracts to a tempdir; we hold the
       context open in a module-level :class:`ExitStack` registered with
       ``atexit`` so the path stays valid for the entire process lifetime,
       not just for the duration of a single ``with`` block. The first
       successful lookup is cached so subsequent calls return immediately.
    """
    global _HEME_ROOT_CACHE, _HEME_RESOURCE_STACK
    if _HEME_ROOT_CACHE is not None:
        return _HEME_ROOT_CACHE

    here = Path(__file__).resolve()
    fast = here.parents[1] / "cypforge" / "data" / "heme_params"
    if fast.exists():
        _HEME_ROOT_CACHE = fast
        return fast

    from importlib.resources import as_file, files

    res = files("cypforge").joinpath("data", "heme_params")
    if _HEME_RESOURCE_STACK is None:
        _HEME_RESOURCE_STACK = ExitStack()
        atexit.register(_HEME_RESOURCE_STACK.close)
    extracted = _HEME_RESOURCE_STACK.enter_context(as_file(res))
    if not extracted.exists():
        raise FileNotFoundError("Could not locate bundled cypforge/data/heme_params")
    _HEME_ROOT_CACHE = Path(extracted)
    return _HEME_ROOT_CACHE


def read_mol2_atoms(path: Path) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    in_atoms = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped == "@<TRIPOS>ATOM":
            in_atoms = True
            continue
        if in_atoms and stripped.startswith("@<TRIPOS>"):
            break
        if not in_atoms or not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 9:
            raise ValueError(f"Invalid MOL2 atom line in {path}: {stripped}")
        charge = None
        for token in reversed(parts):
            try:
                charge = float(token)
                break
            except ValueError:
                continue
        if charge is None:
            raise ValueError(f"Missing charge in MOL2 atom line in {path}: {stripped}")
        atoms.append(
            {
                "index": int(parts[0]),
                "name": parts[1],
                "type": parts[5],
                "resname": parts[7] if len(parts) > 7 else "",
                "charge": charge,
            }
        )
    if not atoms:
        raise ValueError(f"No atoms parsed from MOL2: {path}")
    return atoms


def mol2_charge(path: Path) -> float:
    return round(sum(atom["charge"] for atom in read_mol2_atoms(path)), 6)


def extract_fe_s_bond(path: Path) -> dict[str, Any]:
    sections = parse_frcmod_sections(path)
    for line in sections.get("BOND", []):
        parts = line.split()
        if parts and parts[0].lower() == "fe-sh" and len(parts) >= 3:
            return {"raw": line, "k": float(parts[1]), "r0": float(parts[2])}
    raise ValueError(f"No fe-SH bond parameter found in {path}")


def prepare_heme(state: str, *, heme_params_root: str | Path | None = None, out_json: str | Path | None = None) -> dict[str, Any]:
    state = state.upper()
    if state not in VALID_STATES:
        raise ValueError(f"Unknown heme state {state}; expected one of {VALID_STATES}")
    root = Path(heme_params_root) if heme_params_root else _default_heme_root()
    state_dir = root / state
    heme_mol2 = state_dir / "HEM.mol2"
    cyp_mol2 = state_dir / "CYP.mol2"
    frcmod = state_dir / f"{state}.frcmod"
    missing = [str(path) for path in (heme_mol2, cyp_mol2, frcmod) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing heme parameter files: {missing}")

    heme_atoms = read_mol2_atoms(heme_mol2)
    cyp_atoms = read_mol2_atoms(cyp_mol2)
    fe_atoms = [atom for atom in heme_atoms if atom["name"] == "FE"]
    if len(fe_atoms) != 1:
        raise ValueError(f"{state} HEM.mol2 must contain exactly one FE atom")
    manifest = {
        "schema": "cypforge_core.heme_manifest.v1",
        "state": state,
        "heme_mol2": str(heme_mol2),
        "cyp_mol2": str(cyp_mol2),
        "frcmod": str(frcmod),
        "heme_charge": mol2_charge(heme_mol2),
        "cyp_patch_charge": mol2_charge(cyp_mol2),
        "fe_atom_type": fe_atoms[0]["type"],
        "fe_charge": round(float(fe_atoms[0]["charge"]), 6),
        "o1_count": sum(1 for atom in heme_atoms if atom["name"] == "O1"),
        "o2_count": sum(1 for atom in heme_atoms if atom["name"] == "O2"),
        "fe_s_bond": extract_fe_s_bond(frcmod),
        "sha256": {
            "heme_mol2": sha256_file(heme_mol2),
            "cyp_mol2": sha256_file(cyp_mol2),
            "frcmod": sha256_file(frcmod),
        },
        "limitation": "Source attribution and file consistency only; this does not validate chemical correctness.",
    }
    if out_json:
        write_json(Path(out_json), manifest)
    return manifest
