"""Tests for the CYPForge Outer Shell orchestrator."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cypforge_core import cli as core_cli
from cypforge_core import (
    build_protonation_decision_from_selectors,
    finalize_complex_protonation_mapping,
    recommend_protonation_states,
)
from cypforge_core.cli import _build_parser
from cypforge_core.local_knowledge import LocalDocsIndex, build_run_diagnosis, update_profile
from cypforge_core.ligand_gpu4pyscf_esp import stage_supplied_ligand_parameters
from cypforge_core.orchestrator import (
    RunConfig,
    RunManifest,
    StepDef,
    ModuleDef,
    StepRecord,
    ModuleRecord,
    GateResult,
    build_module_definitions,
    get_module_by_index,
    get_module_by_skill_id,
    WorkflowManager,
    GateChecker,
    build_agent_context,
    CYPForgeOrchestrator,
)
from cypforge_core.orchestrator.models import ModuleRecord
from cypforge_core.orchestrator.runner import ModuleRunner, _format_cmd
from cypforge_core.complex_pre_md_equilibration import validate_complex_pre_md_run
from cypforge_core.complex_pre_md_equilibration import _fatal_keyword_count, _render_run_script
import cypforge_core.complex_global_audit as global_audit


FAKE_PROJECT_ROOT = str(Path("/tmp/cypforge_proj"))
FAKE_RUN_ROOT = str(Path("/tmp/cypforge_run"))


# ── models ───────────────────────────────────────────────────────────────────

def test_build_module_definitions_count():
    modules = build_module_definitions()
    assert len(modules) == 10


def test_build_module_definitions_ordered():
    modules = build_module_definitions()
    for i, mod in enumerate(modules):
        assert mod.index == i


def test_module_definitions_have_all_required_fields():
    modules = build_module_definitions()
    for mod in modules:
        assert mod.skill_id.startswith("cypforge.")
        assert mod.skill_file.endswith(".md")
        assert mod.description
        assert isinstance(mod.steps, list)
        assert isinstance(mod.output_dir_rel, str)


def test_get_module_by_index():
    m = get_module_by_index(0)
    assert m is not None
    assert m.skill_id == "cypforge.environment_check"

    m = get_module_by_index(9)
    assert m is not None
    assert m.skill_id == "cypforge.production_readiness_check"

    assert get_module_by_index(99) is None


def test_get_module_by_skill_id():
    m = get_module_by_skill_id("cypforge.global_audit")
    assert m is not None
    assert m.index == 7

    assert get_module_by_skill_id("cypforge.nonexistent") is None


def test_each_module_has_at_least_one_step():
    modules = build_module_definitions()
    for mod in modules:
        assert len(mod.steps) >= 1, f"{mod.skill_id} has no steps"


def test_core1_steps_use_valid_script_names():
    m = get_module_by_skill_id("cypforge.core1_prepare_heme_cym")
    step_names = {s.name for s in m.steps}
    assert "heme_only_prepare" in step_names
    assert "heme_mapping_leapin" in step_names


def test_core2_steps_use_valid_script_names():
    m = get_module_by_skill_id("cypforge.core2_prepare_ligand_resp_gaff2")
    step_names = {s.name for s in m.steps}
    assert "ligand_gpu4pyscf_esp" in step_names
    assert "ligand_mapping_leapin" in step_names


def test_environment_check_has_6_tool_probes():
    m = get_module_by_skill_id("cypforge.environment_check")
    # 6 tool checks: tleap, pmemd.cuda, cpptraj, antechamber, parmchk2 + python import
    assert len(m.steps) >= 3
    kinds = {s.kind for s in m.steps}
    assert "python_script" in kinds
    assert "wsl_command" in kinds


def test_input_dependency_chain_is_consistent():
    """Verify that each module's required_input_manifests were produced by earlier modules."""
    modules = build_module_definitions()
    all_outputs: set[str] = set()
    for mod in modules:
        for req in mod.required_input_manifests:
            # Template placeholders like {run_root} should not be in the dependency names
            # The actual manifest paths used in required_input_manifests should be relative
            assert req in all_outputs or not req, (
                f"{mod.skill_id} requires '{req}' but it was not produced by any earlier module"
            )
        for out in mod.output_manifests:
            all_outputs.add(out)


# ── RunConfig ────────────────────────────────────────────────────────────────

def test_run_config_defaults():
    cfg = RunConfig(
        run_name="test",
        run_root=FAKE_RUN_ROOT,
        project_root=FAKE_PROJECT_ROOT,
    )
    assert cfg.heme_state == "IC6"
    assert cfg.heme_resname == "HEM"
    assert cfg.ligand_resname == ""
    assert cfg.formal_charge == 0
    assert cfg.auto_accept_warn is False
    assert cfg.max_retries == 0


def test_run_config_python_path():
    cfg = RunConfig(
        run_name="test",
        run_root=FAKE_RUN_ROOT,
        project_root=FAKE_PROJECT_ROOT,
    )
    assert cfg.python_path == str(Path(FAKE_PROJECT_ROOT) / "src")


def test_format_cmd_blank_ligand_chain_uses_explicit_flag():
    command = _format_cmd(
        "python scripts/ligand_mapping_leapin.py"
        " --ligand-resname {ligand_resname}"
        " --ligand-chain {ligand_chain}"
        " --heme-chain {heme_chain}",
        {"ligand_resname": "NCT", "ligand_chain": "", "heme_chain": ""},
    )

    assert "--ligand-resname NCT" in command
    assert "--blank-ligand-chain" in command
    assert "--ligand-chain" not in command
    assert "--heme-chain" not in command


def test_cypforge_run_init_blank_ligand_chain_persists(tmp_path):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "cypforge_run.py"
    spec = importlib.util.spec_from_file_location("cypforge_run_cli", script_path)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    pdb = tmp_path / "complex.pdb"
    sdf = tmp_path / "ligand.sdf"
    pdb.write_text("END\n", encoding="utf-8")
    sdf.write_text("ligand\n", encoding="utf-8")

    parser = cli._build_parser()
    args = parser.parse_args([
        "init",
        "blank_chain",
        "--run-root",
        str(tmp_path / "run"),
        "--project-root",
        str(Path(__file__).resolve().parents[1]),
        "--pdb",
        str(pdb),
        "--sdf",
        str(sdf),
        "--ligand-resname",
        "LIG",
        "--blank-ligand-chain",
        "--amber-sh",
        "/tmp/amber.sh",
        "--multiwfn-bin",
        "/tmp/multiwfn_noGUI",
        "--auto-accept-warn",
    ])

    assert cli.cmd_init(args) == 0
    config = json.loads((tmp_path / "run" / "run_config.json").read_text(encoding="utf-8"))
    assert config["ligand_chain"] == ""


def test_workflow_persists_supplied_parameter_route(tmp_path):
    run_root = tmp_path / "run"
    config = RunConfig(
        run_name="supplied",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
        supplied_ligand_mol2="reviewed.mol2",
        supplied_ligand_frcmod="reviewed.frcmod",
    )
    WorkflowManager(config).init_run()
    persisted = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
    assert persisted["supplied_ligand_mol2"] == "reviewed.mol2"
    assert persisted["supplied_ligand_frcmod"] == "reviewed.frcmod"
    loaded = core_cli._load_config("supplied", str(run_root))
    assert loaded is not None
    assert loaded.supplied_ligand_mol2 == "reviewed.mol2"
    assert loaded.supplied_ligand_frcmod == "reviewed.frcmod"


def test_init_basic_parser_keeps_advanced_arguments_compatible():
    parser = _build_parser(show_advanced=False)
    args = parser.parse_args([
        "init", "compat", "--pdb", "complex.pdb", "--sdf", "ligand.sdf",
        "--heme-state", "CPDI", "--ligand-resname", "LIG", "--formal-charge", "-1",
    ])
    assert args.ligand_resname == "LIG"
    assert args.formal_charge == -1


def test_init_requires_ligand_resname(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    (project_root / "src" / "cypforge_core").mkdir(parents=True)
    pdb = tmp_path / "complex.pdb"
    sdf = tmp_path / "ligand.sdf"
    pdb.write_text("END\n", encoding="utf-8")
    sdf.write_text("ligand\n", encoding="utf-8")
    monkeypatch.setattr(core_cli, "load_profile", lambda: {"values": {}})

    with pytest.raises(SystemExit):
        _build_parser(show_advanced=True).parse_args([
            "init",
            "missing_ligand",
            "--run-root",
            str(tmp_path / "run"),
            "--project-root",
            str(project_root),
            "--pdb",
            str(pdb),
            "--sdf",
            str(sdf),
            "--amber-sh",
            "/opt/amber25/amber.sh",
        ])


def test_init_short_form_matches_explicit_default_options():
    parser = _build_parser(show_advanced=False)
    short = parser.parse_args([
        "init", "same", "--pdb", "complex.pdb", "--sdf", "ligand.sdf",
        "--heme-state", "CPDI", "--ligand-resname", "NCT",
    ])
    explicit = parser.parse_args([
        "init", "same", "--pdb", "complex.pdb", "--sdf", "ligand.sdf",
        "--heme-state", "CPDI", "--heme-resname", "HEM",
        "--ligand-resname", "NCT", "--formal-charge", "0", "--spin", "1",
        "--basis", "6-31G*", "--points-per-atom", "8",
        "--fit-method", "multiwfn-resp", "--pre-resp-relax", "pbe-h-only",
        "--protein-force-field", "ff19SB", "--water-leaprc", "leaprc.water.tip3p",
        "--water-model", "TIP3PBOX", "--box-type", "oct", "--buffer-a", "10.0",
        "--neutralizing-anion", "Cl-", "--max-retries", "0",
    ])
    ignored = {"func", "show_advanced_help"}
    assert {k: v for k, v in vars(short).items() if k not in ignored} == {
        k: v for k, v in vars(explicit).items() if k not in ignored
    }


def test_supplied_ligand_parameters_skip_qm_and_preserve_downstream_names(tmp_path):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text(
        "ligand\n  test\n\n  2  1  0  0  0  0  0  0  0  0  1 V2000\n"
        "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    1.0000    0.0000    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "  1  2  1  0  0  0  0\nM  END\n$$$$\n",
        encoding="utf-8",
    )
    mol2 = tmp_path / "reviewed.mol2"
    mol2.write_text(
        "@<TRIPOS>MOLECULE\nNCT\n2 1 1 0 0\nSMALL\nUSER_CHARGES\n\n"
        "@<TRIPOS>ATOM\n"
        "      1 C1       0.0000    0.0000    0.0000 c3       1 NCT      -0.100000\n"
        "      2 H1       1.0000    0.0000    0.0000 h1       1 NCT       0.100000\n"
        "@<TRIPOS>BOND\n     1    1    2 1\n"
        "@<TRIPOS>SUBSTRUCTURE\n     1 NCT         1 TEMP              0 ****  ****    0 ROOT\n",
        encoding="utf-8",
    )
    frcmod = tmp_path / "reviewed.frcmod"
    frcmod.write_text("MASS\nc3 12.010\nh1 1.008\n\nBOND\nc3-h1 340.0 1.09\n", encoding="utf-8")
    complex_pdb = tmp_path / "complex.pdb"
    complex_pdb.write_text(
        "HETATM    1  C1  NCT A   1       0.000   0.000   0.000  1.00 20.00           C\n"
        "HETATM    2  H1  NCT A   1       1.000   0.000   0.000  1.00 20.00           H\n"
        "END\n",
        encoding="utf-8",
    )

    result = stage_supplied_ligand_parameters(
        supplied_mol2=mol2,
        supplied_frcmod=frcmod,
        ligand_template_sdf=sdf,
        complex_pdb=complex_pdb,
        ligand_resname="NCT",
        ligand_chain="A",
        formal_charge=0,
        output_dir=tmp_path / "out",
    )

    assert result["status"] == "success"
    assert result["qm_esp_resp_executed"] is False
    assert Path(result["mol2"]).name == "NCT_multiwfn_resp.mol2"
    assert Path(result["frcmod"]).name == "NCT.frcmod"


def test_supplied_ligand_parameters_must_be_paired_in_init(tmp_path):
    parser = _build_parser(show_advanced=False)
    args = parser.parse_args([
        "init", "bad_pair", "--pdb", "complex.pdb", "--sdf", "ligand.sdf",
        "--ligand-resname", "LIG", "--supplied-ligand-mol2", str(tmp_path / "ligand.mol2"),
    ])
    assert args.supplied_ligand_mol2
    assert args.supplied_ligand_frcmod is None
    assert core_cli.cmd_init(args) == 2


def test_bundled_4ejj_supplied_parameters_pass_static_contract(tmp_path):
    root = Path(__file__).resolve().parents[1] / "benchmark" / "4EJJ"
    result = stage_supplied_ligand_parameters(
        supplied_mol2=root / "NCT_multiwfn_resp.mol2",
        supplied_frcmod=root / "NCT.frcmod",
        ligand_template_sdf=root / "nicotine.sdf",
        complex_pdb=root / "4EJJ_CPD1_NCT.pdb",
        ligand_resname="NCT",
        ligand_chain="",
        formal_charge=0,
        output_dir=tmp_path / "staged",
    )
    assert result["atom_count"] == 26
    assert result["partial_charge_sum"] == pytest.approx(0.0, abs=1.0e-4)
    assert result["parameter_source"] == "user_supplied_reviewed"
    assert result["complex_pose_check"]["heavy_atom_rmsd_a"] <= 0.05


def test_supplied_ligand_parameters_reject_wrong_complex_pose(tmp_path):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text(
        "ligand\n  test\n\n  2  1  0  0  0  0  0  0  0  0  1 V2000\n"
        "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    1.0000    0.0000    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "  1  2  1  0  0  0  0\nM  END\n$$$$\n",
        encoding="utf-8",
    )
    mol2 = tmp_path / "reviewed.mol2"
    mol2.write_text(
        "@<TRIPOS>MOLECULE\nNCT\n2 1 1 0 0\nSMALL\nUSER_CHARGES\n\n"
        "@<TRIPOS>ATOM\n"
        "1 C1 0.0 0.0 0.0 c3 1 NCT -0.1\n"
        "2 H1 1.0 0.0 0.0 h1 1 NCT 0.1\n"
        "@<TRIPOS>BOND\n1 1 2 1\n@<TRIPOS>SUBSTRUCTURE\n1 NCT 1 TEMP 0 **** **** 0 ROOT\n",
        encoding="utf-8",
    )
    frcmod = tmp_path / "reviewed.frcmod"
    frcmod.write_text("MASS\nc3 12.010\n", encoding="utf-8")
    complex_pdb = tmp_path / "complex.pdb"
    complex_pdb.write_text(
        "HETATM    1  C1  NCT A   1       2.000   0.000   0.000  1.00 20.00           C\n"
        "HETATM    2  H1  NCT A   1       3.000   0.000   0.000  1.00 20.00           H\nEND\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not in the confirmed complex pose"):
        stage_supplied_ligand_parameters(
            supplied_mol2=mol2,
            supplied_frcmod=frcmod,
            ligand_template_sdf=sdf,
            complex_pdb=complex_pdb,
            ligand_resname="NCT",
            ligand_chain="A",
            formal_charge=0,
            output_dir=tmp_path / "out",
        )


def test_core2_command_renders_supplied_parameters_only_when_configured():
    step = get_module_by_skill_id("cypforge.core2_prepare_ligand_resp_gaff2").steps[0]
    base = RunConfig(run_name="base", run_root=FAKE_RUN_ROOT, project_root=FAKE_PROJECT_ROOT)
    base_command = _format_cmd(step.command_template, ModuleRunner(base)._resolve_values())
    assert "--supplied-mol2" not in base_command
    assert "--supplied-frcmod" not in base_command

    supplied = RunConfig(
        run_name="supplied",
        run_root=FAKE_RUN_ROOT,
        project_root=FAKE_PROJECT_ROOT,
        supplied_ligand_mol2="reviewed.mol2",
        supplied_ligand_frcmod="reviewed.frcmod",
    )
    supplied_command = _format_cmd(step.command_template, ModuleRunner(supplied)._resolve_values())
    assert '--supplied-mol2 "reviewed.mol2"' in supplied_command
    assert '--supplied-frcmod "reviewed.frcmod"' in supplied_command


def test_core1_command_preserves_paths_and_trim_ranges_with_spaces():
    step = get_module_by_skill_id("cypforge.core1_prepare_heme_cym").steps[0]
    config = RunConfig(
        run_name="trim",
        run_root="C:/runs with space/trim",
        project_root=FAKE_PROJECT_ROOT,
        raw_protein_heme_pdb="C:/inputs with space/complex.pdb",
        trim_transmembrane_ranges="A:1-35, B:40-50",
        trim_transmembrane_confirmed=True,
    )
    command = _format_cmd(step.command_template, ModuleRunner(config)._resolve_values())
    argv = ModuleRunner._parse_command(command)
    assert argv[argv.index("--output-dir") + 1] == "C:/runs with space/trim\\01_heme_only"
    assert argv[argv.index("--trim-transmembrane-range") + 1] == "A:1-35, B:40-50"
    assert "--confirm-transmembrane-trim" in argv
    assert argv[-1] == "C:/inputs with space/complex.pdb"


def test_config_boolean_strings_parse_strictly():
    cfg = core_cli._dict_to_run_config(
        {
            "run_name": "x",
            "run_root": "C:/runs/x",
            "project_root": "E:/proj",
            "trim_transmembrane_confirmed": "false",
            "auto_accept_warn": "0",
        }
    )
    assert cfg.trim_transmembrane_confirmed is False
    assert cfg.auto_accept_warn is False
    with pytest.raises(ValueError, match="Invalid boolean"):
        core_cli._dict_to_run_config(
            {
                "run_name": "x",
                "run_root": "C:/runs/x",
                "project_root": "E:/proj",
                "trim_transmembrane_confirmed": "maybe",
            }
        )


def test_protonation_selector_requires_chain_name_and_original_residue(tmp_path):
    pdb = tmp_path / "prepared.pdb"
    pdb.write_text(
        "ATOM      1  CA  GLU A 419      10.000  10.000  10.000  1.00 20.00           C\n"
        "ATOM      2  OE1 GLU A 419      11.000  10.000  10.000  1.00 20.00           O\n"
        "END\n",
        encoding="utf-8",
    )
    output = tmp_path / "decision.json"
    decision = build_protonation_decision_from_selectors(
        original_prepared_pdb=pdb,
        selectors=["A:GLU419=GLH"],
        output_json=output,
    )
    assert decision["status"] == "user_confirmed"
    assert decision["recommended_changes"][0]["assembled_resid"] == 1
    assert decision["recommended_changes"][0]["to"] == "GLH"
    with pytest.raises(ValueError, match="does not match"):
        build_protonation_decision_from_selectors(
            original_prepared_pdb=pdb,
            selectors=["B:GLU419=GLH"],
            output_json=output,
        )


def test_protonation_recommendation_is_advisory(tmp_path):
    combined = tmp_path / "combined.pdb"
    combined.write_text(
        "ATOM      1  CA  GLU A   1      10.000  10.000  10.000  1.00 20.00           C\n"
        "ATOM      2  CA  HID A   2      11.000  10.000  10.000  1.00 20.00           C\n"
        "END\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "ligand_mapping_leapin_manifest.json"
    manifest.write_text(json.dumps({"output_files": {"combined_pdb": str(combined)}}), encoding="utf-8")
    report = recommend_protonation_states(
        ligand_mapping_manifest_json=manifest,
        original_prepared_pdb=combined,
        output_dir=tmp_path / "out",
    )
    by_name = {row["current_resname"]: row for row in report["recommendations"]}
    assert by_name["GLU"]["disposition"] == "manual_review"
    assert by_name["GLU"]["recommended_resname"] is None
    assert by_name["HID"]["recommended_resname"] == "HID"
    assert report["status"] == "review_required"


def test_protonation_recommendation_reports_original_residue_identity(tmp_path):
    original = tmp_path / "prepared.pdb"
    original.write_text(
        "ATOM      1  CA  GLU A 419      10.000  10.000  10.000  1.00 20.00           C\nEND\n",
        encoding="utf-8",
    )
    combined = tmp_path / "combined.pdb"
    combined.write_text(
        "ATOM      1  CA  GLU A   1      10.000  10.000  10.000  1.00 20.00           C\nEND\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "ligand_mapping_leapin_manifest.json"
    manifest.write_text(json.dumps({"output_files": {"combined_pdb": str(combined)}}), encoding="utf-8")
    report = recommend_protonation_states(
        ligand_mapping_manifest_json=manifest,
        original_prepared_pdb=original,
        output_dir=tmp_path / "out",
    )
    row = report["recommendations"][0]
    assert row["selector"] == "A:GLU419"
    assert row["assembled_resid"] == 1


def test_protonation_decision_accepts_utf8_bom(tmp_path):
    original = tmp_path / "prepared.pdb"
    original.write_text("ATOM      1  CA  GLU A   1      10.000  10.000  10.000  1.00 20.00           C\nEND\n", encoding="utf-8")
    combined = tmp_path / "combined.pdb"
    combined.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    leapin = tmp_path / "ligand_mapping_leapin.in"
    leapin.write_text("savepdb complex complex_ligand_chainbc.pdb\n", encoding="utf-8")
    manifest = tmp_path / "ligand_mapping_leapin_manifest.json"
    manifest.write_text(
        json.dumps({
            "output_files": {"combined_pdb": str(combined), "leapin": str(leapin)},
            "residues": {},
            "parameter_files": {},
        }),
        encoding="utf-8",
    )
    decision = tmp_path / "decision.json"
    decision.write_text(
        "\ufeff" + json.dumps({"schema": "cypforge.protonation_decision.v1", "recommended_changes": []}),
        encoding="utf-8",
    )
    result = finalize_complex_protonation_mapping(
        ligand_mapping_manifest_json=manifest,
        original_prepared_pdb=original,
        protonation_decision_json=decision,
        output_dir=tmp_path / "out",
    )
    assert result["status"] == "success"


def test_local_docs_fts_profile_and_diagnosis(tmp_path):
    manual = tmp_path / "amber_manual.txt"
    manual.write_text("TLEAP ERROR HANDLING\nUnknown residue names stop topology construction.\n", encoding="utf-8")
    index = LocalDocsIndex(tmp_path / "index.sqlite3")
    indexed = index.index_file(manual, source="amber", version="25")
    assert indexed["status"] == "indexed"
    hits = index.query("unknown residue")
    assert hits and hits[0]["source"] == "amber"

    profile = update_profile(["amber_sh=/opt/amber25/amber.sh"], tmp_path / "profile.json")
    assert profile["values"]["amber_sh"].endswith("amber.sh")
    with pytest.raises(ValueError, match="Unsupported profile key"):
        update_profile(["api_token=secret"], tmp_path / "profile.json")

    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "run_config.json").write_text(json.dumps({"run_name": "test", "project_root": "/private/project"}), encoding="utf-8")
    (run_root / "run_manifest.json").write_text(json.dumps({"workflow_status": "PAUSED", "modules": {}}), encoding="utf-8")
    (run_root / "stage.log").write_text("FATAL unknown residue\n", encoding="utf-8")
    diagnosis = build_run_diagnosis(run_root)
    assert diagnosis["workflow_status"] == "PAUSED"
    assert diagnosis["config_public"]["project_root"] == "project"
    assert diagnosis["failure_signatures"]


def test_init_uses_profile_runs_dir_and_tool_paths(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    (project_root / "src" / "cypforge_core").mkdir(parents=True)
    runs_dir = tmp_path / "profile_runs"
    monkeypatch.setattr(
        core_cli,
        "load_profile",
        lambda: {
            "values": {
                "runs_dir": str(runs_dir),
                "amber_sh": "/opt/amber25/amber.sh",
                "multiwfn_bin": "/opt/Multiwfn",
            }
        },
    )
    args = _build_parser(show_advanced=True).parse_args(
        ["init", "profile_case", "--project-root", str(project_root), "--ligand-resname", "LIG"]
    )
    assert core_cli.cmd_init(args) == 0
    config = json.loads((runs_dir / "profile_case" / "run_config.json").read_text(encoding="utf-8"))
    assert config["run_root"] == str(runs_dir / "profile_case")
    assert config["amber_sh"] == "/opt/amber25/amber.sh"
    assert config["multiwfn_bin"] == "/opt/Multiwfn"
    loaded = core_cli._load_config("profile_case", None)
    assert loaded is not None
    assert loaded.run_root == str(runs_dir / "profile_case")


def test_init_normalizes_relative_input_paths(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    (project_root / "src" / "cypforge_core").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    for name in ("complex.pdb", "ligand.sdf", "reviewed.mol2", "reviewed.frcmod"):
        (work / name).write_text("stub\n", encoding="utf-8")
    monkeypatch.chdir(work)
    monkeypatch.setattr(core_cli, "load_profile", lambda: {"values": {}})

    args = _build_parser(show_advanced=True).parse_args([
        "init",
        "relative_paths",
        "--run-root",
        str(tmp_path / "run"),
        "--project-root",
        str(project_root),
        "--pdb",
        "complex.pdb",
        "--sdf",
        "ligand.sdf",
        "--ligand-resname",
        "LIG",
        "--supplied-ligand-mol2",
        "reviewed.mol2",
        "--supplied-ligand-frcmod",
        "reviewed.frcmod",
        "--amber-sh",
        "/opt/amber25/amber.sh",
    ])

    assert core_cli.cmd_init(args) == 0
    config = json.loads((tmp_path / "run" / "run_config.json").read_text(encoding="utf-8"))
    assert config["raw_protein_heme_pdb"] == str((work / "complex.pdb").resolve())
    assert config["ligand_template_sdf"] == str((work / "ligand.sdf").resolve())
    assert config["supplied_ligand_mol2"] == str((work / "reviewed.mol2").resolve())
    assert config["supplied_ligand_frcmod"] == str((work / "reviewed.frcmod").resolve())


def test_run_diagnosis_redacts_nested_paths_and_secrets(tmp_path):
    run_root = tmp_path / "run"
    run_root.mkdir()
    project_root = tmp_path / "private_project"
    config = {
        "run_name": "test",
        "run_root": str(run_root),
        "project_root": str(project_root),
        "amber_sh": "/home/alice/amber25/amber.sh",
        "supplied_ligand_mol2": "C:/Users/alice/private/reviewed.mol2",
    }
    modules = {
        "core": {
            "command": f"python {project_root}/script.py --token=secret-value",
            "stdout_path": str(run_root / "logs" / "stdout.txt"),
        }
    }
    (run_root / "run_config.json").write_text(json.dumps(config), encoding="utf-8")
    (run_root / "run_manifest.json").write_text(
        json.dumps({"workflow_status": "PAUSED", "modules": modules}),
        encoding="utf-8",
    )
    (run_root / "stage.log").write_text(
        f"FATAL input={project_root}/input.pdb token=secret-value\n",
        encoding="utf-8",
    )
    diagnosis = build_run_diagnosis(run_root)
    serialized = json.dumps(diagnosis)
    assert str(project_root) not in serialized
    assert str(run_root) not in serialized
    assert "secret-value" not in serialized
    assert diagnosis["config_public"]["amber_sh"] == "amber.sh"


def test_run_until_stops_before_pre_md_execution(tmp_path, monkeypatch):
    config = RunConfig(
        run_name="prep_only",
        run_root=str(tmp_path / "run"),
        project_root=FAKE_PROJECT_ROOT,
        auto_accept_warn=True,
    )
    orch = CYPForgeOrchestrator(config)
    orch.init()
    executed: list[str] = []

    def fake_execute_module(self, mod_def, manifest):
        executed.append(mod_def.skill_id)
        record = ModuleRecord(
            skill_id=mod_def.skill_id,
            status="PASS",
            gate_result="PASS",
        )
        self.workflow.update_module_record(manifest, mod_def.skill_id, record)
        return record

    monkeypatch.setattr(CYPForgeOrchestrator, "_execute_module", fake_execute_module)
    manifest = orch.run_until(stop_before_skill_id="cypforge.core3_run_pre_md")

    assert manifest.workflow_status == "COMPLETED"
    assert "cypforge.core3_render_pre_md" in executed
    assert "cypforge.core3_run_pre_md" not in executed
    assert "cypforge.global_audit" not in executed


def test_prep_only_pauses_before_protonation_without_decision(tmp_path, monkeypatch):
    run_root = tmp_path / "run"
    config = RunConfig(
        run_name="needs_review",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
        auto_accept_warn=True,
    )
    CYPForgeOrchestrator(config).init()
    executed: list[str] = []

    def fake_execute_module(self, mod_def, manifest):
        executed.append(mod_def.skill_id)
        record = ModuleRecord(skill_id=mod_def.skill_id, status="PASS", gate_result="PASS")
        self.workflow.update_module_record(manifest, mod_def.skill_id, record)
        return record

    monkeypatch.setattr(CYPForgeOrchestrator, "_execute_module", fake_execute_module)
    exit_code = core_cli.cmd_prep_only(SimpleNamespace(run_name="needs_review", run_root=str(run_root)))
    manifest = json.loads((run_root / "run_manifest.json").read_text(encoding="utf-8"))
    assert exit_code == 3
    assert manifest["workflow_status"] == "PAUSED"
    assert "cypforge.core2_prepare_ligand_resp_gaff2" in executed
    assert "cypforge.core3_finalize_protonation" not in executed


# ── WorkflowManager ──────────────────────────────────────────────────────────

def test_workflow_init_creates_manifest(tmp_path):
    run_root = tmp_path / "test_run"
    config = RunConfig(
        run_name="test_init",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
    )
    wm = WorkflowManager(config)
    manifest = wm.init_run()

    assert run_root.is_dir()
    assert (run_root / "run_config.json").is_file()
    assert (run_root / "run_manifest.json").is_file()

    assert manifest.run_name == "test_init"
    assert manifest.workflow_status == "INITIALIZING"
    assert len(manifest.modules) == 10
    for mod_id in manifest.modules:
        assert manifest.modules[mod_id]["status"] == "PENDING"


def test_workflow_save_and_load_roundtrip(tmp_path):
    run_root = tmp_path / "test_roundtrip"
    config = RunConfig(
        run_name="test_rt",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
    )
    wm = WorkflowManager(config)
    original = wm.init_run()

    # Modify some state
    original.workflow_status = "RUNNING"
    original.modules["cypforge.environment_check"]["status"] = "PASS"
    original.modules["cypforge.environment_check"]["gate_result"] = "PASS"
    wm.save_manifest(original)

    # Reload
    loaded = wm.load_manifest()
    assert loaded is not None
    assert loaded.run_name == "test_rt"
    assert loaded.workflow_status == "RUNNING"
    assert loaded.modules["cypforge.environment_check"]["status"] == "PASS"


def test_find_resume_point_new_run(tmp_path):
    run_root = tmp_path / "test_resume_new"
    config = RunConfig(
        run_name="test_resume",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
    )
    wm = WorkflowManager(config)
    manifest = wm.init_run()

    resume = wm.find_resume_point(manifest)
    assert resume is not None
    assert resume.skill_id == "cypforge.environment_check"


def test_find_resume_point_all_complete(tmp_path):
    run_root = tmp_path / "test_all_done"
    config = RunConfig(
        run_name="test_done",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
    )
    wm = WorkflowManager(config)
    manifest = wm.init_run()

    # Mark all as PASS
    for mod_id in manifest.modules:
        manifest.modules[mod_id]["status"] = "PASS"
    manifest.workflow_status = "COMPLETED"
    wm.save_manifest(manifest)

    resume = wm.find_resume_point(manifest)
    assert resume is None  # nothing to resume


def test_find_resume_point_after_fail(tmp_path):
    run_root = tmp_path / "test_resume_fail"
    config = RunConfig(
        run_name="test_fail_resume",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
    )
    wm = WorkflowManager(config)
    manifest = wm.init_run()

    # Mark first 2 as PASS, 3rd as FAIL
    manifest.modules["cypforge.environment_check"]["status"] = "PASS"
    manifest.modules["cypforge.core1_prepare_heme_cym"]["status"] = "PASS"
    manifest.modules["cypforge.core2_prepare_ligand_resp_gaff2"]["status"] = "FAIL"

    resume = wm.find_resume_point(manifest)
    assert resume is not None
    assert resume.skill_id == "cypforge.core2_prepare_ligand_resp_gaff2"


def test_find_resume_point_warn_no_auto_accept(tmp_path):
    run_root = tmp_path / "test_resume_warn"
    config = RunConfig(
        run_name="test_warn",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
        auto_accept_warn=False,
    )
    wm = WorkflowManager(config)
    manifest = wm.init_run()

    manifest.modules["cypforge.environment_check"]["status"] = "WARN"

    resume = wm.find_resume_point(manifest)
    assert resume is not None
    assert resume.skill_id == "cypforge.environment_check"


def test_find_resume_point_warn_auto_accept(tmp_path):
    run_root = tmp_path / "test_resume_warn_auto"
    config = RunConfig(
        run_name="test_warn_auto",
        run_root=str(run_root),
        project_root=FAKE_PROJECT_ROOT,
        auto_accept_warn=True,
    )
    wm = WorkflowManager(config)
    manifest = wm.init_run()

    manifest.modules["cypforge.environment_check"]["status"] = "WARN"

    resume = wm.find_resume_point(manifest)
    assert resume is not None
    # With auto_accept, WARN is treated as done, so next module
    assert resume.skill_id == "cypforge.core1_prepare_heme_cym"


# ── GateChecker ──────────────────────────────────────────────────────────────

def test_gate_checker_extract_status_pass(tmp_path):
    checker = GateChecker(str(tmp_path))
    assert checker._extract_status({"status": "PASS"}) == "PASS"
    assert checker._extract_status({"status": "success"}) == "PASS"
    assert checker._extract_status({"status": "prepared"}) == "PASS"
    assert checker._extract_status({"status": "passed"}) == "PASS"


def test_gate_checker_extract_status_fail(tmp_path):
    checker = GateChecker(str(tmp_path))
    assert checker._extract_status({"status": "FAIL"}) == "FAIL"
    assert checker._extract_status({"status": "failed"}) == "FAIL"
    assert checker._extract_status({"status": "error"}) == "FAIL"


def test_gate_checker_extract_status_warn(tmp_path):
    checker = GateChecker(str(tmp_path))
    assert checker._extract_status({"status": "WARN"}) == "WARN"
    assert checker._extract_status({"status": "warning"}) == "WARN"


def test_gate_checker_combine_gates(tmp_path):
    checker = GateChecker(str(tmp_path))
    # Empty gate list = misconfiguration → fail closed (see gates.py:_combine).
    assert checker._combine([]) == "FAIL"
    assert checker._combine([
        GateResult(gate_id="1", name="a", status="PASS", detail=""),
    ]) == "PASS"
    assert checker._combine([
        GateResult(gate_id="1", name="a", status="PASS", detail=""),
        GateResult(gate_id="2", name="b", status="WARN", detail=""),
    ]) == "WARN"
    assert checker._combine([
        GateResult(gate_id="1", name="a", status="PASS", detail=""),
        GateResult(gate_id="2", name="b", status="FAIL", detail=""),
    ]) == "FAIL"


def test_gate_checker_missing_manifest(tmp_path):
    checker = GateChecker(str(tmp_path))
    status, gates, summary = checker.check_module_output(
        "test.module", {"missing_manifest": "nonexistent/path.json"}
    )
    assert status == "FAIL"
    assert len(gates) == 1
    assert gates[0].status == "FAIL"
    assert "not found" in gates[0].detail.lower() or "missing" in gates[0].detail.lower()


def test_gate_checker_valid_manifest(tmp_path):
    manifest_dir = tmp_path / "test_output"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "test_manifest.json"
    manifest_path.write_text(
        json.dumps({"status": "PASS", "outputs": {"file1.txt": "path"}}),
        encoding="utf-8",
    )

    checker = GateChecker(str(tmp_path))
    status, gates, summary = checker.check_module_output(
        "test.module", {"test_manifest": "test_output/test_manifest.json"}
    )
    assert status == "PASS"
    assert len(gates) == 1
    assert gates[0].status == "PASS"


def test_gate_checker_global_audit_sub_gates(tmp_path):
    manifest_dir = tmp_path / "audit_output"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "00_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "status": "WARN",
            "gate_results": [
                {"gate": "Gate 1", "name": "residue", "status": "PASS"},
                {"gate": "Gate 2", "name": "ligand", "status": "WARN"},
                {"gate": "Gate 3", "name": "charge", "status": "PASS"},
            ],
        }),
        encoding="utf-8",
    )

    checker = GateChecker(str(tmp_path))
    status, gates, summary = checker.check_module_output(
        "cypforge.global_audit", {"00_manifest": "audit_output/00_manifest.json"}
    )
    assert status == "WARN"


# ── context building ─────────────────────────────────────────────────────────

def test_build_agent_context_empty():
    manifest = {
        "run_name": "test_context",
        "run_root": ".",
        "workflow_status": "INITIALIZING",
        "modules": {},
    }
    ctx = build_agent_context(manifest)
    assert "workflow" in ctx
    assert "modules" in ctx
    assert "summary" in ctx
    assert "next_allowed_actions" in ctx
    assert "policy_reminders" in ctx
    assert "Do not infer ligand atom mapping from atom order." in ctx["policy_reminders"]
    assert "Do not use PDB bond order as ligand chemistry truth." in ctx["policy_reminders"]


def test_build_agent_context_with_modules(tmp_path):
    # Create a mock manifest file
    output_dir = tmp_path / "00_environment_check"
    output_dir.mkdir()
    manifest_file = output_dir / "environment_manifest.json"
    manifest_file.write_text(
        json.dumps({
            "status": "PASS",
            "project_root": str(tmp_path),
            "run_root": str(tmp_path),
        }),
        encoding="utf-8",
    )

    raw_manifest = {
        "run_name": "test_ctx",
        "run_root": str(tmp_path),
        "workflow_status": "RUNNING",
        "modules": {
            "cypforge.environment_check": {
                "skill_id": "cypforge.environment_check",
                "status": "PASS",
                "gate_result": "PASS",
                "manifest_paths": {
                    "environment_manifest": "00_environment_check/environment_manifest.json",
                },
                "errors": [],
                "warnings": ["Multiwfn not found"],
                "summary": "All tools OK",
            },
            "cypforge.core1_prepare_heme_cym": {
                "skill_id": "cypforge.core1_prepare_heme_cym",
                "status": "PENDING",
                "gate_result": "",
                "manifest_paths": {},
                "errors": [],
                "warnings": [],
                "summary": "",
            },
        },
    }
    ctx = build_agent_context(raw_manifest)
    assert ctx["workflow"]["overall_status"] == "RUNNING"
    assert "cypforge.environment_check" in ctx["workflow"]["completed_modules"]
    assert "cypforge.core1_prepare_heme_cym" in ctx["workflow"]["pending_modules"]
    assert ctx["summary"]["modules_completed"] == 1
    assert ctx["summary"]["modules_pending"] == 1
    assert len(ctx["summary"]["warnings"]) >= 1


def test_build_agent_context_includes_policy_reminders():
    manifest = {
        "run_name": "test",
        "run_root": ".",
        "workflow_status": "INITIALIZING",
        "modules": {},
    }
    ctx = build_agent_context(manifest)
    reminders = ctx["policy_reminders"]
    assert any("SDF is the ligand chemistry source" in r for r in reminders)
    assert any("hard gate failure stops the workflow" in r.lower() for r in reminders)
    assert any("do not run production md" in r.lower() for r in reminders)


# ── StepRecord / ModuleRecord ────────────────────────────────────────────────

def test_step_record_defaults():
    sr = StepRecord(name="test_step")
    assert sr.status == "PENDING"
    assert sr.command == ""
    assert sr.exit_code is None


def test_module_record_defaults():
    mr = ModuleRecord(skill_id="test.module")
    assert mr.status == "PENDING"
    assert mr.steps == []
    assert mr.errors == []
    assert mr.warnings == []


def test_solvation_and_pre_md_modules_include_execution_validation_steps():
    solvation = get_module_by_skill_id("cypforge.core3_solvate_ionize")
    assert [step.name for step in solvation.steps] == [
        "solvate_ionize",
        "run_solvation_tleap",
        "validate_solvation_tleap",
    ]
    assert "15_complex_solvation_ionization/solvation_ionization_validation.json" in solvation.output_manifests

    pre_md_run = get_module_by_skill_id("cypforge.core3_run_pre_md")
    assert [step.name for step in pre_md_run.steps] == ["run_pre_md", "validate_pre_md_run"]
    assert "17_complex_pre_md_equilibration/complex_pre_md_equilibration_run_validation.json" in pre_md_run.output_manifests


def test_validate_complex_pre_md_run_success(tmp_path):
    pre_md = tmp_path / "pre_md"
    run = pre_md / "run"
    run.mkdir(parents=True)
    manifest = pre_md / "complex_pre_md_equilibration_manifest.json"
    manifest.write_text(
        json.dumps({
            "output_files": {"manifest_json": str(manifest), "run_dir": str(run)},
            "stages_range": "all",
            "stages": [
                {"id": "01_min", "trajectory": None},
                {"id": "02_md", "trajectory": "02_md.nc"},
            ],
        }),
        encoding="utf-8",
    )
    (run / "run_pre_md.started_at.txt").write_text("start\n", encoding="utf-8")
    (run / "run_pre_md.finished_at.txt").write_text("finish\n", encoding="utf-8")
    (run / "run_pre_md.exit_code.txt").write_text("0\n", encoding="utf-8")
    (run / "stage_status.tsv").write_text(
        "stage\tmdout\trestart\texit_code\tnormal_end\n"
        "01_min\trun/01_min.out\t01_min.rst7\t0\t1\n"
        "02_md\trun/02_md.out\t02_md.rst7\t0\t1\n",
        encoding="utf-8",
    )
    (run / "01_min.out").write_text("Final Performance Info\n", encoding="utf-8")
    (run / "02_md.out").write_text("Final Performance Info\n", encoding="utf-8")
    (pre_md / "01_min.rst7").write_text("rst\n", encoding="utf-8")
    (pre_md / "02_md.rst7").write_text("rst\n", encoding="utf-8")
    (run / "02_md.nc").write_text("nc\n", encoding="utf-8")

    result = validate_complex_pre_md_run(pre_md_manifest_json=manifest)
    assert result["status"] == "success"
    assert len(result["stages"]) == 2
    assert (pre_md / "complex_pre_md_equilibration_run_validation.json").is_file()


def test_validate_complex_pre_md_run_accepts_utf8_bom_manifest(tmp_path):
    pre_md = tmp_path / "pre_md"
    run = pre_md / "run"
    run.mkdir(parents=True)
    manifest = pre_md / "complex_pre_md_equilibration_manifest.json"
    payload = {
        "output_files": {"manifest_json": str(manifest), "run_dir": str(run)},
        "stages_range": "all",
        "stages": [{"id": "01_min", "trajectory": None}],
    }
    manifest.write_text("\ufeff" + json.dumps(payload), encoding="utf-8")
    (run / "run_pre_md.started_at.txt").write_text("start\n", encoding="utf-8")
    (run / "run_pre_md.finished_at.txt").write_text("finish\n", encoding="utf-8")
    (run / "run_pre_md.exit_code.txt").write_text("0\n", encoding="utf-8")
    (run / "stage_status.tsv").write_text(
        "stage\tmdout\trestart\texit_code\tnormal_end\n"
        "01_min\trun/01_min.out\t01_min.rst7\t0\t1\n",
        encoding="utf-8",
    )
    (run / "01_min.out").write_text("Final Performance Info\n", encoding="utf-8")
    (pre_md / "01_min.rst7").write_text("rst\n", encoding="utf-8")

    result = validate_complex_pre_md_run(pre_md_manifest_json=manifest)
    assert result["status"] == "success"


def test_pre_md_validator_ignores_benign_error_word_and_script_stops_on_missing_normal_end(tmp_path):
    mdout = tmp_path / "stage.out"
    mdout.write_text("RMS error estimate is printed here\nFinal Performance Info\n", encoding="utf-8")
    assert _fatal_keyword_count(mdout) == 0
    mdout.write_text("SHAKE failure detected\n", encoding="utf-8")
    assert _fatal_keyword_count(mdout) == 1

    script = _render_run_script(
        {"engine": "pmemd.cuda"},
        [{
            "id": "01_min",
            "mdin": str(tmp_path / "01_min.in"),
            "input_restart": "system_lig_solv.rst7",
            "output_restart": "01_min.rst7",
            "trajectory": None,
            "reference_restart": None,
        }],
    )
    assert 'if [ "$normal_end" -ne 1 ]; then' in script
    assert "lacks a normal-end marker" in script


def test_global_audit_charge_and_ion_gates_use_manifest_values(monkeypatch, tmp_path):
    ligand_check = tmp_path / "ligand_atom_check.json"
    ligand_check.write_text(json.dumps({"mol2_charge_sum": -1.0}), encoding="utf-8")
    solvation_validation = tmp_path / "solvation_ionization_validation.json"
    solvation_validation.write_text(
        json.dumps({"tleap": {"final_charge": 0.0, "cl_required": 2}}),
        encoding="utf-8",
    )
    paths = {"ligand_atom_check": ligand_check, "protstate_validation": tmp_path / "missing.json", "solvation_validation": solvation_validation}
    ligand_manifest = {
        "residues": {"ligand": {"leap_resname": "IMD", "leap_resid": 502}},
        "ligand_atom_check": {"expected_formal_charge": -1},
    }
    solvation_manifest = {"ionization": {"expected_neutralizing_anion_count": 2, "neutralizing_anion": "Cl-"}}

    gate, rows = global_audit._gate_charge_accounting(ligand_manifest, {}, solvation_manifest, paths)
    assert gate["status"] == "PASS"
    assert rows[0]["component"] == "IMD_mol2"
    assert rows[-1]["expected"] == 2

    atoms = [
        {"resname": "HEM", "resid": 501, "name": "FE", "x": 0.0, "y": 0.0, "z": 0.0, "element": "FE"},
        {"resname": "CYM", "resid": 410, "name": "SG", "x": 0.0, "y": 0.0, "z": 2.4, "element": "S"},
        {"resname": "IMD", "resid": 502, "name": "N1", "x": 8.0, "y": 0.0, "z": 0.0, "element": "N"},
        {"resname": "Cl-", "resid": 900, "name": "Cl-", "x": 20.0, "y": 0.0, "z": 0.0, "element": "Cl"},
        {"resname": "Cl-", "resid": 901, "name": "Cl-", "x": 21.0, "y": 0.0, "z": 0.0, "element": "Cl"},
    ]
    gate, rows = global_audit._gate_solvation_ions(solvation_manifest, atoms, {
        "heme_resname": "HEM",
        "heme_leap_resid": 501,
        "cym_resname": "CYM",
        "cym_leap_resid": 410,
        "ligand_resname": "IMD",
        "neutralizing_anion": "Cl-",
        "expected_neutralizing_anion_count": 2,
    })
    assert gate["status"] == "PASS"
    assert rows[-1]["observed"] == 2


def test_global_audit_residue_gate_uses_manifest_not_bundled_default_map():
    atoms = [{"resid": 1, "resname": "ALA"}, {"resid": 2, "resname": "HEM"}]
    gate, rows = global_audit._gate_residue_mapping({}, atoms)
    assert gate["status"] == "PASS"
    assert rows == []

    gate, rows = global_audit._gate_residue_mapping(
        {"expected_final_residue_checks": {"2": {"expected_resname": "HEM"}}},
        atoms,
    )
    assert gate["status"] == "PASS"
    assert rows[0]["current_resid"] == 2


def test_global_audit_geometry_uses_manifest_heme_name_and_fails_missing_ligand(tmp_path):
    traj = tmp_path / "traj.pdb"
    traj.write_text(
        "MODEL        1\n"
        "HETATM    1 FE   HMX B 501       0.000   0.000   0.000  1.00 20.00          FE\n"
        "HETATM    2 NA   HMX B 501       2.000   0.000   0.000  1.00 20.00           N\n"
        "HETATM    3 NB   HMX B 501      -2.000   0.000   0.000  1.00 20.00           N\n"
        "HETATM    4 NC   HMX B 501       0.000   2.000   0.000  1.00 20.00           N\n"
        "HETATM    5 ND   HMX B 501       0.000  -2.000   0.000  1.00 20.00           N\n"
        "ATOM      6 SG   CYM A 410       0.000   0.000   2.400  1.00 20.00           S\n"
        "ENDMDL\n",
        encoding="utf-8",
    )
    cfg = {"heme_resname": "HMX", "heme_leap_resid": 501, "cym_resname": "CYM", "cym_leap_resid": 410, "ligand_resname": "IMD"}
    geom = global_audit._single_frame_heme_geometry(global_audit._read_pdb_models(traj)[0], cfg)
    assert geom["fe_na_a"] == pytest.approx(2.0)

    gate, rows = global_audit._gate_p450_geometry({"trajectory_multimodel_pdb": traj}, cfg)
    assert gate["status"] == "FAIL"
    assert any(row.get("reason") == "No ligand heavy atoms found in trajectory frame 1" for row in rows)
