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

from cypforge_core import prepare_complex_pre_md_equilibration


def main() -> int:
    parser = argparse.ArgumentParser(description="Render third-core multi-stage Amber pre-MD/equilibration inputs.")
    parser.add_argument("--solvation-manifest-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--protocol-config-json", help="Optional user-edited pre_md_protocol_config.json.")
    parser.add_argument("--no-write-default-config", action="store_true")
    parser.add_argument("--stages", default="all", choices=("all", "1-8", "9"),
                        help="Stage range: all (default), 1-8 (restrained), 9 (free NPT only).")
    args = parser.parse_args()

    result = prepare_complex_pre_md_equilibration(
        solvation_manifest_json=Path(args.solvation_manifest_json),
        output_dir=Path(args.output_dir),
        protocol_config_json=Path(args.protocol_config_json) if args.protocol_config_json else None,
        write_default_config=not args.no_write_default_config,
        stages_range=args.stages,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
