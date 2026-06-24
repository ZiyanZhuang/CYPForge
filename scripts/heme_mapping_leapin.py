from __future__ import annotations

import argparse
import json
from pathlib import Path

from cypforge_core import build_heme_mapping_and_leapin


def main() -> int:
    parser = argparse.ArgumentParser(description="Build heme/CYM LEaP mapping and heme_mapping_leapin.in.")
    parser.add_argument("--prepared-pdb", required=True)
    parser.add_argument("--prepare-report-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--heme-resname", default="HEM")
    args = parser.parse_args()

    result = build_heme_mapping_and_leapin(
        prepared_pdb=Path(args.prepared_pdb),
        prepare_report_json=Path(args.prepare_report_json),
        output_dir=Path(args.output_dir),
        heme_resname=args.heme_resname,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
