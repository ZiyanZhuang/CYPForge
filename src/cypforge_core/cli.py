#!/usr/bin/env python3
"""CYPForge Outer Shell workflow orchestration CLI.

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
from datetime import datetime, timezone
from pathlib import Path

from .complex_protonation_finalize import (
    build_protonation_decision_from_selectors,
    finalize_complex_protonation_mapping,
    recommend_protonation_states,
)
from .complex_pre_md_equilibration import prepare_complex_pre_md_equilibration, validate_complex_pre_md_run
from .complex_solvation_ionization import prepare_complex_solvation_ionization, validate_solvation_tleap_outputs
from .complex_global_audit import run_complex_global_audit
from .heme_mapping_leapin import build_heme_mapping_and_leapin
from .heme_parameterization import parameterize_protein_heme_complex
from .ligand_mapping_leapin import build_ligand_mapping_and_leapin
from .ligand_gpu4pyscf_esp import (
    extract_ligand_from_complex_pdb,
    prepare_complex_sdf_ligand_resp_inputs,
    prepare_gpu4pyscf_esp_job,
    prepare_gpu4pyscf_molden_job,
    run_complex_ligand_multiwfn_resp_parameterization,
    run_complex_sdf_ligand_multiwfn_resp_parameterization,
    run_gpu4pyscf_esp_parameterization,
    run_gpu4pyscf_multiwfn_resp_parameterization,
    stage_supplied_ligand_parameters,
)
from .local_knowledge import LocalDocsIndex, build_run_diagnosis, load_profile, update_profile
from .orchestrator import CYPForgeOrchestrator, RunConfig


VERSION = "1.3.0"


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


#  Banner

BANNER = f"CYPForge v{VERSION}\nCYP450 Amber MD preprocessing framework\n"


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


#  RunConfig field list - single source of truth for serialization

_RUN_CONFIG_SCALAR_FIELDS = [
    "run_name", "run_root", "project_root",
    "raw_protein_heme_pdb", "ligand_template_sdf",
    "supplied_ligand_mol2", "supplied_ligand_frcmod",
    "heme_state", "heme_resname", "heme_chain", "protein_chain",
    "trim_transmembrane_ranges",
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
_RUN_CONFIG_BOOL_FIELDS = ["trim_transmembrane_confirmed", "auto_accept_warn"]


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
        val = data.get(name, defaults.get(name, False))
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            normalized = val.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off", ""}:
                return False
        if val in (0, 1):
            return bool(val)
        raise ValueError(f"Invalid boolean value for {name}: {val!r}")

    return RunConfig(
        run_name=_s("run_name"),
        run_root=_s("run_root"),
        project_root=_s("project_root"),
        raw_protein_heme_pdb=_s("raw_protein_heme_pdb"),
        ligand_template_sdf=_s("ligand_template_sdf"),
        supplied_ligand_mol2=_s("supplied_ligand_mol2"),
        supplied_ligand_frcmod=_s("supplied_ligand_frcmod"),
        heme_state=_s("heme_state") or "IC6",
        heme_resname=_s("heme_resname") or "HEM",
        heme_chain=_s("heme_chain"),
        protein_chain=_s("protein_chain"),
        axial_cys_resid=data.get("axial_cys_resid"),
        trim_transmembrane_ranges=_s("trim_transmembrane_ranges"),
        trim_transmembrane_confirmed=_b("trim_transmembrane_confirmed"),
        ligand_resname=_s("ligand_resname"),
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


#  Command implementations

def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new CYPForge run."""
    run_name = args.run_name
    try:
        profile_values = load_profile().get("values", {})
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR] Cannot read the local CYPForge profile: {exc}")
        return 2

    runs_dir = str(profile_values.get("runs_dir", "")) or DEFAULT_RUNS_DIR
    run_root = str(Path(args.run_root) if args.run_root else Path(runs_dir) / run_name)
    project_root = args.project_root or _detect_project_root()
    ligand_chain = "" if args.blank_ligand_chain else args.ligand_chain

    def _normalize_input_path(value: str | None) -> str:
        if not value:
            return ""
        return str(Path(value).expanduser().resolve())

    pdb_path = _normalize_input_path(args.pdb)
    sdf_path = _normalize_input_path(args.sdf)
    supplied_mol2_path = _normalize_input_path(args.supplied_ligand_mol2)
    supplied_frcmod_path = _normalize_input_path(args.supplied_ligand_frcmod)

    # input validation warnings
    warnings: list[str] = []

    if not pdb_path:
        warnings.append("--pdb is not set; Core 1 will fail without a protein+heme PDB file.")
    elif not Path(pdb_path).is_file():
        warnings.append(f"--pdb file not found: {args.pdb}")

    if not sdf_path:
        warnings.append("--sdf is not set; Core 2 will fail without a ligand template SDF file.")
    elif not Path(sdf_path).is_file():
        warnings.append(f"--sdf file not found: {args.sdf}")

    if not args.ligand_resname:
        print("[ERROR] --ligand-resname is required; CYPForge no longer defaults to a benchmark-specific ligand name.")
        return 2

    if not (Path(project_root) / "src" / "cypforge_core").is_dir():
        warnings.append(
            f"project_root does not contain src/cypforge_core/: {project_root}"
        )

    amber_sh = (
        args.amber_sh
        or os.environ.get("AMBER_SH", os.environ.get("AMBERHOME", ""))
        or str(profile_values.get("amber_sh", ""))
    )
    if not amber_sh:
        warnings.append("AMBER_SH not set; WSL Amber commands will fail. Set --amber-sh or $env:AMBER_SH.")

    supplied_pair = bool(supplied_mol2_path and supplied_frcmod_path)
    if bool(supplied_mol2_path) != bool(supplied_frcmod_path):
        print("[ERROR] --supplied-ligand-mol2 and --supplied-ligand-frcmod must be provided together.")
        return 2
    for supplied_path, label in (
        (supplied_mol2_path, "--supplied-ligand-mol2"),
        (supplied_frcmod_path, "--supplied-ligand-frcmod"),
    ):
        if supplied_path and not Path(supplied_path).is_file():
            print(f"[ERROR] {label} file not found: {supplied_path}")
            return 2

    multiwfn = args.multiwfn_bin or os.environ.get("MULTIWFN_BIN", "") or str(profile_values.get("multiwfn_bin", ""))
    wsl_user = args.wsl_user or str(profile_values.get("wsl_user", ""))
    if not supplied_pair and not multiwfn and args.fit_method == "multiwfn-resp":
        warnings.append("MULTIWFN_BIN not set; RESP charge fitting requires Multiwfn. Set --multiwfn-bin or $env:MULTIWFN_BIN.")

    for w in warnings:
        print(f"[WARN] {w}")

    if warnings:
        print()

    config = RunConfig(
        run_name=run_name,
        run_root=run_root,
        project_root=project_root,
        raw_protein_heme_pdb=pdb_path,
        ligand_template_sdf=sdf_path,
        supplied_ligand_mol2=supplied_mol2_path,
        supplied_ligand_frcmod=supplied_frcmod_path,
        heme_state=args.heme_state,
        heme_resname=args.heme_resname,
        heme_chain=args.heme_chain or "",
        protein_chain=args.protein_chain or "",
        axial_cys_resid=args.axial_cys_resid,
        trim_transmembrane_ranges=",".join(args.trim_transmembrane_range or []),
        trim_transmembrane_confirmed=args.confirm_transmembrane_trim,
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
        wsl_user=wsl_user,
        amber_sh=amber_sh,
        multiwfn_bin=multiwfn,
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
    if not config.protonation_decision_json:
        manifest = orch.run_until(stop_before_skill_id="cypforge.core3_finalize_protonation")
        if manifest.workflow_status not in {"STOPPED_ON_FAIL", "PAUSED"}:
            manifest.workflow_status = "PAUSED"
            manifest.completed_at = ""
            orch.workflow.save_manifest(manifest)
            print("\nPAUSED: protonation review is required before Core 3 finalization.")
            print(f"  cypforge protonation recommend {args.run_name} --run-root \"{config.run_root}\"")
            print(
                f"  cypforge protonation apply {args.run_name} --run-root \"{config.run_root}\" "
                "--set <CHAIN>:<CURRENT><RESID>=<TARGET>"
            )
            print(f"  cypforge prep-only {args.run_name} --run-root \"{config.run_root}\"")
    else:
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
    if manifest.workflow_status == "PAUSED":
        return 3
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


def _run_root_for(run_name: str, run_root_override: str | None) -> Path:
    if run_root_override:
        return Path(run_root_override)
    profile_values = load_profile().get("values", {})
    runs_dir = str(profile_values.get("runs_dir", "")) or DEFAULT_RUNS_DIR
    return Path(runs_dir) / run_name


def cmd_protonation_recommend(args: argparse.Namespace) -> int:
    run_root = _run_root_for(args.run_name, args.run_root)
    if _load_config(args.run_name, str(run_root)) is None:
        return 1
    report = recommend_protonation_states(
        ligand_mapping_manifest_json=run_root / "13_ligand_mapping_leapin" / "ligand_mapping_leapin_manifest.json",
        original_prepared_pdb=run_root / "01_heme_only" / "prepared_heme_complex.pdb",
        output_dir=run_root / "14_complex_protonation_finalize",
        ph=args.ph,
        evidence_json=args.evidence_json,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_protonation_apply(args: argparse.Namespace) -> int:
    run_root = _run_root_for(args.run_name, args.run_root)
    config = _load_config(args.run_name, str(run_root))
    if config is None:
        return 1
    original_pdb = run_root / "01_heme_only" / "prepared_heme_complex.pdb"
    decision_path = Path(args.decision_json) if args.decision_json else run_root / "protonation_decision.json"
    if args.set_values:
        if args.decision_json:
            raise ValueError("Use either --set or --decision-json, not both.")
        build_protonation_decision_from_selectors(
            original_prepared_pdb=original_pdb,
            selectors=args.set_values,
            output_json=decision_path,
        )
    elif not decision_path.is_file():
        raise FileNotFoundError("Provide at least one --set selector or an existing --decision-json.")

    result = finalize_complex_protonation_mapping(
        ligand_mapping_manifest_json=run_root / "13_ligand_mapping_leapin" / "ligand_mapping_leapin_manifest.json",
        original_prepared_pdb=original_pdb,
        protonation_decision_json=decision_path,
        output_dir=run_root / "14_complex_protonation_finalize",
    )
    config_path = run_root / "run_config.json"
    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    config_data["protonation_decision_json"] = str(decision_path)
    config_path.write_text(json.dumps(config_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_path = run_root / "run_manifest.json"
    if manifest_path.is_file():
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_data["run_config"] = config_data
        manifest_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_docs_sync(args: argparse.Namespace) -> int:
    index = LocalDocsIndex(args.database)
    rows = [index.index_file(path, source=args.source, version=args.document_version) for path in args.files]
    print(json.dumps({"database": str(index.database), "documents": rows}, indent=2, ensure_ascii=False))
    return 0


def cmd_docs_query(args: argparse.Namespace) -> int:
    index = LocalDocsIndex(args.database)
    print(json.dumps({"query": args.query, "results": index.query(args.query, args.limit)}, indent=2, ensure_ascii=False))
    return 0


def cmd_profile_set(args: argparse.Namespace) -> int:
    print(json.dumps(update_profile(args.assignments, args.profile), indent=2, ensure_ascii=False))
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    print(json.dumps(load_profile(args.profile), indent=2, ensure_ascii=False))
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    run_root = _run_root_for(args.run_name, args.run_root)
    report = build_run_diagnosis(run_root, args.output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _print_json_result(result: dict, *, success_statuses: set[str] | None = None) -> int:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if success_statuses is None:
        return 0
    return 0 if str(result.get("status", "")).lower() in success_statuses else 2


def cmd_module_heme_prepare(args: argparse.Namespace) -> int:
    if args.heme_state == "CUSTOM":
        missing = [
            opt for opt, value in (
                ("--custom-heme-mol2", args.custom_heme_mol2),
                ("--custom-cyp-mol2", args.custom_cyp_mol2),
                ("--custom-frcmod", args.custom_frcmod),
            ) if not value
        ]
        if missing:
            raise ValueError(f"--heme-state CUSTOM requires: {', '.join(missing)}")
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
    return _print_json_result(result)


def cmd_module_heme_leap(args: argparse.Namespace) -> int:
    result = build_heme_mapping_and_leapin(
        prepared_pdb=Path(args.prepared_pdb),
        prepare_report_json=Path(args.prepare_report_json),
        output_dir=Path(args.output_dir),
        heme_resname=args.heme_resname,
    )
    return _print_json_result(result)


def cmd_module_ligand_prepare(args: argparse.Namespace) -> int:
    if args.blank_ligand_chain:
        args.ligand_chain = ""
    out = Path(args.output_dir)
    supplied_pair = bool(args.supplied_mol2 and args.supplied_frcmod)
    if bool(args.supplied_mol2) != bool(args.supplied_frcmod):
        raise ValueError("--supplied-mol2 and --supplied-frcmod must be provided together.")
    if supplied_pair and not args.complex_pdb:
        raise ValueError("--complex-pdb is required when staging supplied parameters.")
    if not supplied_pair and not args.ligand_pose and not args.complex_pdb:
        raise ValueError("Provide --ligand-pose or --complex-pdb.")

    try:
        if supplied_pair:
            if not args.ligand_template_sdf:
                raise ValueError("--ligand-template-sdf is required when staging supplied parameters.")
            result = stage_supplied_ligand_parameters(
                supplied_mol2=args.supplied_mol2,
                supplied_frcmod=args.supplied_frcmod,
                ligand_template_sdf=args.ligand_template_sdf,
                complex_pdb=args.complex_pdb,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                formal_charge=args.formal_charge,
                output_dir=out,
            )
        elif args.complex_pdb and args.ligand_template_sdf and not args.prepare_only and args.fit_method == "multiwfn-resp":
            result = run_complex_sdf_ligand_multiwfn_resp_parameterization(
                complex_pdb=args.complex_pdb,
                ligand_template_sdf=args.ligand_template_sdf,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                formal_charge=args.formal_charge,
                output_dir=out,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                multiwfn_bin=args.multiwfn_bin,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
                resp_geometry_cleanup=args.resp_geometry_cleanup,
                pre_resp_relax=args.pre_resp_relax,
            )
        elif args.complex_pdb and not args.prepare_only and args.fit_method == "multiwfn-resp":
            result = run_complex_ligand_multiwfn_resp_parameterization(
                complex_pdb=args.complex_pdb,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                formal_charge=args.formal_charge,
                output_dir=out,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                multiwfn_bin=args.multiwfn_bin,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
                resp_geometry_cleanup=args.resp_geometry_cleanup,
            )
        elif args.complex_pdb and args.ligand_template_sdf and args.prepare_only:
            result = prepare_complex_sdf_ligand_resp_inputs(
                complex_pdb=args.complex_pdb,
                ligand_template_sdf=args.ligand_template_sdf,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                formal_charge=args.formal_charge,
                output_dir=out,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
            )
        elif args.complex_pdb and args.prepare_only:
            ligand_pose = str(out / f"{args.ligand_resname}_from_confirmed_complex.pdb")
            extract_ligand_from_complex_pdb(
                complex_pdb=args.complex_pdb,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                output_pdb=ligand_pose,
            )
            result = prepare_gpu4pyscf_molden_job(
                ligand_pose=ligand_pose,
                formal_charge=args.formal_charge,
                output_dir=out,
                resname=args.ligand_resname,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
            )
        elif args.prepare_only:
            if args.fit_method == "multiwfn-resp":
                result = prepare_gpu4pyscf_molden_job(
                    ligand_pose=args.ligand_pose,
                    formal_charge=args.formal_charge,
                    output_dir=out,
                    resname=args.ligand_resname,
                    spin_multiplicity=args.spin,
                    basis=args.basis,
                    use_gpu=not args.cpu_only,
                    require_gpu=args.require_gpu,
                )
            else:
                result = prepare_gpu4pyscf_esp_job(
                    ligand_pose=args.ligand_pose,
                    formal_charge=args.formal_charge,
                    output_dir=out,
                    resname=args.ligand_resname,
                    spin_multiplicity=args.spin,
                    basis=args.basis,
                    points_per_atom=args.points_per_atom,
                    use_gpu=not args.cpu_only,
                    require_gpu=args.require_gpu,
                )
        elif args.fit_method == "multiwfn-resp":
            result = run_gpu4pyscf_multiwfn_resp_parameterization(
                ligand_pose=args.ligand_pose,
                formal_charge=args.formal_charge,
                output_dir=out,
                resname=args.ligand_resname,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                multiwfn_bin=args.multiwfn_bin,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
                resp_geometry_cleanup=args.resp_geometry_cleanup,
            )
        else:
            result = run_gpu4pyscf_esp_parameterization(
                ligand_pose=args.ligand_pose,
                formal_charge=args.formal_charge,
                output_dir=out,
                resname=args.ligand_resname,
                spin_multiplicity=args.spin,
                basis=args.basis,
                points_per_atom=args.points_per_atom,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
            )
    except Exception as exc:
        result = {
            "schema": "cypforge.gpu4pyscf_esp_cli_result.v1",
            "status": "failed",
            "error": str(exc),
            "input_ligand_pose": args.ligand_pose,
            "formal_charge": args.formal_charge,
        }

    pre_resp = result.get("pre_resp_relaxation", {}) if isinstance(result, dict) else {}
    warnings = []
    if isinstance(pre_resp, dict) and str(pre_resp.get("status", "")).lower() in {"warn", "warning"}:
        warnings.append({
            "source": "pre_resp_relaxation",
            "status": "warning",
            "gate": pre_resp.get("gate"),
            "reason": pre_resp.get("reason") or pre_resp.get("error"),
        })
    canonical_status = str(result.get("status", "failed"))
    if canonical_status.lower() in {"success", "prepared", "pass", "passed", "ok"} and warnings:
        canonical_status = "warning"
    canonical_manifest = {
        "schema": "cypforge.ligand_parameterization_gate.v1",
        "status": canonical_status,
        "route": "supplied_reviewed_parameters" if supplied_pair else "qm_esp_charge_fit",
        "qm_esp_resp_executed": bool(result.get("qm_esp_resp_executed", not supplied_pair)),
        "warnings": warnings,
        "source_schema": result.get("schema"),
        "parameter_source": result.get("parameter_source", "calculated" if not supplied_pair else None),
        "mol2": result.get("mol2"),
        "frcmod": result.get("frcmod"),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "ligand_parameterization_gate.json").write_text(
        json.dumps(canonical_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") in {"prepared", "success"} else 2


def cmd_module_ligand_leap(args: argparse.Namespace) -> int:
    if args.blank_ligand_chain:
        args.ligand_chain = ""
    result = build_ligand_mapping_and_leapin(
        complex_pdb=Path(args.complex_pdb),
        prepare_report_json=Path(args.prepare_report_json),
        ligand_mol2=Path(args.ligand_mol2),
        ligand_frcmod=Path(args.ligand_frcmod),
        ligand_resname=args.ligand_resname,
        ligand_chain=args.ligand_chain,
        expected_ligand_charge=args.expected_ligand_charge,
        output_dir=Path(args.output_dir),
        heme_resname=args.heme_resname,
    )
    return _print_json_result(result)


def cmd_module_protonation_finalize(args: argparse.Namespace) -> int:
    result = finalize_complex_protonation_mapping(
        ligand_mapping_manifest_json=Path(args.ligand_mapping_manifest_json),
        original_prepared_pdb=Path(args.original_prepared_pdb),
        protonation_decision_json=Path(args.protonation_decision_json),
        output_dir=Path(args.output_dir),
    )
    return _print_json_result(result)


def cmd_module_solvate_render(args: argparse.Namespace) -> int:
    result = prepare_complex_solvation_ionization(
        protonation_manifest_json=Path(args.protonation_manifest_json),
        output_dir=Path(args.output_dir),
        protein_force_field=args.protein_force_field,
        water_leaprc=args.water_leaprc,
        water_model=args.water_model,
        box_type=args.box_type,
        buffer_a=args.buffer_a,
        neutralizing_anion=args.neutralizing_anion,
    )
    return _print_json_result(result)


def cmd_module_solvate_validate(args: argparse.Namespace) -> int:
    result = validate_solvation_tleap_outputs(
        solvation_manifest_json=args.solvation_manifest_json,
        leap_log=args.leap_log,
        output_json=args.output_json,
    )
    return _print_json_result(result, success_statuses={"success"})


def cmd_module_pre_md_render(args: argparse.Namespace) -> int:
    result = prepare_complex_pre_md_equilibration(
        solvation_manifest_json=Path(args.solvation_manifest_json),
        output_dir=Path(args.output_dir),
        protocol_config_json=Path(args.protocol_config_json) if args.protocol_config_json else None,
        write_default_config=not args.no_write_default_config,
        stages_range=args.stages,
    )
    return _print_json_result(result)


def cmd_module_pre_md_validate(args: argparse.Namespace) -> int:
    result = validate_complex_pre_md_run(
        pre_md_manifest_json=args.pre_md_manifest_json,
        output_json=args.output_json,
    )
    return _print_json_result(result, success_statuses={"success"})


def cmd_module_global_audit(args: argparse.Namespace) -> int:
    result = run_complex_global_audit(
        ligand_mapping_manifest_json=args.ligand_mapping_manifest_json,
        protonation_manifest_json=args.protonation_manifest_json,
        solvation_manifest_json=args.solvation_manifest_json,
        pre_md_manifest_json=args.pre_md_manifest_json,
        pre_md_run_validation_json=args.pre_md_run_validation_json,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") != "FAIL" else 2


def _load_config(run_name: str, run_root_override: str | None) -> RunConfig | None:
    """Load RunConfig from an existing run's run_config.json."""
    run_root = str(_run_root_for(run_name, run_root_override))
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


#  Argument parser

def _build_parser(show_advanced: bool = False) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cypforge",
        description="CYPForge Outer Shell: automated CYP450 Amber MD preprocessing workflow",
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
        "--help-advanced", action="store_true", dest="show_advanced_help",
        help="Use 'cypforge init --help-advanced' to show all initialization options",
    )
    parser.add_argument(
        "--version", "-V", action="version",
        version=f"cypforge v{VERSION}  (CYPForge {VERSION})",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser(
        "init",
        help="Initialize a new CYPForge run",
        description="Create a run directory with configuration and a fresh workflow manifest. "
                    "All 10 pipeline modules start in PENDING state.",
        epilog="After init, use 'prep-only' for the no-MD preparation route or 'status' to inspect.",
    )
    if show_advanced:
        p_init.add_argument(
            "--help-advanced",
            action="help",
            help="Show basic and advanced initialization options and exit",
        )
    basic = p_init.add_argument_group("Basic options")
    advanced = p_init.add_argument_group("Advanced options")
    advanced_help = (lambda text: text if show_advanced else argparse.SUPPRESS)
    basic.add_argument("run_name", help=f"Unique name for this run (default base: {DEFAULT_RUNS_DIR})")
    basic.add_argument("--pdb", help="[REQUIRED for Core 1] Input protein+heme PDB file")
    basic.add_argument("--sdf", help="[REQUIRED for Core 2] Input ligand template SDF file")
    basic.add_argument("--heme-state", default="IC6", choices=("IC6", "DIOXY", "CPDI", "CUSTOM"),
                        help="Heme electronic state (default: IC6)")
    advanced.add_argument("--run-root", help=advanced_help(f"Override default run root (default base: {DEFAULT_RUNS_DIR})"))
    advanced.add_argument("--project-root", help=advanced_help("Override the auto-detected project root"))
    advanced.add_argument("--heme-resname", default="HEM", help=advanced_help("Heme residue name in PDB (default: HEM)"))
    advanced.add_argument("--heme-chain", default="", help=advanced_help("Heme chain ID in PDB"))
    advanced.add_argument("--protein-chain", default="", help=advanced_help("Protein chain ID in PDB"))
    advanced.add_argument("--axial-cys-resid", type=int, help=advanced_help("Residue ID of axial cysteine"))
    advanced.add_argument("--trim-transmembrane-range", action="append", default=None, metavar="CHAIN:START-END", help=advanced_help("Remove explicit protein residue range before Core 1; may be repeated or comma-separated"))
    advanced.add_argument("--confirm-transmembrane-trim", action="store_true", help=advanced_help("Required with --trim-transmembrane-range; confirms human-reviewed deletion ranges"))
    advanced.add_argument("--ligand-resname", required=True, help=advanced_help("Ligand residue name in the input complex, e.g. LIG, COU, 8MO, NCT"))
    advanced.add_argument("--supplied-ligand-mol2", help=advanced_help("Reviewed charged ligand MOL2; requires --supplied-ligand-frcmod and skips QM/RESP"))
    advanced.add_argument("--supplied-ligand-frcmod", help=advanced_help("Matching reviewed ligand frcmod; requires --supplied-ligand-mol2"))
    advanced.add_argument("--ligand-chain", default="", help=advanced_help("Ligand chain ID (default: blank)"))
    advanced.add_argument("--blank-ligand-chain", action="store_true", help=advanced_help("Select a ligand with a blank PDB chain ID"))
    advanced.add_argument("--formal-charge", type=int, default=0, help=advanced_help("Ligand formal charge (default: 0)"))
    advanced.add_argument("--spin", type=int, default=1, help=advanced_help("Ligand spin multiplicity (default: 1)"))
    advanced.add_argument("--basis", default="6-31G*", help=advanced_help("QM basis set for RESP (default: 6-31G*)"))
    advanced.add_argument("--points-per-atom", type=int, default=8, help=advanced_help("ESP grid points per atom (default: 8)"))
    advanced.add_argument("--fit-method", default="multiwfn-resp", choices=("multiwfn-resp", "esp-lsq"), help=advanced_help("Charge fitting method (default: multiwfn-resp)"))
    advanced.add_argument("--pre-resp-relax", default="pbe-h-only", help=advanced_help("Pre-RESP geometry relaxation mode (default: pbe-h-only)"))
    advanced.add_argument("--protonation-decision-json", help=advanced_help("Path to the user-approved protonation decision JSON"))
    advanced.add_argument("--protein-force-field", default="ff19SB", choices=("ff14SB", "ff19SB"), help=advanced_help("Protein force field (default: ff19SB)"))
    advanced.add_argument("--water-leaprc", default="leaprc.water.tip3p", help=advanced_help("Water LEaP rc file"))
    advanced.add_argument("--water-model", default="TIP3PBOX", help=advanced_help("Water model (default: TIP3PBOX)"))
    advanced.add_argument("--box-type", default="oct", choices=("oct", "box"), help=advanced_help("Solvent box type (default: oct)"))
    advanced.add_argument("--buffer-a", type=float, default=10.0, help=advanced_help("Solvent buffer distance in A (default: 10.0)"))
    advanced.add_argument("--neutralizing-anion", default="Cl-", help=advanced_help("Neutralizing ion (default: Cl-)"))
    advanced.add_argument("--wsl-user", default=None, help=advanced_help("WSL username for Amber commands"))
    advanced.add_argument("--amber-sh", default="", help=advanced_help("Path to amber.sh or set AMBER_SH"))
    advanced.add_argument("--multiwfn-bin", default="", help=advanced_help("Path to Multiwfn or set MULTIWFN_BIN"))
    advanced.add_argument("--auto-accept-warn", action="store_true", help=advanced_help("Auto-accept WARN gates"))
    advanced.add_argument("--max-retries", type=int, default=0, help=advanced_help("Max retries on module failure (default: 0)"))

    # run
    p_run = sub.add_parser(
        "run",
        help="Execute the full pipeline",
        description="Run all pending modules in order. If a run_manifest.json exists, "
                    "automatically resumes from the checkpoint. Stops on FAIL or pauses on WARN "
                    "(unless --auto-accept-warn was set at init).",
    )
    p_run.add_argument("run_name", help="Name of the run to execute")
    p_run.add_argument("--run-root", help="Override run root directory")

    # prep-only
    p_prep = sub.add_parser(
        "prep-only",
        help="Run through pre-MD input rendering without launching MD",
        description="Execute pending preprocessing modules through cypforge.core3_render_pre_md, "
                    "then stop before cypforge.core3_run_pre_md. This generates and audits "
                    "pre-MD input files but does not call pmemd.cuda, pmemd, or sander.",
    )
    p_prep.add_argument("run_name", help="Name of the run to execute")
    p_prep.add_argument("--run-root", help="Override run root directory")

    # resume
    p_resume = sub.add_parser(
        "resume",
        help="Resume a paused or failed run",
        description="Continue a run that was paused (WARN gate awaiting review) or stopped (FAIL gate). "
                    "Review and fix the failed module before resuming. Re-runs the failed module "
                    "and continues downstream.",
    )
    p_resume.add_argument("run_name", help="Name of the run to resume")
    p_resume.add_argument("--run-root", help="Override run root directory")

    # status
    p_status = sub.add_parser(
        "status",
        help="Show workflow status table",
        description="Display a table of all 10 pipeline modules with their current status "
                    "(PENDING / RUNNING / PASS / WARN / FAIL) and gate results. "
                    "An arrow marks the current or blocking module.",
    )
    p_status.add_argument("run_name", help="Name of the run to inspect")
    p_status.add_argument("--run-root", help="Override run root directory")

    # context
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

    p_prot = sub.add_parser("protonation", help="Recommend or apply reviewed protonation states")
    prot_sub = p_prot.add_subparsers(dest="protonation_command", required=True)
    p_rec = prot_sub.add_parser("recommend", help="Write a non-mutating protonation review list")
    p_rec.add_argument("run_name")
    p_rec.add_argument("--run-root")
    p_rec.add_argument("--ph", type=float, default=7.4)
    p_rec.add_argument("--evidence-json", help="Optional reviewed pKa/H++ recommendation records")
    p_apply = prot_sub.add_parser("apply", help="Apply only user-confirmed residue-state selectors")
    p_apply.add_argument("run_name")
    p_apply.add_argument("--run-root")
    p_apply.add_argument("--set", action="append", dest="set_values", default=[], metavar="A:GLU419=GLH")
    p_apply.add_argument("--decision-json")

    p_docs = sub.add_parser("docs", help="Index or query local software manuals")
    docs_sub = p_docs.add_subparsers(dest="docs_command", required=True)
    p_sync = docs_sub.add_parser("sync", help="Index user-local manual files")
    p_sync.add_argument("files", nargs="+")
    p_sync.add_argument(
        "--source",
        required=True,
        choices=("amber", "ambertools", "pyscf", "gpu4pyscf", "multiwfn", "cypforge", "other"),
    )
    p_sync.add_argument("--document-version", default="")
    p_sync.add_argument("--database")
    p_query = docs_sub.add_parser("query", help="Search the local FTS5 manual index")
    p_query.add_argument("query")
    p_query.add_argument("--limit", type=int, default=5)
    p_query.add_argument("--database")

    p_profile = sub.add_parser("profile", help="Store user-approved local tool paths")
    profile_sub = p_profile.add_subparsers(dest="profile_command", required=True)
    p_profile_set = profile_sub.add_parser("set")
    p_profile_set.add_argument("assignments", nargs="+")
    p_profile_set.add_argument("--profile")
    p_profile_show = profile_sub.add_parser("show")
    p_profile_show.add_argument("--profile")

    p_diagnose = sub.add_parser("diagnose", help="Export a redacted run and failure summary")
    p_diagnose.add_argument("run_name")
    p_diagnose.add_argument("--run-root")
    p_diagnose.add_argument("--output")

    p_module = sub.add_parser(
        "module",
        help="Run a single CYPForge module through the standard CLI",
        description=(
            "Developer and reproducibility interface for one Core/gate operation. "
            "These commands wrap the same APIs used by the Outer Shell, so user-facing "
            "workflows can call cypforge consistently through the installed entry point."
        ),
    )
    module_sub = p_module.add_subparsers(dest="module_command", required=True)

    p_heme = module_sub.add_parser("heme", help="Core 1 heme/CYM operations")
    heme_sub = p_heme.add_subparsers(dest="heme_command", required=True)
    p_heme_prepare = heme_sub.add_parser("prepare", help="Prepare protein+heme/CYM coordinates")
    p_heme_prepare.add_argument("pdb")
    p_heme_prepare.add_argument("--heme-state", required=True, choices=("IC6", "DIOXY", "CPDI", "CUSTOM"))
    p_heme_prepare.add_argument("--output-dir", required=True)
    p_heme_prepare.add_argument("--heme-resname", default="HEM")
    p_heme_prepare.add_argument("--heme-chain", default=None)
    p_heme_prepare.add_argument("--protein-chain", default=None)
    p_heme_prepare.add_argument("--axial-cys-resid", type=int, default=None)
    p_heme_prepare.add_argument("--custom-heme-mol2", default=None)
    p_heme_prepare.add_argument("--custom-cyp-mol2", default=None)
    p_heme_prepare.add_argument("--custom-frcmod", default=None)
    p_heme_prepare.add_argument("--custom-state-label", default=None)
    p_heme_prepare.add_argument("--trim-transmembrane-range", action="append", default=None, metavar="CHAIN:START-END")
    p_heme_prepare.add_argument("--confirm-transmembrane-trim", action="store_true")
    p_heme_leap = heme_sub.add_parser("leap", help="Build Core 1 heme/CYM LEaP input")
    p_heme_leap.add_argument("--prepared-pdb", required=True)
    p_heme_leap.add_argument("--prepare-report-json", required=True)
    p_heme_leap.add_argument("--output-dir", required=True)
    p_heme_leap.add_argument("--heme-resname", default="HEM")

    p_ligand = module_sub.add_parser("ligand", help="Core 2 ligand operations")
    ligand_sub = p_ligand.add_subparsers(dest="ligand_command", required=True)
    p_ligand_prepare = ligand_sub.add_parser("prepare", help="Prepare or stage ligand parameters")
    p_ligand_prepare.add_argument("--ligand-pose")
    p_ligand_prepare.add_argument("--complex-pdb")
    p_ligand_prepare.add_argument("--ligand-template-sdf")
    p_ligand_prepare.add_argument("--supplied-mol2")
    p_ligand_prepare.add_argument("--supplied-frcmod")
    p_ligand_prepare.add_argument("--ligand-resname", default="LIG")
    p_ligand_prepare.add_argument("--ligand-chain", default="")
    p_ligand_prepare.add_argument("--blank-ligand-chain", action="store_true")
    p_ligand_prepare.add_argument("--formal-charge", type=int, required=True)
    p_ligand_prepare.add_argument("--spin", type=int, default=1)
    p_ligand_prepare.add_argument("--basis", default="6-31g*")
    p_ligand_prepare.add_argument("--points-per-atom", type=int, default=24)
    p_ligand_prepare.add_argument("--output-dir", required=True)
    p_ligand_prepare.add_argument("--fit-method", choices=["multiwfn-resp", "esp-lsq"], default="multiwfn-resp")
    p_ligand_prepare.add_argument("--multiwfn-bin", default=None)
    p_ligand_prepare.add_argument("--amber-sh", default=None)
    p_ligand_prepare.add_argument("--prepare-only", action="store_true")
    p_ligand_prepare.add_argument("--cpu-only", action="store_true")
    p_ligand_prepare.add_argument("--require-gpu", action="store_true")
    p_ligand_prepare.add_argument("--no-parmchk2", action="store_true")
    p_ligand_prepare.add_argument("--resp-geometry-cleanup", choices=["h-only", "none"], default="none")
    p_ligand_prepare.add_argument("--pre-resp-relax", choices=["pbe-h-only", "none"], default="pbe-h-only")
    p_ligand_leap = ligand_sub.add_parser("leap", help="Build Core 2 ligand LEaP input")
    p_ligand_leap.add_argument("--complex-pdb", required=True)
    p_ligand_leap.add_argument("--prepare-report-json", required=True)
    p_ligand_leap.add_argument("--ligand-mol2", required=True)
    p_ligand_leap.add_argument("--ligand-frcmod", required=True)
    p_ligand_leap.add_argument("--ligand-resname", required=True)
    p_ligand_leap.add_argument("--ligand-chain", default="")
    p_ligand_leap.add_argument("--blank-ligand-chain", action="store_true")
    p_ligand_leap.add_argument("--expected-ligand-charge", type=int)
    p_ligand_leap.add_argument("--output-dir", required=True)
    p_ligand_leap.add_argument("--heme-resname", default="HEM")

    p_module_prot = module_sub.add_parser("protonation", help="Core 3 protonation operations")
    prot_module_sub = p_module_prot.add_subparsers(dest="module_protonation_command", required=True)
    p_prot_finalize = prot_module_sub.add_parser("finalize", help="Apply reviewed protonation decision JSON")
    p_prot_finalize.add_argument("--ligand-mapping-manifest-json", required=True)
    p_prot_finalize.add_argument("--original-prepared-pdb", required=True)
    p_prot_finalize.add_argument("--protonation-decision-json", required=True)
    p_prot_finalize.add_argument("--output-dir", required=True)

    p_solvate = module_sub.add_parser("solvate", help="Core 3 solvation operations")
    solvate_sub = p_solvate.add_subparsers(dest="solvate_command", required=True)
    p_solvate_render = solvate_sub.add_parser("render", help="Render solvation/ionization LEaP input")
    p_solvate_render.add_argument("--protonation-manifest-json", required=True)
    p_solvate_render.add_argument("--output-dir", required=True)
    p_solvate_render.add_argument("--protein-force-field", choices=["ff14SB", "ff19SB"], default="ff19SB")
    p_solvate_render.add_argument("--water-leaprc", default="leaprc.water.tip3p")
    p_solvate_render.add_argument("--water-model", default="TIP3PBOX")
    p_solvate_render.add_argument("--box-type", choices=["oct", "box"], default="oct")
    p_solvate_render.add_argument("--buffer-a", type=float, default=10.0)
    p_solvate_render.add_argument("--neutralizing-anion", default="Cl-")
    p_solvate_validate = solvate_sub.add_parser("validate", help="Validate solvation LEaP outputs")
    p_solvate_validate.add_argument("--solvation-manifest-json", required=True)
    p_solvate_validate.add_argument("--leap-log", default=None)
    p_solvate_validate.add_argument("--output-json", default=None)

    p_pre_md = module_sub.add_parser("pre-md", help="Core 3 pre-MD operations")
    pre_md_sub = p_pre_md.add_subparsers(dest="pre_md_command", required=True)
    p_pre_md_render = pre_md_sub.add_parser("render", help="Render staged Amber pre-MD inputs")
    p_pre_md_render.add_argument("--solvation-manifest-json", required=True)
    p_pre_md_render.add_argument("--output-dir", required=True)
    p_pre_md_render.add_argument("--protocol-config-json")
    p_pre_md_render.add_argument("--no-write-default-config", action="store_true")
    p_pre_md_render.add_argument("--stages", default="all", choices=("all", "1-8", "9"))
    p_pre_md_validate = pre_md_sub.add_parser("validate", help="Validate pre-MD stage outputs")
    p_pre_md_validate.add_argument("--pre-md-manifest-json", required=True)
    p_pre_md_validate.add_argument("--output-json", default=None)

    p_global_audit = module_sub.add_parser("global-audit", help="Run global CYP450 audit gates")
    p_global_audit.add_argument("--ligand-mapping-manifest-json", required=True)
    p_global_audit.add_argument("--protonation-manifest-json", required=True)
    p_global_audit.add_argument("--solvation-manifest-json", required=True)
    p_global_audit.add_argument("--pre-md-manifest-json", required=True)
    p_global_audit.add_argument("--pre-md-run-validation-json", required=True)
    p_global_audit.add_argument("--output-dir", required=True)

    return parser


#  Entry point

def main() -> int:
    show_advanced = "--help-advanced" in sys.argv
    parser = _build_parser(show_advanced=show_advanced)
    args = parser.parse_args()

    # Show banner on every command except 'context' (which produces pure JSON).
    # Also show banner before help text.
    if args.command != "context":
        _print_banner()

    if args.show_help or args.show_advanced_help:
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
    elif args.command == "protonation" and args.protonation_command == "recommend":
        return cmd_protonation_recommend(args)
    elif args.command == "protonation" and args.protonation_command == "apply":
        return cmd_protonation_apply(args)
    elif args.command == "docs" and args.docs_command == "sync":
        return cmd_docs_sync(args)
    elif args.command == "docs" and args.docs_command == "query":
        return cmd_docs_query(args)
    elif args.command == "profile" and args.profile_command == "set":
        return cmd_profile_set(args)
    elif args.command == "profile" and args.profile_command == "show":
        return cmd_profile_show(args)
    elif args.command == "diagnose":
        return cmd_diagnose(args)
    elif args.command == "module" and args.module_command == "heme" and args.heme_command == "prepare":
        return cmd_module_heme_prepare(args)
    elif args.command == "module" and args.module_command == "heme" and args.heme_command == "leap":
        return cmd_module_heme_leap(args)
    elif args.command == "module" and args.module_command == "ligand" and args.ligand_command == "prepare":
        return cmd_module_ligand_prepare(args)
    elif args.command == "module" and args.module_command == "ligand" and args.ligand_command == "leap":
        return cmd_module_ligand_leap(args)
    elif args.command == "module" and args.module_command == "protonation" and args.module_protonation_command == "finalize":
        return cmd_module_protonation_finalize(args)
    elif args.command == "module" and args.module_command == "solvate" and args.solvate_command == "render":
        return cmd_module_solvate_render(args)
    elif args.command == "module" and args.module_command == "solvate" and args.solvate_command == "validate":
        return cmd_module_solvate_validate(args)
    elif args.command == "module" and args.module_command == "pre-md" and args.pre_md_command == "render":
        return cmd_module_pre_md_render(args)
    elif args.command == "module" and args.module_command == "pre-md" and args.pre_md_command == "validate":
        return cmd_module_pre_md_validate(args)
    elif args.command == "module" and args.module_command == "global-audit":
        return cmd_module_global_audit(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
