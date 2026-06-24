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

from cypforge_core import validate_solvation_tleap_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate solvated tleap outputs after running LEaP.")
    parser.add_argument("--solvation-manifest-json", required=True)
    parser.add_argument("--leap-log", default=None)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args()

    result = validate_solvation_tleap_outputs(
        solvation_manifest_json=args.solvation_manifest_json,
        leap_log=args.leap_log,
        output_json=args.output_json,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
