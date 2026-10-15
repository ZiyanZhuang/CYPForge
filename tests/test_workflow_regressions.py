import pytest

from cypforge_core.orchestrator import CYPForgeOrchestrator, RunConfig, ModuleRecord


@pytest.fixture
def simulated_workflow(tmp_path, monkeypatch):
    orchestrator = CYPForgeOrchestrator(RunConfig("resume", str(tmp_path / "run"), str(tmp_path)))
    orchestrator.init()
    executed = []

    def execute(self, module, manifest):
        executed.append(module.index)
        record = ModuleRecord(module.skill_id, status="PASS", gate_result="PASS")
        self.workflow.update_module_record(manifest, module.skill_id, record)
        return record

    monkeypatch.setattr(CYPForgeOrchestrator, "_execute_module", execute)
    return orchestrator, executed


def test_preparation_boundary_remains_resumable_without_claiming_full_completion(simulated_workflow):
    orchestrator, executed = simulated_workflow
    prepared = orchestrator.run_until("cypforge.core3_run_pre_md")

    assert prepared.workflow_status == "PREPARED"
    assert prepared.completed_at == ""
    assert executed == list(range(6))
    assert orchestrator.resume().workflow_status == "COMPLETED"
    assert executed == list(range(10))


def test_legacy_partial_completed_checkpoint_can_resume(simulated_workflow):
    orchestrator, executed = simulated_workflow
    manifest = orchestrator.workflow.load_manifest()
    for module in orchestrator.workflow.get_ordered_modules()[:6]:
        manifest.modules[module.skill_id]["status"] = "PASS"
    manifest.workflow_status = "COMPLETED"
    manifest.completed_at = "old preparation endpoint"
    orchestrator.workflow.save_manifest(manifest)

    assert orchestrator.resume().workflow_status == "COMPLETED"
    assert executed == [6, 7, 8, 9]


def test_preparation_query_does_not_erase_later_failure(simulated_workflow):
    orchestrator, _ = simulated_workflow
    manifest = orchestrator.run_until("cypforge.core3_run_pre_md")
    manifest.modules["cypforge.core3_run_pre_md"]["status"] = "FAIL"
    manifest.workflow_status = "STOPPED_ON_FAIL"
    orchestrator.workflow.save_manifest(manifest)

    assert orchestrator.run_until("cypforge.core3_run_pre_md").workflow_status == "STOPPED_ON_FAIL"


def test_execution_rejects_ignored_retry_setting_before_any_module(simulated_workflow):
    orchestrator, executed = simulated_workflow
    orchestrator.config.max_retries = 1
    with pytest.raises(ValueError, match="retries"):
        orchestrator.run_until("cypforge.core3_run_pre_md")
    assert executed == []
