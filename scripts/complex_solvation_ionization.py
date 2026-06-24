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

from cypforge_core import prepare_complex_solvation_ionization


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare third-core solvation/neutralization LEaP input.")
    parser.add_argument("--protonation-manifest-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--protein-force-field", choices=["ff14SB", "ff19SB"], default="ff19SB")
    parser.add_argument("--water-leaprc", default="leaprc.water.tip3p")
    parser.add_argument("--water-model", default="TIP3PBOX")
    parser.add_argument("--box-type", choices=["oct", "box"], default="oct")
    parser.add_argument("--buffer-a", type=float, default=10.0)
    parser.add_argument("--neutralizing-anion", default="Cl-")
    args = parser.parse_args()

    result = prepare_complex_solvation_ionization(
        protonation_manifest_json=Path(args.protonation_manifest_json),
        output_dir=Path(args.output_dir),
        protein_force_field=args.protein_force_field,
        water_leaprc=args.water_leaprc,
        water_model=args.water_model,
        box_type=args.box_type,
        buffer_a=args.buffer_a,
        neutralizing_anion=args.neutralizing_anion,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
