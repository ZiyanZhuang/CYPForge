#!/usr/bin/env python3
"""Convert mmCIF (PDBx) to fixed-column PDB format.

Handles both standard PDB mmCIF and Protenix/AF3 predicted CIF formats.
Column order is determined from the _atom_site loop header, not hardcoded.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

PDB_FMT = (
    "{record:6s}{serial:5d} {atname:<4s}{altloc:1s}{resname:3s} {chain:1s}"
    "{resid:4d}{inscode:1s}   {x:8.3f}{y:8.3f}{z:8.3f}"
    "{occ:6.2f}{bfactor:6.2f}          {element:>2s}\n"
)


def _parse_cif_loop(lines: list[str], start_idx: int) -> tuple[list[str], list[list[str]], int]:
    """Parse a CIF loop_ block. Returns (column_names, data_rows, next_index)."""
    col_names: list[str] = []
    data_rows: list[list[str]] = []
    i = start_idx

    # Collect column names (lines starting with _)
    # Strip leading _ and any common prefix like atom_site.
    while i < len(lines) and lines[i].strip().startswith("_"):
        name = lines[i].strip().lstrip("_")
        # Remove common mmCIF category prefix
        if name.startswith("atom_site."):
            name = name[len("atom_site."):]
        col_names.append(name)
        i += 1

    # Collect data rows (lines NOT starting with _ or # or loop_ and non-empty)
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("_") or stripped.startswith("loop_"):
            break
        values = stripped.split()
        if values:
            data_rows.append(values)
        i += 1

    return col_names, data_rows, i


def _resolve_value(cols: list[str], row: list[str], *candidates: str, default: str = "") -> str:
    """Return the first value matching one of the candidate column names."""
    for cand in candidates:
        if cand in cols:
            idx = cols.index(cand)
            if idx < len(row):
                val = row[idx]
                if val in (".", "?"):
                    continue
                return val
    return default


def _resolve_int_value(cols: list[str], row: list[str], *candidates: str) -> int | None:
    """Resolve the first candidate that can be parsed as an integer.

    Non-polymer mmCIF rows often have label_seq_id='.' while auth_seq_id
    stores the PDB residue number. A plain first-nonempty lookup drops HEM.
    """
    for cand in candidates:
        value = _resolve_value(cols, row, cand)
        if not value:
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _truncate_number(value: str, max_digits: int) -> str:
    """Truncate a numeric string to max_digits, keeping sign."""
    if not value:
        return "0"
    value = value.strip()
    if len(value) <= max_digits:
        return value
    # Try as float and format
    try:
        v = float(value)
        if max_digits == 4:
            return f"{int(v):4d}"
        if max_digits == 8:
            return f"{v:8.3f}"
        return value[:max_digits]
    except ValueError:
        return value[:max_digits]


def _format_atom_line(
    serial: int,
    record: str,
    atname: str,
    altloc: str,
    resname: str,
    chain: str,
    resid: int,
    inscode: str,
    x: float,
    y: float,
    z: float,
    occ: float,
    bfactor: float,
    element: str,
) -> str:
    """Write a single PDB ATOM/HETATM line with correct column alignment.

    PDB format rules for atom name (cols 13-16):
    - 1-letter elements (C,N,O,H,S,P): atom name starts at col 14 (col 13 is blank)
    - 2-letter elements (FE,CL,BR,ZN,MG): atom name starts at col 13, left-aligned
    """
    if len(element) == 1 and len(atname) < 4:
        # 1-letter element, 1-3 char name: starts at col 14 (col 13 blank)
        atname_fmt = f" {atname:<3s}"
    elif len(element) == 1 and len(atname) == 4:
        # 1-letter element, 4-char name: must start at col 13 (no room for leading space)
        atname_fmt = f"{atname:<4s}"
    elif len(element) == 2:
        # 2-letter element: starts at col 13
        atname_fmt = f"{atname:<4s}"
    else:
        atname_fmt = f"{atname:<4s}"
    return PDB_FMT.format(
        record=record,
        serial=serial % 100000,
        atname=atname_fmt,
        altloc=altloc if altloc else " ",
        resname=resname,
        chain=chain if chain else " ",
        resid=resid % 10000,
        inscode=inscode if inscode else " ",
        x=x,
        y=y,
        z=z,
        occ=occ,
        bfactor=bfactor,
        element=element,
    )


def convert_cif_to_pdb(cif_path: Path, output_pdb: Path, model_num: int = 1) -> dict[str, Any]:
    """Convert an mmCIF file to PDB fixed-column format.

    Args:
        cif_path: Path to input mmCIF file.
        output_pdb: Path to output PDB file.
        model_num: Model number to extract (1-indexed). For multi-model CIFs
            (Protenix), only atoms with pdbx_PDB_model_num == model_num are
            written. For single-model CIFs, all atoms are written.

    Returns:
        Dict with conversion statistics.
    """
    raw = cif_path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()

    stats: dict[str, Any] = {
        "input_cif": str(cif_path),
        "output_pdb": str(output_pdb),
        "model_num": model_num,
        "total_atom_site_rows": 0,
        "atoms_written": 0,
        "hetatm_atoms": 0,
        "chains_found": set(),
        "residues_found": set(),
    }

    # Find atom_site loop
    atom_site_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("_atom_site."):
            # Backtrack to loop_ keyword
            for j in range(i - 1, max(i - 5, -1), -1):
                if lines[j].strip() == "loop_":
                    atom_site_start = j
                    break
            if atom_site_start is None:
                atom_site_start = i - 1  # assume loop_ is right before first column
            break

    if atom_site_start is None:
        raise ValueError("No _atom_site loop found in CIF file.")

    cols, rows, _ = _parse_cif_loop(lines, atom_site_start + 1)

    if not rows:
        raise ValueError("No atom_site data rows found.")

    # Detect if this CIF has model numbers
    has_models = "pdbx_PDB_model_num" in cols

    output_lines: list[str] = []
    serial = 0

    for row in rows:
        stats["total_atom_site_rows"] += 1

        if has_models:
            row_model = _resolve_value(cols, row, "pdbx_PDB_model_num")
            if row_model and int(row_model) != model_num:
                continue

        group = _resolve_value(cols, row, "group_PDB", "group_PDB")
        record = "ATOM" if group == "ATOM" else "HETATM"

        atname = _resolve_value(cols, row, "auth_atom_id", "label_atom_id")
        altloc = _resolve_value(cols, row, "label_alt_id", "pdbx_label_alt_id")
        resname = _resolve_value(cols, row, "label_comp_id", "auth_comp_id")
        # PDB columns 18-20 allow at most 3 chars; truncate CCD codes like A1L3H -> A1L
        if len(resname) > 3:
            resname = resname[:3]
        chain = _resolve_value(cols, row, "label_asym_id", "auth_asym_id")
        element = _resolve_value(cols, row, "type_symbol")

        resid = _resolve_int_value(cols, row, "label_seq_id", "auth_seq_id")
        inscode = _resolve_value(cols, row, "pdbx_PDB_ins_code")

        x_str = _resolve_value(cols, row, "Cartn_x")
        y_str = _resolve_value(cols, row, "Cartn_y")
        z_str = _resolve_value(cols, row, "Cartn_z")
        occ_str = _resolve_value(cols, row, "occupancy", default="1.0")
        bfac_str = _resolve_value(cols, row, "B_iso_or_equiv", default="0.0")

        if not atname or not resname:
            continue

        try:
            if resid is None:
                continue
            x = float(x_str)
            y = float(y_str)
            z = float(z_str)
            occ = float(occ_str) if occ_str else 1.0
            bfactor = float(bfac_str) if bfac_str else 0.0
        except (ValueError, TypeError):
            continue

        serial += 1
        line = _format_atom_line(serial, record, atname, altloc,
                                  resname, chain, resid, inscode,
                                  x, y, z, occ, bfactor, element)
        output_lines.append(line)

        if record == "HETATM":
            stats["hetatm_atoms"] += 1
        if chain:
            stats["chains_found"].add(chain)
        stats["residues_found"].add((chain, resname, resid))

    output_pdb.parent.mkdir(parents=True, exist_ok=True)
    output_pdb.write_text("".join(output_lines), encoding="utf-8")

    stats["atoms_written"] = serial
    stats["chains_found"] = sorted(stats["chains_found"])
    stats["unique_residues"] = len(stats["residues_found"])

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert mmCIF to fixed-column PDB format for CYPForge."
    )
    parser.add_argument("--input-cif", required=True, help="Input mmCIF file.")
    parser.add_argument("--output-pdb", required=True, help="Output PDB file.")
    parser.add_argument("--model-num", type=int, default=1,
                        help="Model number to extract (default: 1).")
    args = parser.parse_args()

    cif_path = Path(args.input_cif)
    if not cif_path.is_file():
        print(f"ERROR: Input CIF not found: {cif_path}", file=sys.stderr)
        return 1

    try:
        stats = convert_cif_to_pdb(cif_path, Path(args.output_pdb), args.model_num)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Converted {stats['input_cif']} -> {stats['output_pdb']}")
    print(f"  Model: {stats['model_num']}")
    print(f"  Atoms written: {stats['atoms_written']} "
          f"(HETATM: {stats['hetatm_atoms']})")
    print(f"  Chains: {', '.join(stats['chains_found'])}")
    print(f"  Unique residues: {stats['unique_residues']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
