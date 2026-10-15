from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import os
import errno

from cypforge_core import cli
from cypforge_core.orchestrator import RunConfig, WorkflowManager
from cypforge_core.orchestrator import CYPForgeOrchestrator


def test_init_refuses_to_overwrite_existing_run(tmp_path):
    config = RunConfig("original", str(tmp_path / "run"), str(tmp_path))
    workflow = WorkflowManager(config)
    workflow.init_run()
    before = {path.name: path.read_bytes() for path in (workflow.config_path, workflow.manifest_path)}

    with pytest.raises(FileExistsError):
        WorkflowManager(RunConfig("replacement", config.run_root, config.project_root)).init_run()

    assert {path.name: path.read_bytes() for path in (workflow.config_path, workflow.manifest_path)} == before


def test_concurrent_init_has_exactly_one_owner(tmp_path):
    def initialize(name):
        try:
            WorkflowManager(RunConfig(name, str(tmp_path / "run"), str(tmp_path))).init_run()
        except FileExistsError:
            return "conflict"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(initialize, ("first", "second"))) == ["conflict", "created"]


def test_cli_init_reports_existing_directory_without_changing_it(tmp_path, capsys):
    run_root = tmp_path / "run"
    run_root.mkdir()
    marker = run_root / "keep.txt"
    marker.write_text("existing data", encoding="utf-8")
    args = cli._build_parser().parse_args([
        "init", "existing", "--run-root", str(run_root), "--ligand-resname", "LIG",
        "--project-root", str(Path(__file__).resolve().parents[1]),
    ])

    assert cli.cmd_init(args) == 2
    assert "[ERROR]" in capsys.readouterr().out
    assert list(run_root.iterdir()) == [marker]


def test_failed_checkpoint_replacement_preserves_last_manifest(tmp_path, monkeypatch):
    workflow = WorkflowManager(RunConfig("atomic", str(tmp_path / "run"), str(tmp_path)))
    manifest = workflow.init_run()
    original = workflow.manifest_path.read_bytes()
    manifest.workflow_status = "RUNNING"

    def replacement_failed(source, target):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(os, "replace", replacement_failed)
    with pytest.raises(OSError, match="interrupted replacement"):
        workflow.save_manifest(manifest)

    assert workflow.manifest_path.read_bytes() == original
    assert {path.name for path in workflow.run_root.iterdir()} == {
        "run_config.json", "run_manifest.json", "logs", "decisions",
    }


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_checkpoint_retries_transient_windows_sharing_conflict(tmp_path, monkeypatch, winerror):
    workflow = WorkflowManager(RunConfig("sharing", str(tmp_path / "run"), str(tmp_path)))
    manifest = workflow.init_run()
    replace = os.replace
    calls = []

    def transient_replace(source, target):
        calls.append(target)
        if len(calls) <= 2:
            error = PermissionError("reader temporarily owns a Windows handle")
            error.winerror = winerror
            raise error
        return replace(source, target)

    monkeypatch.setattr(os, "replace", transient_replace)
    manifest.workflow_status = "RUNNING"
    workflow.save_manifest(manifest)
    assert workflow.load_manifest().workflow_status == "RUNNING"
    assert len(calls) == 3
    assert not list(workflow.run_root.glob("*.tmp"))


@pytest.mark.parametrize("error_code", [errno.ENOENT, errno.EACCES, getattr(errno, "ENODATA", 61)])
def test_checkpoint_reader_retries_drvfs_replacement_window(tmp_path, monkeypatch, error_code):
    workflow = WorkflowManager(RunConfig("reader", str(tmp_path / "run"), str(tmp_path)))
    workflow.init_run()
    read_text = Path.read_text
    calls = []

    def transient_read(path, *args, **kwargs):
        if path == workflow.manifest_path:
            calls.append(path)
            if len(calls) <= 2:
                raise OSError(error_code, "transient shared-filesystem replacement window")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", transient_read)
    assert workflow.load_manifest().run_name == "reader"
    assert len(calls) == 3


def test_concurrent_workflow_execution_is_rejected(tmp_path, monkeypatch):
    from threading import Event
    from types import SimpleNamespace
    import cypforge_core.orchestrator.runner as runner_module

    started, finish = Event(), Event()
    config = RunConfig("owner", str(tmp_path / "run"), str(tmp_path))
    first = CYPForgeOrchestrator(config)
    first.init()

    def subprocess_probe(*args, **kwargs):
        if not started.is_set():
            started.set()
            assert finish.wait(5), "test did not release the running subprocess"
        return SimpleNamespace(returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr(runner_module.subprocess, "run", subprocess_probe)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first.run_until, "cypforge.core1_prepare_heme_cym")
        try:
            assert started.wait(5)
            with pytest.raises(RuntimeError, match="already.*run|run.*already"):
                CYPForgeOrchestrator(config).run_until("cypforge.core1_prepare_heme_cym")
        finally:
            finish.set()
            future.result(timeout=5)

    assert first.workflow.load_manifest().modules["cypforge.environment_check"]["status"] == "PASS"
