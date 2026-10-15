import json

import pytest

from cypforge_core import (
    recommend_protonation_states,
    build_protonation_decision_from_selectors,
    finalize_complex_protonation_mapping,
)


@pytest.fixture
def protonation_inputs(tmp_path):
    def build(chain):
        original = tmp_path / "original.pdb"
        original.write_text(
            f"ATOM      1  CA  GLU {chain:1s} 419      10.000  10.000  10.000  1.00 20.00           C\nEND\n",
            encoding="utf-8",
        )
        combined = tmp_path / "combined.pdb"
        combined.write_text("ATOM      1  CA  GLU A   1      10.000  10.000  10.000  1.00 20.00           C\nEND\n", encoding="utf-8")
        leapin = tmp_path / "leap.in"
        leapin.write_text("savepdb complex combined.pdb\n", encoding="utf-8")
        manifest = tmp_path / "ligand.json"
        manifest.write_text(json.dumps({
            "output_files": {"combined_pdb": str(combined), "leapin": str(leapin)},
            "residues": {}, "parameter_files": {},
        }), encoding="utf-8")
        return original, manifest
    return build


@pytest.mark.parametrize("chain", ["", "A"])
def test_recommended_selector_preserves_original_chain_through_apply(tmp_path, protonation_inputs, chain):
    original, manifest = protonation_inputs(chain)
    report = recommend_protonation_states(
        ligand_mapping_manifest_json=manifest, original_prepared_pdb=original, output_dir=tmp_path / "review",
    )
    decision_path = tmp_path / "decision.json"
    decision = build_protonation_decision_from_selectors(
        original_prepared_pdb=original, selectors=[report["recommendations"][0]["selector"] + "=GLH"],
        output_json=decision_path,
    )
    result = finalize_complex_protonation_mapping(
        ligand_mapping_manifest_json=manifest, original_prepared_pdb=original,
        protonation_decision_json=decision_path, output_dir=tmp_path / "final",
    )

    assert result["status"] == "success"
    assert decision["recommended_changes"][0]["original_chain"] == chain
    assert result["expected_final_residue_checks"]["1"]["found_resname"] == "GLH"
