#!/usr/bin/env python3
"""Run Amber's native two-stage RESP fit and inject charges by explicit atom map.

Use this after an external QM program has created an Amber-compatible ``esp.dat``
file and after the user has reviewed the two RESP control files. The script does
not generate equivalence/restraint directives: they are chemical decisions and
must be encoded in the supplied stage-1 and stage-2 inputs.

The map TSV is required so RESP order is never assumed to be the MOL2 row order.
It must contain ``resp_index`` (1-based RESP order) and ``mol2_atom_id`` (Tripos
atom ID). Optional ``atom_name`` and ``element`` columns are checked against MOL2.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
from pathlib import Path


def _read_charge_file(path: Path, expected_count: int) -> list[float]:
    """Read a qout-style file that contains exactly one numeric charge per record."""
    charges: list[float] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.strip().split()
        if not fields:
            continue
        if len(fields) != 1:
            raise ValueError(f"{path}: line {line_number} is not a single RESP charge")
        try:
            value = float(fields[0])
        except ValueError as exc:
            raise ValueError(f"{path}: line {line_number} is not numeric") from exc
        if not math.isfinite(value):
            raise ValueError(f"{path}: line {line_number} is non-finite")
        charges.append(value)
    if len(charges) != expected_count:
        raise ValueError(f"{path}: expected {expected_count} charges, found {len(charges)}")
    return charges


def _mol2_atom_lines(lines: list[str]) -> tuple[int, int]:
    """Return the half-open MOL2 atom-record range, failing on malformed input."""
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "@<TRIPOS>ATOM") + 1
        end = next(i for i in range(start, len(lines)) if lines[i].startswith("@<TRIPOS>"))
    except StopIteration as exc:
        raise ValueError("MOL2 lacks a complete @<TRIPOS>ATOM section") from exc
    return start, end


def _read_mapping(path: Path, mol2_atoms: dict[int, list[str]]) -> list[dict[str, str]]:
    """Require a bijective map between RESP position and MOL2 identity."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows or not {"resp_index", "mol2_atom_id"}.issubset(rows[0]):
        raise ValueError("Mapping TSV requires resp_index and mol2_atom_id columns")
    seen_resp: set[int] = set()
    seen_mol2: set[int] = set()
    for row in rows:
        resp_index, mol2_id = int(row["resp_index"]), int(row["mol2_atom_id"])
        if resp_index < 1 or resp_index in seen_resp or mol2_id in seen_mol2:
            raise ValueError("Mapping RESP indices and MOL2 atom IDs must be unique positive values")
        if mol2_id not in mol2_atoms:
            raise ValueError(f"Mapped MOL2 atom ID {mol2_id} does not exist")
        fields = mol2_atoms[mol2_id]
        if row.get("atom_name") and row["atom_name"] != fields[1]:
            raise ValueError(f"MOL2 atom-name mismatch for atom ID {mol2_id}")
        if row.get("element") and row["element"].upper() != fields[5].split(".")[0].upper():
            raise ValueError(f"MOL2 element/type mismatch for atom ID {mol2_id}")
        seen_resp.add(resp_index)
        seen_mol2.add(mol2_id)
    if seen_resp != set(range(1, len(rows) + 1)):
        raise ValueError("Mapping RESP indices must be contiguous from 1")
    if seen_mol2 != set(mol2_atoms):
        raise ValueError("Mapping must cover every MOL2 atom exactly once")
    return rows


def _run_resp(resp_bin: str, control: Path, esp: Path, qin: Path, qout: Path, log: Path) -> None:
    """Run one native Amber RESP stage and retain its captured console output."""
    command = [resp_bin, "-O", "-i", str(control), "-o", str(log), "-e", str(esp), "-q", str(qin), "-t", str(qout)]
    completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.with_suffix(log.suffix + ".stdout.txt").write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0 or not qout.is_file():
        raise RuntimeError(f"Amber resp stage failed: {' '.join(command)}; inspect {log}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp", type=Path, required=True, help="QM-derived Amber esp.dat")
    parser.add_argument("--resp1-in", type=Path, required=True, help="Reviewed Amber RESP stage-1 input")
    parser.add_argument("--resp2-in", type=Path, required=True, help="Reviewed Amber RESP stage-2 input")
    parser.add_argument("--mol2", type=Path, required=True, help="GAFF2-typed MOL2 with matching QM atom identities")
    parser.add_argument("--atom-map-tsv", type=Path, required=True, help="Explicit RESP-to-MOL2 atom map")
    parser.add_argument("--out-mol2", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--resp-bin", default="resp", help="Amber resp executable or absolute path")
    parser.add_argument("--formal-charge", type=float, required=True)
    parser.add_argument("--charge-tolerance", type=float, default=1.0e-4)
    args = parser.parse_args()

    for required in (args.esp, args.resp1_in, args.resp2_in, args.mol2, args.atom_map_tsv):
        if not required.is_file():
            raise FileNotFoundError(required)
    if shutil.which(args.resp_bin) is None and not Path(args.resp_bin).is_file():
        raise FileNotFoundError(f"Amber resp executable not found: {args.resp_bin}")
    args.workdir.mkdir(parents=True, exist_ok=True)

    mol2_lines = args.mol2.read_text(encoding="utf-8").splitlines()
    atom_start, atom_end = _mol2_atom_lines(mol2_lines)
    mol2_atoms = {int(line.split()[0]): line.split() for line in mol2_lines[atom_start:atom_end]}
    mapping = _read_mapping(args.atom_map_tsv, mol2_atoms)
    atom_count = len(mapping)

    # Stage 1 starts from zero charges. Stage-2 directives in the reviewed input
    # decide which charges are restrained/equivalenced; this script never invents them.
    qzero = args.workdir / "qzero.in"
    qzero.write_text("\n".join("0.000000" for _ in range(atom_count)) + "\n", encoding="ascii")
    qout1, qout2 = args.workdir / "resp1.qout", args.workdir / "resp2.qout"
    _run_resp(args.resp_bin, args.resp1_in, args.esp, qzero, qout1, args.workdir / "resp1.out")
    _read_charge_file(qout1, atom_count)  # Validate before feeding stage 1 to stage 2.
    _run_resp(args.resp_bin, args.resp2_in, args.esp, qout1, qout2, args.workdir / "resp2.out")
    charges = _read_charge_file(qout2, atom_count)
    charge_sum = sum(charges)
    if abs(charge_sum - args.formal_charge) > args.charge_tolerance:
        raise ValueError(f"Final RESP charge sum {charge_sum:.8f} != {args.formal_charge:.8f}")

    charges_by_mol2 = {int(row["mol2_atom_id"]): charges[int(row["resp_index"]) - 1] for row in mapping}
    output = mol2_lines[:]
    for line_index in range(atom_start, atom_end):
        fields = output[line_index].split()
        fields[-1] = f"{charges_by_mol2[int(fields[0])]:.6f}"
        output[line_index] = " ".join(fields)
    args.out_mol2.parent.mkdir(parents=True, exist_ok=True)
    args.out_mol2.write_text("\n".join(output) + "\n", encoding="utf-8")
    report = {
        "status": "PASS", "engine": "Amber native resp two-stage", "esp": str(args.esp.resolve()),
        "resp1_input": str(args.resp1_in.resolve()), "resp2_input": str(args.resp2_in.resolve()),
        "mol2": str(args.mol2.resolve()), "atom_map_tsv": str(args.atom_map_tsv.resolve()),
        "atom_count": atom_count, "formal_charge": args.formal_charge,
        "fitted_charge_sum": charge_sum, "charge_tolerance": args.charge_tolerance,
    }
    (args.workdir / "amber_native_resp_manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
