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

from cypforge_core import check_ligand_pose_frame


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ligand pose coordinates against the current target-heme receptor frame.")
    parser.add_argument("--current-receptor-pdb", required=True)
    parser.add_argument("--docking-receptor-pdb", required=True)
    parser.add_argument("--ligand-mol2", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--heme-resname", default="HEM")
    parser.add_argument("--ligand-resname", default="LIG")
    parser.add_argument("--anchor-rmsd-threshold", type=float, default=0.25)
    args = parser.parse_args()

    report = check_ligand_pose_frame(
        current_receptor_pdb=args.current_receptor_pdb,
        docking_receptor_pdb=args.docking_receptor_pdb,
        ligand_mol2=args.ligand_mol2,
        output_dir=args.output_dir,
        heme_resname=args.heme_resname,
        ligand_resname=args.ligand_resname,
        anchor_rmsd_threshold=args.anchor_rmsd_threshold,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
