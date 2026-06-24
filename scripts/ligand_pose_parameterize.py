from __future__ import annotations

import argparse
import json
from pathlib import Path

from cypforge_core import parameterize_selected_ligand_pose


def main() -> int:
    parser = argparse.ArgumentParser(description="Parameterize a user-selected ligand pose MOL2.")
    parser.add_argument("--pose-mol2", required=True)
    parser.add_argument("--charge-csv", required=True)
    parser.add_argument("--formal-charge", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--resname", default=None)
    parser.add_argument("--no-parmchk2", action="store_true")
    parser.add_argument("--amber-sh", default=None, help="Path to amber.sh. Default: $AMBER_SH, then $AMBERHOME/amber.sh. Required if env vars are not set.")
    args = parser.parse_args()

    result = parameterize_selected_ligand_pose(
        pose_mol2=Path(args.pose_mol2),
        charge_csv=Path(args.charge_csv),
        formal_charge=args.formal_charge,
        output_dir=Path(args.output_dir),
        resname=args.resname,
        run_parmchk2=not args.no_parmchk2,
        amber_sh=args.amber_sh,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
