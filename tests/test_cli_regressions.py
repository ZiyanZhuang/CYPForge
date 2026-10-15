import json
import sys
import shutil
from pathlib import Path

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


def test_cli_resume_error_checkpoint_returns_failure_without_execution(tmp_path, monkeypatch, capsys):
    root = tmp_path / "run"
    workflow = WorkflowManager(RunConfig("error", str(root), str(tmp_path)))
    manifest = workflow.init_run()
    manifest.workflow_status = "ERROR"
    workflow.save_manifest(manifest)
    original = workflow.manifest_path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["cypforge", "resume", "error", "--run-root", str(root)])

    assert cli.main() == 2
    assert workflow.manifest_path.read_bytes() == original
    assert "[ERROR]" in capsys.readouterr().out


def test_init_resolves_amberhome_directory_to_setup_filename(tmp_path, monkeypatch):
    root = tmp_path / "run"
    monkeypatch.delenv("AMBER_SH", raising=False)
    monkeypatch.setenv("AMBERHOME", "/opt/amber custom")
    monkeypatch.setattr(cli, "load_profile", lambda: {"values": {}})
    args = cli._build_parser().parse_args([
        "init", "setup", "--ligand-resname", "LIG", "--run-root", str(root),
        "--project-root", str(Path(__file__).resolve().parents[1]),
    ])
    assert cli.cmd_init(args) == 0
    assert json.loads((root / "run_config.json").read_text(encoding="utf-8"))["amber_sh"] == "/opt/amber custom/amber.sh"


@pytest.mark.parametrize("command", ["status", "context", "resume"])
def test_cli_rejects_existing_run_with_missing_checkpoint(tmp_path, monkeypatch, capsys, command):
    root = tmp_path / "run"
    workflow = WorkflowManager(RunConfig("incomplete", str(root), str(tmp_path)))
    workflow.init_run()
    workflow.manifest_path.unlink()
    monkeypatch.setattr(sys, "argv", ["cypforge", command, "incomplete", "--run-root", str(root)])
    assert cli.main() == 2
    assert "[ERROR]" in capsys.readouterr().err
    assert not workflow.manifest_path.exists()


@pytest.mark.parametrize("redirect", ["config", "manifest"])
def test_explicit_run_root_cannot_redirect_to_a_different_run(tmp_path, monkeypatch, capsys, redirect):
    original = tmp_path / "original"
    copied = tmp_path / "copied"
    WorkflowManager(RunConfig("original", str(original), str(tmp_path))).init_run()
    shutil.copytree(original, copied)
    if redirect == "manifest":
        config_path = copied / "run_config.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["run_root"] = str(copied)
        config_path.write_text(json.dumps(data), encoding="utf-8")
    before = {str(path): path.read_bytes() for root in (original, copied) for path in root.glob("*.json")}
    monkeypatch.setattr(sys, "argv", ["cypforge", "status", "copied", "--run-root", str(copied)])
    assert cli.main() == 2
    assert "run root" in capsys.readouterr().err.lower()
    assert {name: Path(name).read_bytes() for name in before} == before


@pytest.mark.parametrize("retry_count", ["1", "-1"])
def test_init_rejects_unsupported_automatic_retries(tmp_path, monkeypatch, retry_count):
    root = tmp_path / "run"
    monkeypatch.setattr(sys, "argv", [
        "cypforge", "init", "retry", "--ligand-resname", "LIG", "--run-root", str(root), "--max-retries", retry_count,
    ])
    assert cli.main() == 2
    assert not root.exists()


@pytest.mark.parametrize("downstream_status", ["PASS", "WARN", "RUNNING", "SKIPPED", "PENDING", "FAIL"])
def test_protonation_apply_cannot_rewrite_inputs_consumed_by_downstream_modules(tmp_path, monkeypatch, downstream_status):
    root = tmp_path / "run"
    workflow = WorkflowManager(RunConfig("protonation", str(root), str(tmp_path)))
    manifest = workflow.init_run()
    original = root / "01_heme_only/prepared_heme_complex.pdb"
    original.parent.mkdir()
    original.write_text("ATOM      1  CA  GLU A 419      10.000  10.000  10.000  1.00 20.00           C\nEND\n", encoding="utf-8")
    mapping = root / "13_ligand_mapping_leapin"
    mapping.mkdir()
    combined = mapping / "combined.pdb"
    combined.write_text("ATOM      1  CA  GLU A   1      10.000  10.000  10.000  1.00 20.00           C\nEND\n", encoding="utf-8")
    leapin = mapping / "leap.in"
    leapin.write_text("savepdb complex combined.pdb\n", encoding="utf-8")
    (mapping / "ligand_mapping_leapin_manifest.json").write_text(json.dumps({
        "output_files": {"combined_pdb": str(combined), "leapin": str(leapin)}, "residues": {}, "parameter_files": {},
    }), encoding="utf-8")
    manifest.modules["cypforge.core3_solvate_ionize"]["status"] = downstream_status
    workflow.save_manifest(manifest)
    def snapshot():
        return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*")
                if path.is_file() and path.name != ".cypforge.lock"}
    before = snapshot()
    monkeypatch.setattr(sys, "argv", [
        "cypforge", "protonation", "apply", "protonation", "--run-root", str(root), "--set", "A:GLU419=GLH",
    ])
    if downstream_status in {"PENDING", "FAIL"}:
        assert cli.main() == 0
        assert "GLH" in (root / "14_complex_protonation_finalize/complex_ligand_protonation_final.pdb").read_text(encoding="utf-8")
    else:
        assert cli.main() == 2
        assert snapshot() == before
