import json
from pathlib import Path

from cypforge_core.orchestrator import CYPForgeOrchestrator, RunConfig


def test_bundled_supplied_parameter_workflow_retains_prepared_heme_and_ligand(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    benchmark = repo / "benchmark" / "4EJJ"
    config = RunConfig(
        "4ejj", str(tmp_path / "run"), str(repo),
        raw_protein_heme_pdb=str(benchmark / "4EJJ_CPD1_NCT.pdb"),
        ligand_template_sdf=str(benchmark / "nicotine.sdf"),
        supplied_ligand_mol2=str(benchmark / "NCT_multiwfn_resp.mol2"),
        supplied_ligand_frcmod=str(benchmark / "NCT.frcmod"),
        heme_state="CPDI", ligand_resname="NCT", ligand_chain="",
    )
    orchestrator = CYPForgeOrchestrator(config)
    manifest = orchestrator.init()
    # This fixture exercises real no-QM Core 1/2; no external MD tool is launched.
    manifest.modules["cypforge.environment_check"]["status"] = "PASS"
    orchestrator.workflow.save_manifest(manifest)

    result = orchestrator.run_until("cypforge.core3_finalize_protonation")

    assert result.modules["cypforge.core2_prepare_ligand_resp_gaff2"]["status"] == "PASS"
    root = Path(config.run_root)
    mapping = json.loads((root / "13_ligand_mapping_leapin/ligand_mapping_leapin_manifest.json").read_text(encoding="utf-8"))
    staged = Path(mapping["input_files"]["complex_pdb"]).read_text(encoding="utf-8").splitlines()
    prepared = (root / "01_heme_only/prepared_heme_complex.pdb").read_text(encoding="utf-8").splitlines()
    assert [line[12:54] for line in staged if line[17:20] == "HEM"] == [
        line[12:54] for line in prepared if line[17:20] == "HEM"
    ]
    assert len([line for line in staged if line[17:20] == "NCT"]) == 26
    ligand_gate = json.loads((root / "10_ligand_gpu4pyscf_esp/ligand_parameterization_gate.json").read_text(encoding="utf-8"))
    assert ligand_gate["qm_esp_resp_executed"] is False
