from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cypforge_core import cli
from cypforge_core.orchestrator import RunConfig, WorkflowManager


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
