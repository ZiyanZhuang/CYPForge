import json
import sys

import pytest

from cypforge_core import cli
from cypforge_core.orchestrator import RunConfig, WorkflowManager


@pytest.mark.parametrize("filename, payload", [
    ("run_config.json", "{"), ("run_config.json", "[]"),
    ("run_manifest.json", "{"), ("run_manifest.json", "[]"),
    ("run_manifest.json", '{"schema":"cypforge.orchestrator.run_manifest.v1","modules":[]}'),
])
def test_cli_status_reports_corrupt_state_as_error_exit(tmp_path, monkeypatch, capsys, filename, payload):
    root = tmp_path / "run"
    WorkflowManager(RunConfig("broken", str(root), str(tmp_path))).init_run()
    (root / filename).write_text(payload, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cypforge", "status", "broken", "--run-root", str(root)])

    assert cli.main() == 2
    output = capsys.readouterr()
    assert "[ERROR]" in output.out + output.err
    assert "Traceback" not in output.out + output.err


def test_cli_docs_reports_invalid_database_as_error_exit(tmp_path, monkeypatch, capsys):
    database = tmp_path / "docs.sqlite3"
    database.write_bytes(b"invalid SQLite database")
    monkeypatch.setattr(sys, "argv", ["cypforge", "docs", "query", "unknown", "--database", str(database)])
    assert cli.main() == 2
    output = capsys.readouterr()
    assert "[ERROR]" in output.out + output.err
