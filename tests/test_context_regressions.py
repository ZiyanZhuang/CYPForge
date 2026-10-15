import json

from cypforge_core.orchestrator import build_agent_context


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
