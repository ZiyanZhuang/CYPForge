import json

import pytest

from cypforge_core.orchestrator import GateChecker


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
