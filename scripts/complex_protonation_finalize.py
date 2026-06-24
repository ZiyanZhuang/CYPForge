#!/usr/bin/env python3
"""Apply or analyze protonation-state residue renames for a ligand-aware LEaP package.

Default mode (no --analyze-only): apply renames from a decision JSON.
Analyze-only mode (--analyze-only): produce a structured report of current
protonation state and proposed changes without modifying any files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cypforge_core import analyze_protonation_state, finalize_complex_protonation_mapping


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply protonation-state residue renames or analyze current state."
    )
    parser.add_argument("--ligand-mapping-manifest-json", required=True)
    parser.add_argument("--original-prepared-pdb", required=True)
    parser.add_argument(
        "--protonation-decision-json",
        default=None,
        help="JSON with recommended_changes, expected_residue_checks, etc. Required for apply mode.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Analyze current protonation state and report proposed changes; do not modify any files.",
    )
    args = parser.parse_args()

    if args.analyze_only:
        result = analyze_protonation_state(
            ligand_mapping_manifest_json=Path(args.ligand_mapping_manifest_json),
            original_prepared_pdb=Path(args.original_prepared_pdb),
            protonation_decision_json=Path(args.protonation_decision_json) if args.protonation_decision_json else None,
            output_dir=Path(args.output_dir),
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if not args.protonation_decision_json:
        parser.error("--protonation-decision-json is required for apply mode. Use --analyze-only for analysis without applying changes.")

    result = finalize_complex_protonation_mapping(
        ligand_mapping_manifest_json=Path(args.ligand_mapping_manifest_json),
        original_prepared_pdb=Path(args.original_prepared_pdb),
        protonation_decision_json=Path(args.protonation_decision_json),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
