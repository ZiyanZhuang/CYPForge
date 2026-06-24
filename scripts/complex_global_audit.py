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

from cypforge_core.complex_global_audit import run_complex_global_audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CYPForge third-core global CYP450/heme/ligand audit gates.")
    parser.add_argument("--ligand-mapping-manifest-json", required=True)
    parser.add_argument("--protonation-manifest-json", required=True)
    parser.add_argument("--solvation-manifest-json", required=True)
    parser.add_argument("--pre-md-manifest-json", required=True)
    parser.add_argument("--pre-md-run-validation-json", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = run_complex_global_audit(
        ligand_mapping_manifest_json=args.ligand_mapping_manifest_json,
        protonation_manifest_json=args.protonation_manifest_json,
        solvation_manifest_json=args.solvation_manifest_json,
        pre_md_manifest_json=args.pre_md_manifest_json,
        pre_md_run_validation_json=args.pre_md_run_validation_json,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
