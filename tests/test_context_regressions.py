import json
import pytest

from cypforge_core.orchestrator import build_agent_context
from cypforge_core.orchestrator.models import build_module_definitions


def test_context_retains_nested_output_paths_charge_and_failed_residue_evidence(tmp_path):
    data = {
        "status": "failed", "output_files": {"prmtop": "system.prmtop", "pdb": "system.pdb"},
        "inputs": {"formal_charge": 0},
        "expected_final_residue_checks": {"1": {
            "status": "failed", "expected_resname": "GLH", "found_resname": "GLU",
        }},
        "unselected_bulk": list(range(100)), "outputs": list(range(100)),
    }
    (tmp_path / "protonation.json").write_text(json.dumps(data), encoding="utf-8")
    context = build_agent_context({"run_root": str(tmp_path), "modules": {"core": {
        "status": "FAIL", "manifest_paths": {"protonation": "protonation.json"},
    }}})
    compact = context["modules"]["core"]["manifests"]["protonation"]

    assert compact["output_files"] == data["output_files"]
    assert compact["inputs"]["formal_charge"] == 0
    assert compact["expected_final_residue_checks"]["1"] == data["expected_final_residue_checks"]["1"]
    assert "unselected_bulk" not in compact
    assert compact["outputs"] == "[100 items]"


@pytest.mark.parametrize("audit_status", ["PASS", "WARN"])
def test_context_does_not_authorize_equilibration_before_the_decision(tmp_path, audit_status):
    modules = {
        module.skill_id: {"status": "PASS" if module.index < 8 else "PENDING"}
        for module in build_module_definitions()
    }
    modules["cypforge.global_audit"]["status"] = audit_status
    context = build_agent_context({"run_root": str(tmp_path), "workflow_status": "RUNNING", "modules": modules})
    actions = context["next_allowed_actions"]
    assert not any(action.startswith("ALLOW_") for action in actions)
    assert any("cypforge.equilibration_decision" in action for action in actions)


@pytest.mark.parametrize("payload", [b"[]", b"null", b"1", b"{", b"\xff", None])
def test_context_reports_unreadable_stage_evidence_and_blocks_progress(tmp_path, payload):
    if payload is not None:
        (tmp_path / "bad.json").write_bytes(payload)
    (tmp_path / "good.json").write_text('{"status":"success","charge":0}', encoding="utf-8")
    context = build_agent_context({"run_root": str(tmp_path), "modules": {
        "bad": {"status": "PASS", "gate_result": "PASS", "manifest_paths": {"evidence": "bad.json"}},
        "good": {"status": "PASS", "gate_result": "PASS", "manifest_paths": {"evidence": "good.json"}},
    }})
    assert "_error" in context["modules"]["bad"]["manifests"]["evidence"]
    assert context["modules"]["good"]["manifests"]["evidence"]["charge"] == 0
    assert "STOP_FIX_UPSTREAM_MODULE" in context["next_allowed_actions"]


def test_context_reads_bom_stage_manifest(tmp_path):
    (tmp_path / "stage.json").write_text('{"status":"success","charge":0}', encoding="utf-8-sig")
    context = build_agent_context({"run_root": str(tmp_path), "modules": {
        "core": {"status": "PASS", "manifest_paths": {"evidence": "stage.json"}},
    }})
    assert context["modules"]["core"]["manifests"]["evidence"]["charge"] == 0
