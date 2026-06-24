#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cypforge_core.ligand_vina_pose_selection import run_vina_crystal_rmsd_selection


def main() -> int:
    parser = argparse.ArgumentParser(description="Dock with heme retained, then select the pose with minimum heavy-atom RMSD to crystal ligand.")
    parser.add_argument("--current-receptor-pdb", required=True)
    parser.add_argument("--crystal-clean-pdb", required=True)
    parser.add_argument("--ligand-resname", required=True)
    parser.add_argument("--ligand-chain", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--vina-bin",
        default=os.environ.get("VINA_EXE"),
        help="Path to the AutoDock Vina executable (defaults to $env:VINA_EXE if unset)",
    )
    parser.add_argument("--exhaustiveness", type=int, default=128)
    parser.add_argument("--num-modes", type=int, default=100)
    parser.add_argument("--energy-range", type=float, default=10.0)
    parser.add_argument("--cpu", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260531)
    parser.add_argument("--box-size", type=float, default=20.0)
    args = parser.parse_args()
    if not args.vina_bin:
        print("ERROR: --vina-bin is required (or set the VINA_EXE environment variable).", file=sys.stderr)
        return 2

    manifest = run_vina_crystal_rmsd_selection(
        current_receptor_pdb=args.current_receptor_pdb,
        crystal_clean_pdb=args.crystal_clean_pdb,
        ligand_resname=args.ligand_resname,
        ligand_chain=args.ligand_chain,
        output_dir=args.output_dir,
        vina_bin=args.vina_bin,
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        energy_range=args.energy_range,
        cpu=args.cpu,
        seed=args.seed,
        box_size=args.box_size,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
