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

from cypforge_core import validate_complex_pre_md_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CYPForge pre-MD run outputs.")
    parser.add_argument("--pre-md-manifest-json", required=True)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args()

    result = validate_complex_pre_md_run(
        pre_md_manifest_json=args.pre_md_manifest_json,
        output_json=args.output_json,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
