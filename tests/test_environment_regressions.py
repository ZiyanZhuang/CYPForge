from types import SimpleNamespace

import pytest

from cypforge_core.orchestrator import CYPForgeOrchestrator, RunConfig
import cypforge_core.orchestrator.runner as runner_module


@pytest.mark.parametrize("supplied", [False, True])
def test_environment_requires_only_tools_used_by_selected_ligand_route(tmp_path, monkeypatch, supplied):
    config = RunConfig(
        "tools", str(tmp_path / "run"), str(tmp_path),
        supplied_ligand_mol2="reviewed.mol2" if supplied else "",
        supplied_ligand_frcmod="reviewed.frcmod" if supplied else "",
    )
    orchestrator = CYPForgeOrchestrator(config)
    orchestrator.init()

    def probe(parts, **kwargs):
        missing = any(tool in parts[-1] for tool in ("which antechamber", "which parmchk2"))
        return SimpleNamespace(returncode=1 if missing else 0, stdout="", stderr="")

    monkeypatch.setattr(runner_module.subprocess, "run", probe)
    manifest = orchestrator.run_until("cypforge.core1_prepare_heme_cym")

    assert manifest.modules["cypforge.environment_check"]["status"] == ("PASS" if supplied else "FAIL")
