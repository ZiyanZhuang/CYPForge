from __future__ import annotations

import argparse
import json
from pathlib import Path

from cypforge_core import parameterize_protein_heme_complex


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare protein+heme/CYP coordinates for a CYPForge heme state. "
                    "Use --heme-state CUSTOM with --custom-heme-mol2/--custom-cyp-mol2/"
                    "--custom-frcmod to supply externally-built parameters (e.g. MCPB.py)."
    )
    parser.add_argument("pdb", help="Input protein+heme PDB.")
    parser.add_argument("--heme-state", required=True,
                        choices=("IC6", "DIOXY", "CPDI", "CUSTOM"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--heme-resname", default="HEM")
    parser.add_argument("--heme-chain", default=None)
    parser.add_argument("--protein-chain", default=None)
    parser.add_argument("--axial-cys-resid", type=int, default=None)
    parser.add_argument("--custom-heme-mol2", default=None,
                        help="User-supplied HEM.mol2 (required for --heme-state CUSTOM).")
    parser.add_argument("--custom-cyp-mol2", default=None,
                        help="User-supplied CYP.mol2 (required for --heme-state CUSTOM).")
    parser.add_argument("--custom-frcmod", default=None,
                        help="User-supplied frcmod (required for --heme-state CUSTOM).")
    parser.add_argument("--custom-state-label", default=None,
                        help="Label for the custom state recorded in the manifest (e.g. 'MCPB_IC6').")
    parser.add_argument(
        "--trim-transmembrane-range",
        action="append",
        default=None,
        metavar="CHAIN:START-END",
        help=(
            "Optional Core-1 preprocessing: remove an explicit protein residue range before "
            "heme/CYP preparation, e.g. A:1-35. May be repeated or comma-separated. "
            "No transmembrane helix prediction is performed."
        ),
    )
    parser.add_argument(
        "--confirm-transmembrane-trim",
        action="store_true",
        help=(
            "Required with --trim-transmembrane-range. Confirms that a human supplied the exact "
            "chain:residue ranges and accepts structural responsibility for removing them."
        ),
    )
    args = parser.parse_args()

    if args.heme_state == "CUSTOM":
        missing = []
        if not args.custom_heme_mol2:
            missing.append("--custom-heme-mol2")
        if not args.custom_cyp_mol2:
            missing.append("--custom-cyp-mol2")
        if not args.custom_frcmod:
            missing.append("--custom-frcmod")
        if missing:
            parser.error(f"--heme-state CUSTOM requires: {', '.join(missing)}")

    result = parameterize_protein_heme_complex(
        Path(args.pdb),
        heme_state=args.heme_state,
        output_dir=Path(args.output_dir),
        heme_resname=args.heme_resname,
        heme_chain=args.heme_chain,
        protein_chain=args.protein_chain,
        axial_cys_resid=args.axial_cys_resid,
        template_mol2_path=args.custom_heme_mol2,
        cyp_mol2_path=args.custom_cyp_mol2,
        frcmod_path=args.custom_frcmod,
        custom_state_label=args.custom_state_label,
        trim_transmembrane_ranges=args.trim_transmembrane_range,
        trim_transmembrane_confirmed=args.confirm_transmembrane_trim,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
