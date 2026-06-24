#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cypforge_core import build_ligand_mapping_and_leapin


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ligand-aware LEaP residue mapping and ligand_mapping_leapin.in.")
    parser.add_argument("--complex-pdb", required=True)
    parser.add_argument("--prepare-report-json", required=True)
    parser.add_argument("--ligand-mol2", required=True)
    parser.add_argument("--ligand-frcmod", required=True)
    parser.add_argument("--ligand-resname", required=True)
    parser.add_argument("--ligand-chain", default="")
    parser.add_argument("--blank-ligand-chain", action="store_true", help="Select a ligand whose PDB chain ID is blank.")
    parser.add_argument("--expected-ligand-charge", type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--heme-resname", default="HEM")
    args = parser.parse_args()
    if args.blank_ligand_chain:
        args.ligand_chain = ""

    result = build_ligand_mapping_and_leapin(
        complex_pdb=Path(args.complex_pdb),
        prepare_report_json=Path(args.prepare_report_json),
        ligand_mol2=Path(args.ligand_mol2),
        ligand_frcmod=Path(args.ligand_frcmod),
        ligand_resname=args.ligand_resname,
        ligand_chain=args.ligand_chain,
        expected_ligand_charge=args.expected_ligand_charge,
        output_dir=Path(args.output_dir),
        heme_resname=args.heme_resname,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
