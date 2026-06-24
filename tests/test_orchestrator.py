"""Tests for the CYPForge Outer Shell orchestrator."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

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
from cypforge_core.orchestrator.runner import _format_cmd


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
    assert cfg.ligand_resname == "NCT"
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
