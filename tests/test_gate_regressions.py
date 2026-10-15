import json

import pytest

from cypforge_core.orchestrator import GateChecker
from cypforge_core.orchestrator.gates import make_equilibration_decision
from cypforge_core.orchestrator.models import AUDIT_DIR_REL


@pytest.mark.parametrize("payload", [
    [], None, "PASS", 42,
    {"status": "PASS", "gate_results": [{"name": "hard failure", "status": "FAIL"}]},
    {"status": "success", "gate_results": [{"status": "failed"}]},
    {"status": "unknown", "gate_results": [{"status": "PASS"}]},
    {"gate_results": [{}]}, {"gate_results": [None]},
    {"status": "PASS", "gate_results": "FAIL"},
    {"status": "PASS", "gate_results": []},
])
def test_manifest_gates_fail_closed_on_conflicts_or_invalid_shapes(tmp_path, payload):
    (tmp_path / "candidate.json").write_text(json.dumps(payload), encoding="utf-8")

    status, gates, _ = GateChecker(str(tmp_path)).check_module_output("cypforge.probe", {"probe": "candidate.json"})

    assert status == "FAIL"
    assert gates[0].status == "FAIL"


def test_invalid_manifest_encoding_is_a_failed_gate(tmp_path):
    (tmp_path / "candidate.json").write_bytes(b"\xff")
    status, _, _ = GateChecker(str(tmp_path)).check_module_output("cypforge.probe", {"probe": "candidate.json"})
    assert status == "FAIL"


def test_warning_child_cannot_be_hidden_by_pass_parent(tmp_path):
    (tmp_path / "candidate.json").write_text(json.dumps({
        "status": "PASS", "gate_results": [{"status": "warning"}],
    }), encoding="utf-8")
    status, _, _ = GateChecker(str(tmp_path)).check_module_output("cypforge.probe", {"probe": "candidate.json"})
    assert status == "WARN"


@pytest.mark.parametrize("payload, expected_prefix", [
    ({"status": "failed", "gate_results": [{"name": "heme failure", "status": "failed"}]}, "STOP_"),
    ({"status": "unknown", "gate_results": [{"status": "PASS"}]}, "STOP_"),
    ({"status": "PASS", "gate_results": [{"status": "failed"}]}, "STOP_"),
    ({"status": "warning", "gate_results": [{"status": "warning"}]}, "WARN_"),
    ([], "STOP_"),
])
def test_equilibration_decision_never_allows_failed_or_unknown_audit(tmp_path, payload, expected_prefix):
    audit = tmp_path / AUDIT_DIR_REL / "00_manifest.json"
    audit.parent.mkdir()
    audit.write_text(json.dumps(payload), encoding="utf-8")

    make_equilibration_decision(str(tmp_path))

    decision = json.loads((audit.parent / "equilibration_decision_state.json").read_text(encoding="utf-8"))
    assert decision["decision"].startswith(expected_prefix)
