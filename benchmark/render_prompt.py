#!/usr/bin/env python3
"""Render a CYPForge benchmark prompt from a template + local config.

Reads ``benchmark/config.json`` (created by copying ``config.example.json``
and filling in local paths) and substitutes ``{{key}}`` placeholders inside a
prompt template under ``benchmark/prompts/``. Top-level config keys substitute
as ``{{key}}``; per-case keys substitute as ``{{case.key}}``.

Usage::

    python benchmark/render_prompt.py --case 4EJJ --variant full
    python benchmark/render_prompt.py --case 1Z10 --variant no_outer_shell --out my_run.md

The rendered prompt is written to ``benchmark/build/<run_id>.md`` by default.
The script aborts if any placeholder remains unresolved or if the config still
contains the ``<set to ...>`` example values.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
PROMPTS_DIR = ROOT / "prompts"
BUILD_DIR = ROOT / "build"

REQUIRED_TOP_KEYS = (
    "project_root",
    "benchmark_input_root",
    "run_root_base",
    "wsl_user",
    "amber_sh",
    "multiwfn_bin",
)
REQUIRED_CASE_KEYS = (
    "pdb_rel",
    "sdf_rel",
    "ligand_full_name",
    "ligand_resname",
    "ligand_resid",
    "ligand_atom_count",
    "ligand_chain",
    "blank_ligand_chain",
    "heme_resname",
    "heme_resid",
    "heme_atom_count",
    "heme_chain",
    "blank_heme_chain",
    "heme_state",
    "heme_state_evidence",
    "protein_chain",
    "blank_protein_chain",
    "axial_cys_resname",
    "axial_cys_resid",
    "axial_cys_chain",
    "formal_charge",
    "spin",
    "expected_protonation_decision",
    "expected_protonation_residues",
)

VARIANTS = {
    "full": "full_test.md.tmpl",
    "no_outer_shell": "no_outer_shell_test.md.tmpl",
    "no_cypforge": "no_cypforge_test.md.tmpl",
}


def _die(msg: str) -> "None":
    sys.stderr.write(f"render_prompt: {msg}\n")
    raise SystemExit(2)


def _load_config(path: Path) -> dict:
    if not path.exists():
        _die(
            f"missing {path}. Copy benchmark/config.example.json to benchmark/config.json "
            "and fill in your local paths."
        )
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _die(f"invalid JSON in {path}: {exc}")
    for key in REQUIRED_TOP_KEYS:
        if key not in cfg:
            _die(f"config is missing required top-level key '{key}'.")
        val = cfg[key]
        if not isinstance(val, str) or not val or val.startswith("<set to"):
            _die(
                f"config key '{key}' still has the example placeholder. "
                "Edit benchmark/config.json to set your local value."
            )
    if "cases" not in cfg or not isinstance(cfg["cases"], dict):
        _die("config is missing the 'cases' object.")
    return cfg


def _join_input_path(input_root: str, rel: str) -> str:
    base = input_root.replace("\\", "/").rstrip("/")
    rel_norm = rel.replace("\\", "/").lstrip("/")
    return f"{base}/{rel_norm}"


def _format_chain(value: str, *, is_blank: bool) -> str:
    return "<blank>" if is_blank or value == "" else value


def _build_substitutions(cfg: dict, case_name: str, run_id: str) -> "dict[str, str]":
    cases = cfg["cases"]
    if case_name not in cases:
        available = ", ".join(sorted(cases.keys())) or "<none>"
        _die(f"case '{case_name}' not found in config. Available: {available}")
    case = cases[case_name]
    for key in REQUIRED_CASE_KEYS:
        if key not in case:
            _die(f"case '{case_name}' is missing required key '{key}'.")

    input_root = cfg["benchmark_input_root"]
    run_root = f"{cfg['run_root_base'].replace(chr(92), '/').rstrip('/')}/{run_id}"

    subs: "dict[str, str]" = {
        "project_root": cfg["project_root"],
        "benchmark_input_root": input_root,
        "run_root_base": cfg["run_root_base"],
        "wsl_user": cfg["wsl_user"],
        "amber_sh": cfg["amber_sh"],
        "multiwfn_bin": cfg["multiwfn_bin"],
        "run_id": run_id,
        "run_root": run_root,
        "case.name": case_name,
        "case.pdb_path": _join_input_path(input_root, case["pdb_rel"]),
        "case.sdf_path": _join_input_path(input_root, case["sdf_rel"]),
        "case.ligand_full_name": case["ligand_full_name"],
        "case.ligand_resname": case["ligand_resname"],
        "case.ligand_resid": str(case["ligand_resid"]),
        "case.ligand_atom_count": str(case["ligand_atom_count"]),
        "case.ligand_chain": _format_chain(case["ligand_chain"], is_blank=bool(case["blank_ligand_chain"])),
        "case.ligand_chain_raw": case["ligand_chain"],
        "case.blank_ligand_chain": "true" if case["blank_ligand_chain"] else "false",
        "case.heme_resname": case["heme_resname"],
        "case.heme_resid": str(case["heme_resid"]),
        "case.heme_atom_count": str(case["heme_atom_count"]),
        "case.heme_chain": _format_chain(case["heme_chain"], is_blank=bool(case["blank_heme_chain"])),
        "case.heme_chain_raw": case["heme_chain"],
        "case.blank_heme_chain": "true" if case["blank_heme_chain"] else "false",
        "case.heme_state": case["heme_state"],
        "case.heme_state_evidence": case["heme_state_evidence"],
        "case.protein_chain": _format_chain(case["protein_chain"], is_blank=bool(case["blank_protein_chain"])),
        "case.protein_chain_raw": case["protein_chain"],
        "case.blank_protein_chain": "true" if case["blank_protein_chain"] else "false",
        "case.axial_cys_resname": case["axial_cys_resname"],
        "case.axial_cys_resid": str(case["axial_cys_resid"]),
        "case.axial_cys_chain": _format_chain(case["axial_cys_chain"], is_blank=case["axial_cys_chain"] == ""),
        "case.formal_charge": str(case["formal_charge"]),
        "case.spin": str(case["spin"]),
        "case.expected_protonation_decision": case["expected_protonation_decision"],
        "case.expected_protonation_residues": case["expected_protonation_residues"],
    }
    return subs


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")


def _render(template_text: str, subs: "dict[str, str]") -> str:
    missing: "list[str]" = []

    def repl(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key not in subs:
            missing.append(key)
            return match.group(0)
        return subs[key]

    rendered = _PLACEHOLDER_RE.sub(repl, template_text)
    if missing:
        unique = sorted(set(missing))
        _die("unresolved placeholders: " + ", ".join(unique))
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True, help="case name (e.g. 4EJJ, 1Z10, 1Z11)")
    parser.add_argument(
        "--variant",
        required=True,
        choices=sorted(VARIANTS.keys()),
        help="ablation variant",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="run identifier; default: <variant>_<case>",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="output file path; default: benchmark/build/<run_id>.md",
    )
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="path to benchmark config (default: benchmark/config.json)",
    )
    args = parser.parse_args()

    cfg = _load_config(Path(args.config))
    run_id = args.run_id or f"{args.variant}_{args.case}"
    subs = _build_substitutions(cfg, args.case, run_id)

    template_path = PROMPTS_DIR / VARIANTS[args.variant]
    if not template_path.exists():
        _die(f"template not found: {template_path}")
    template_text = template_path.read_text(encoding="utf-8")
    rendered = _render(template_text, subs)

    out_path = Path(args.out) if args.out else BUILD_DIR / f"{run_id}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
