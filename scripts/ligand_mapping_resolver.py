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

from cypforge_core.ligand_mapping_resolver import resolve_sdf_to_complex_mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve ligand SDF-to-complex atom mapping with graph+geometry scoring.")
    parser.add_argument("--sdf-template", required=True)
    parser.add_argument("--ligand-pdb", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--max-mappings", type=int, default=50000)
    parser.add_argument("--distance-prune-a", type=float, default=-1.0,
                        help="Pair-distance pruning cutoff; <=0 disables pruning for flexible ligands.")
    parser.add_argument("--rmsd-gap-unique-a", type=float, default=0.25)
    parser.add_argument("--equivalent-rmsd-tol-a", type=float, default=0.02)
    args = parser.parse_args()

    result = resolve_sdf_to_complex_mapping(
        sdf_template=args.sdf_template,
        ligand_pdb=args.ligand_pdb,
        output_json=args.output_json,
        max_mappings=args.max_mappings,
        distance_prune_a=None if args.distance_prune_a <= 0 else args.distance_prune_a,
        rmsd_gap_unique_a=args.rmsd_gap_unique_a,
        equivalent_rmsd_tol_a=args.equivalent_rmsd_tol_a,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
