#!/usr/bin/env python3
"""CYPForge Outer Shell — workflow orchestration CLI.

Usage:
    cypforge init <run_name> [options]
    cypforge run <run_name>
    cypforge resume <run_name>
    cypforge status <run_name>
    cypforge context <run_name>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .orchestrator import CYPForgeOrchestrator, RunConfig


VERSION = "1.1.0"


def _default_runs_dir() -> str:
    """Default base directory for run roots.

    Priority: ``$CYPFORGE_RUNS_DIR`` > platform-specific default.
    On Windows we keep the historical ``C:\\cypforge_runs`` for backward
    compatibility; on POSIX hosts we fall back to ``~/cypforge_runs`` so the
    CLI does not invent an unwritable path. Override per-run with
    ``--run-root`` or globally with the environment variable.
    """
    override = os.environ.get("CYPFORGE_RUNS_DIR")
    if override:
        return override
    if os.name == "nt":
        return r"C:\cypforge_runs"
    return str(Path.home() / "cypforge_runs")


DEFAULT_RUNS_DIR = _default_runs_dir()


# ══════════════════════════════════════════════════════════════════════════════
#  Banner
# ══════════════════════════════════════════════════════════════════════════════

BANNER = (
    "   ██████╗██╗   ██╗██████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗\n"
    "  ██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝\n"
    "  ██║      ╚████╔╝ ██████╔╝█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  \n"
    "  ██║       ╚██╔╝  ██╔═══╝ ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  \n"
    "  ╚██████╗   ██║   ██║     ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗\n"
    "   ╚═════╝   ╚═╝   ╚═╝     ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝\n"
    f"   CYP450 Amber MD Preprocessing Framework  —  v{VERSION}\n"
)


def _print_banner() -> None:
    print(BANNER)


def _detect_project_root() -> str:
    """Locate the project root that contains src/cypforge_core/.

    In source / editable installs, `Path(__file__).resolve().parents[2]` is the
    repo root and contains `src/cypforge_core/`. In a wheel install no such
    layout exists; fall back to CWD with a stderr warning so the user can pass
    `--project-root` explicitly.
    """
    guessed = Path(__file__).resolve().parents[2]
    if (guessed / "src" / "cypforge_core").is_dir():
        return str(guessed)
    cwd = Path.cwd()
    if (cwd / "src" / "cypforge_core").is_dir():
        return str(cwd)
    print(
        f"[WARN] could not auto-detect project_root (tried {guessed} and {cwd}); "
        "falling back to CWD. Pass --project-root to override.",
        file=sys.stderr,
    )
    return str(cwd)


# ══════════════════════════════════════════════════════════════════════════════
#  RunConfig field list — single source of truth for serialization
# ══════════════════════════════════════════════════════════════════════════════

_RUN_CONFIG_SCALAR_FIELDS = [
    "run_name", "run_root", "project_root",
    "raw_protein_heme_pdb", "ligand_template_sdf",
    "heme_state", "heme_resname", "heme_chain", "protein_chain",
    "ligand_resname", "ligand_chain",
    "basis", "fit_method", "pre_resp_relax",
    "protonation_decision_json",
    "protein_force_field", "water_leaprc", "water_model", "box_type",
    "neutralizing_anion",
    "wsl_user", "amber_sh", "multiwfn_bin",
]
_RUN_CONFIG_INT_FIELDS = [
    "axial_cys_resid", "formal_charge", "spin", "points_per_atom", "max_retries",
]
_RUN_CONFIG_FLOAT_FIELDS = ["buffer_a"]
_RUN_CONFIG_BOOL_FIELDS = ["auto_accept_warn"]


def _run_config_to_dict(config: RunConfig) -> dict:
    """Serialize a RunConfig to a JSON-safe dict."""
    d: dict = {}
    for name in _RUN_CONFIG_SCALAR_FIELDS:
        d[name] = getattr(config, name, "")
    for name in _RUN_CONFIG_INT_FIELDS:
        val = getattr(config, name, None)
        d[name] = val if val is not None else 0
    for name in _RUN_CONFIG_FLOAT_FIELDS:
        d[name] = getattr(config, name, 0.0)
    for name in _RUN_CONFIG_BOOL_FIELDS:
        d[name] = getattr(config, name, False)
    return d


def _dict_to_run_config(data: dict, defaults: dict | None = None) -> RunConfig:
    """Build a RunConfig from a dict, with optional defaults for missing keys."""
    if defaults is None:
        defaults = {}
    def _s(name: str) -> str:
        return data.get(name, defaults.get(name, ""))
    def _i(name: str) -> int | None:
        val = data.get(name, defaults.get(name, 0))
        return int(val) if val is not None else None
    def _f(name: str) -> float:
        return float(data.get(name, defaults.get(name, 10.0)))
    def _b(name: str) -> bool:
        return bool(data.get(name, defaults.get(name, False)))

    return RunConfig(
        run_name=_s("run_name"),
        run_root=_s("run_root"),
        project_root=_s("project_root"),
        raw_protein_heme_pdb=_s("raw_protein_heme_pdb"),
        ligand_template_sdf=_s("ligand_template_sdf"),
        heme_state=_s("heme_state") or "IC6",
        heme_resname=_s("heme_resname") or "HEM",
        heme_chain=_s("heme_chain"),
        protein_chain=_s("protein_chain"),
        axial_cys_resid=data.get("axial_cys_resid"),
        ligand_resname=_s("ligand_resname") or "NCT",
        ligand_chain=_s("ligand_chain"),
        formal_charge=int(data.get("formal_charge", 0)),
        spin=int(data.get("spin", 1)),
        basis=_s("basis") or "6-31G*",
        points_per_atom=int(data.get("points_per_atom", 8)),
        fit_method=_s("fit_method") or "multiwfn-resp",
        pre_resp_relax=_s("pre_resp_relax") or "pbe-h-only",
        protonation_decision_json=_s("protonation_decision_json"),
        protein_force_field=_s("protein_force_field") or "ff19SB",
        water_leaprc=_s("water_leaprc") or "leaprc.water.tip3p",
        water_model=_s("water_model") or "TIP3PBOX",
        box_type=_s("box_type") or "oct",
        buffer_a=float(data.get("buffer_a", 10.0)),
        neutralizing_anion=_s("neutralizing_anion") or "Cl-",
        wsl_user=_s("wsl_user"),
        amber_sh=_s("amber_sh"),
        multiwfn_bin=_s("multiwfn_bin"),
        auto_accept_warn=_b("auto_accept_warn"),
        max_retries=int(data.get("max_retries", 0)),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Command implementations
# ══════════════════════════════════════════════════════════════════════════════

def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new CYPForge run."""
    run_name = args.run_name
    run_root = str(Path(args.run_root) if args.run_root else Path(DEFAULT_RUNS_DIR) / run_name)
    project_root = args.project_root or _detect_project_root()
    ligand_chain = "" if args.blank_ligand_chain else args.ligand_chain

    # ── input validation warnings ──────────────────────────────────────
    warnings: list[str] = []

    if not args.pdb:
        warnings.append("--pdb is not set; Core 1 will fail without a protein+heme PDB file.")
    elif not Path(args.pdb).is_file():
        warnings.append(f"--pdb file not found: {args.pdb}")

    if not args.sdf:
        warnings.append("--sdf is not set; Core 2 will fail without a ligand template SDF file.")
    elif not Path(args.sdf).is_file():
        warnings.append(f"--sdf file not found: {args.sdf}")

    if not (Path(project_root) / "src" / "cypforge_core").is_dir():
        warnings.append(
            f"project_root does not contain src/cypforge_core/: {project_root}"
        )

    amber_sh = args.amber_sh or os.environ.get("AMBER_SH", os.environ.get("AMBERHOME", ""))
    if not amber_sh:
        warnings.append("AMBER_SH not set; WSL Amber commands will fail. Set --amber-sh or $env:AMBER_SH.")

    multiwfn = args.multiwfn_bin or os.environ.get("MULTIWFN_BIN", "")
    if not multiwfn and args.fit_method == "multiwfn-resp":
        warnings.append("MULTIWFN_BIN not set; RESP charge fitting requires Multiwfn. Set --multiwfn-bin or $env:MULTIWFN_BIN.")

    for w in warnings:
        print(f"[WARN] {w}")

    if warnings:
        print()

    config = RunConfig(
        run_name=run_name,
        run_root=run_root,
        project_root=project_root,
        raw_protein_heme_pdb=args.pdb or "",
        ligand_template_sdf=args.sdf or "",
        heme_state=args.heme_state,
        heme_resname=args.heme_resname,
        heme_chain=args.heme_chain or "",
        protein_chain=args.protein_chain or "",
        axial_cys_resid=args.axial_cys_resid,
        ligand_resname=args.ligand_resname,
        ligand_chain=ligand_chain,
        formal_charge=args.formal_charge,
        spin=args.spin,
        basis=args.basis,
        points_per_atom=args.points_per_atom,
        fit_method=args.fit_method,
        pre_resp_relax=args.pre_resp_relax,
        protonation_decision_json=args.protonation_decision_json or "",
        protein_force_field=args.protein_force_field,
        water_leaprc=args.water_leaprc,
        water_model=args.water_model,
        box_type=args.box_type,
        buffer_a=args.buffer_a,
        neutralizing_anion=args.neutralizing_anion,
        wsl_user=args.wsl_user,
        amber_sh=args.amber_sh or "",
        multiwfn_bin=args.multiwfn_bin or "",
        auto_accept_warn=args.auto_accept_warn,
        max_retries=args.max_retries,
    )

    orch = CYPForgeOrchestrator(config)
    orch.init()

    print(f"Run initialized: {run_name}")
    print(f"  Run root:    {run_root}")
    print(f"  Project:     {project_root}")
    print(f"  Config:      {orch.workflow.config_path}")
    print(f"  Manifest:    {orch.workflow.manifest_path}")
    print(f"\n{orch.status()}")

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run the full pipeline (or resume from checkpoint)."""
    config = _load_config(args.run_name, args.run_root)
    if config is None:
        return 1

    orch = CYPForgeOrchestrator(config)
    manifest = orch.run()

    print(f"\n{orch.status()}")
    if manifest.workflow_status == "STOPPED_ON_FAIL":
        return 2
    if manifest.workflow_status == "PAUSED":
        return 3
    return 0


def cmd_prep_only(args: argparse.Namespace) -> int:
    """Run preprocessing through pre-MD input rendering, without launching MD."""
    config = _load_config(args.run_name, args.run_root)
    if config is None:
        return 1

    orch = CYPForgeOrchestrator(config)
    manifest = orch.run_until(stop_before_skill_id="cypforge.core3_run_pre_md")

    print(f"\n{orch.status()}")
    if manifest.workflow_status == "STOPPED_ON_FAIL":
        return 2
    if manifest.workflow_status == "PAUSED":
        return 3
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume a paused or failed run."""
    config = _load_config(args.run_name, args.run_root)
    if config is None:
        return 1

    orch = CYPForgeOrchestrator(config)
    manifest = orch.resume()

    print(f"\n{orch.status()}")
    if manifest.workflow_status == "STOPPED_ON_FAIL":
        return 2
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Print workflow status table."""
    config = _load_config(args.run_name, args.run_root)
    if config is None:
        return 1

    orch = CYPForgeOrchestrator(config)
    print(orch.status())
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    """Print aggregated context dict as JSON (for LLM agent consumption)."""
    config = _load_config(args.run_name, args.run_root)
    if config is None:
        return 1

    orch = CYPForgeOrchestrator(config)
    ctx = orch.get_context()
    print(json.dumps(ctx, indent=2, ensure_ascii=False))
    return 0


def _load_config(run_name: str, run_root_override: str | None) -> RunConfig | None:
    """Load RunConfig from an existing run's run_config.json."""
    run_root = run_root_override or str(Path(DEFAULT_RUNS_DIR) / run_name)
    config_path = Path(run_root) / "run_config.json"

    if not config_path.is_file():
        print(f"[ERROR] No run found at: {run_root}")
        print(f"        Config file missing: {config_path}")
        print(f"        Run 'cypforge init {run_name} ...' first.")
        return None

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[ERROR] Cannot read config: {config_path}")
        print(f"        {exc}")
        return None

    return _dict_to_run_config(data, defaults={"run_name": run_name, "run_root": run_root})


# ══════════════════════════════════════════════════════════════════════════════
#  Argument parser
# ══════════════════════════════════════════════════════════════════════════════

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cypforge",
        description="CYPForge Outer Shell — automated CYP450 Amber MD preprocessing workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        epilog=(
            "Examples:\n"
            "  cypforge init my_run --pdb complex.pdb --sdf ligand.sdf\n"
            "  cypforge run my_run\n"
            "  cypforge prep-only my_run\n"
            "  cypforge status my_run\n"
            "  cypforge context my_run > agent_input.json\n"
        ),
    )
    parser.add_argument(
        "-h", "--help", action="store_true", dest="show_help",
        help="Show this help message and exit",
    )
    parser.add_argument(
        "--version", "-V", action="version",
        version=f"cypforge v{VERSION}  (CYPForge {VERSION})",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── init ──────────────────────────────────────────────────────────
    p_init = sub.add_parser(
        "init",
        help="Initialize a new CYPForge run",
        description="Create a run directory with configuration and a fresh workflow manifest. "
                    "All 10 pipeline modules start in PENDING state.",
        epilog="After init, use 'run' to execute the full pipeline or 'status' to inspect.",
    )
    p_init.add_argument("run_name", help=f"Unique name for this run (used as directory name under {DEFAULT_RUNS_DIR}; override base with $CYPFORGE_RUNS_DIR or --run-root)")
    p_init.add_argument("--run-root", help=f"Override default run root (default base: {DEFAULT_RUNS_DIR}; env $CYPFORGE_RUNS_DIR also accepted)")
    p_init.add_argument("--project-root", help="Override project root (default: auto-detected from cli.py location)")
    p_init.add_argument("--pdb", help="[REQUIRED for Core 1] Input protein+heme PDB file")
    p_init.add_argument("--sdf", help="[REQUIRED for Core 2] Input ligand template SDF file")
    p_init.add_argument("--heme-state", default="IC6", choices=("IC6", "DIOXY", "CPDI", "CUSTOM"),
                        help="Heme electronic state (default: IC6)")
    p_init.add_argument("--heme-resname", default="HEM", help="Heme residue name in PDB (default: HEM)")
    p_init.add_argument("--heme-chain", default="", help="Heme chain ID in PDB")
    p_init.add_argument("--protein-chain", default="", help="Protein chain ID in PDB")
    p_init.add_argument("--axial-cys-resid", type=int, help="Residue ID of axial cysteine")
    p_init.add_argument("--ligand-resname", default="NCT", help="Ligand residue name (default: NCT)")
    p_init.add_argument("--ligand-chain", default="", help="Ligand chain ID (default: blank). Pass --blank-ligand-chain for blank chain handling.")
    p_init.add_argument("--blank-ligand-chain", action="store_true",
                        help="Select a ligand whose PDB chain ID is blank; overrides --ligand-chain.")
    p_init.add_argument("--formal-charge", type=int, default=0, help="Ligand formal charge (default: 0)")
    p_init.add_argument("--spin", type=int, default=1, help="Ligand spin multiplicity (default: 1)")
    p_init.add_argument("--basis", default="6-31G*", help="QM basis set for RESP (default: 6-31G*)")
    p_init.add_argument("--points-per-atom", type=int, default=8, help="ESP grid points per atom (default: 8)")
    p_init.add_argument("--fit-method", default="multiwfn-resp", choices=("multiwfn-resp", "esp-lsq"),
                        help="Charge fitting method (default: multiwfn-resp)")
    p_init.add_argument("--pre-resp-relax", default="pbe-h-only",
                        help="Pre-RESP geometry relaxation mode (default: pbe-h-only)")
    p_init.add_argument("--protonation-decision-json", help="Path to protonation decision JSON (required for Core 3)")
    p_init.add_argument("--protein-force-field", default="ff19SB", choices=("ff14SB", "ff19SB"),
                        help="Protein force field (default: ff19SB)")
    p_init.add_argument("--water-leaprc", default="leaprc.water.tip3p", help="Water LEaP rc file")
    p_init.add_argument("--water-model", default="TIP3PBOX", help="Water model (default: TIP3PBOX)")
    p_init.add_argument("--box-type", default="oct", choices=("oct", "box"),
                        help="Solvent box type (default: oct)")
    p_init.add_argument("--buffer-a", type=float, default=10.0, help="Solvent buffer distance in A (default: 10.0)")
    p_init.add_argument("--neutralizing-anion", default="Cl-", help="Neutralizing ion (default: Cl-)")
    p_init.add_argument("--wsl-user", default=None, help="WSL username for Amber commands (required for WSL steps; falls back to the WSL distro's default user if omitted)")
    p_init.add_argument("--amber-sh", default="", help="Path to amber.sh in WSL (or set AMBER_SH env var)")
    p_init.add_argument("--multiwfn-bin", default="", help="Path to Multiwfn binary (or set MULTIWFN_BIN env var)")
    p_init.add_argument("--auto-accept-warn", action="store_true",
                        help="Auto-accept WARN gates without pausing for human review")
    p_init.add_argument("--max-retries", type=int, default=0, help="Max retries on module failure (default: 0)")

    # ── run ───────────────────────────────────────────────────────────
    p_run = sub.add_parser(
        "run",
        help="Execute the full pipeline",
        description="Run all pending modules in order. If a run_manifest.json exists, "
                    "automatically resumes from the checkpoint. Stops on FAIL or pauses on WARN "
                    "(unless --auto-accept-warn was set at init).",
    )
    p_run.add_argument("run_name", help="Name of the run to execute")
    p_run.add_argument("--run-root", help="Override run root directory")

    # ── prep-only ─────────────────────────────────────────────────────
    p_prep = sub.add_parser(
        "prep-only",
        help="Run through pre-MD input rendering without launching MD",
        description="Execute pending preprocessing modules through cypforge.core3_render_pre_md, "
                    "then stop before cypforge.core3_run_pre_md. This generates and audits "
                    "pre-MD input files but does not call pmemd.cuda, pmemd, or sander.",
    )
    p_prep.add_argument("run_name", help="Name of the run to execute")
    p_prep.add_argument("--run-root", help="Override run root directory")

    # ── resume ────────────────────────────────────────────────────────
    p_resume = sub.add_parser(
        "resume",
        help="Resume a paused or failed run",
        description="Continue a run that was paused (WARN gate awaiting review) or stopped (FAIL gate). "
                    "Review and fix the failed module before resuming. Re-runs the failed module "
                    "and continues downstream.",
    )
    p_resume.add_argument("run_name", help="Name of the run to resume")
    p_resume.add_argument("--run-root", help="Override run root directory")

    # ── status ────────────────────────────────────────────────────────
    p_status = sub.add_parser(
        "status",
        help="Show workflow status table",
        description="Display a table of all 10 pipeline modules with their current status "
                    "(PENDING / RUNNING / PASS / WARN / FAIL) and gate results. "
                    "An arrow (←) marks the current or blocking module.",
    )
    p_status.add_argument("run_name", help="Name of the run to inspect")
    p_status.add_argument("--run-root", help="Override run root directory")

    # ── context ───────────────────────────────────────────────────────
    p_context = sub.add_parser(
        "context",
        help="Export aggregated context for LLM agent",
        description="Read all completed module manifests and produce a structured JSON document "
                    "containing workflow state, gate results, chemical metrics, and policy reminders. "
                    "This is the input format for LLM agent decision-making at gated review points. "
                    "Output is pure JSON on stdout (no banner).",
    )
    p_context.add_argument("run_name", help="Name of the run to export context from")
    p_context.add_argument("--run-root", help="Override run root directory")

    return parser


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # Show banner on every command except 'context' (which produces pure JSON).
    # Also show banner before help text.
    if args.command != "context":
        _print_banner()

    if args.show_help:
        parser.print_help()
        return 0

    if args.command == "init":
        return cmd_init(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "prep-only":
        return cmd_prep_only(args)
    elif args.command == "resume":
        return cmd_resume(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "context":
        return cmd_context(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
