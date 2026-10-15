from pathlib import Path
from datetime import datetime, timezone
import shutil
import sys
from types import SimpleNamespace
import pytest

from cypforge_core.orchestrator import ModuleRunner, RunConfig, StepDef
import cypforge_core.orchestrator.runner as runner_module
from cypforge_core.io import _win_to_wsl


def test_runner_creates_portable_logs_and_executes_step(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    run_root = tmp_path / "中文 run"
    runner = ModuleRunner(RunConfig("logs", str(run_root), str(project_root)))

    record = runner.run_step(
        StepDef("python_probe", "python_script", command_template='python -c "print(42)"'),
        run_root / "logs",
    )

    assert record.status == "PASS", record.error_message
    assert Path(record.stdout_path).read_text(encoding="utf-8").strip() == "42"
    assert Path(record.stderr_path).is_file()
    assert len(list((run_root / "logs").glob("*_command.txt"))) == 1


def test_repeated_step_keeps_both_attempt_logs(tmp_path, monkeypatch):
    class FrozenDatetime:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(runner_module, "datetime", FrozenDatetime)
    runner = ModuleRunner(RunConfig("retry", str(tmp_path), str(tmp_path)))
    first = runner.run_step(StepDef("probe", "python_script", command_template='python -c "print(42)"'), tmp_path)
    second = runner.run_step(StepDef("probe", "python_script", command_template='python -c "print(43)"'), tmp_path)

    assert first.status == second.status == "PASS"
    assert first.stdout_path != second.stdout_path
    assert Path(first.stdout_path).read_text(encoding="utf-8").strip() == "42"
    assert Path(second.stdout_path).read_text(encoding="utf-8").strip() == "43"
    assert len(list(tmp_path.glob("*_command.txt"))) == 2


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows path-length boundary")
def test_windows_log_path_limit(tmp_path):
    log_dir = tmp_path / ("x" * max(1, 172 - len(str(tmp_path)) - 1))
    log_dir.mkdir()
    runner = ModuleRunner(RunConfig("long-log", str(tmp_path), str(tmp_path)))
    step = StepDef("stage_prepared_ligand_complex", "python_script", command_template='python -c "print(42)"')
    first = runner.run_step(step, log_dir)
    second = runner.run_step(step, log_dir)
    assert first.status == second.status == "PASS"
    assert first.stdout_path != second.stdout_path
    assert Path(first.stdout_path).read_text(encoding="utf-8").strip() == "42"
    command_logs = list(log_dir.glob("*_command.txt"))
    assert len(command_logs) == 2
    assert all(step.name in path.read_text(encoding="utf-8") for path in command_logs)


def test_runner_preserves_exit_code_and_logs_with_non_utf8_output(tmp_path):
    script = tmp_path / "emit_bytes.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write(b'\\xff\\xfeA\\x00')\n"
        "sys.stderr.buffer.write(b'FATAL \\xff\\n')\nsys.exit(7)\n",
        encoding="utf-8",
    )
    runner = ModuleRunner(RunConfig("encoding", str(tmp_path), str(tmp_path)))

    record = runner.run_step(StepDef("probe", "python_script", command_template="python emit_bytes.py"), tmp_path / "logs")

    assert record.status == "FAIL"
    assert record.exit_code == 7
    assert Path(record.stdout_path).is_file()
    assert "FATAL" in Path(record.stderr_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", ["python_script", "python_inline"])
def test_command_substitution_preserves_repeated_spaces_in_input_paths(tmp_path, kind):
    source = tmp_path / "input  中文  with  spaces.pdb"
    source.write_text("END\n", encoding="utf-8")
    (tmp_path / "check_path.py").write_text(
        "import pathlib, sys\nassert pathlib.Path(sys.argv[1]).is_file(), sys.argv[1]\n", encoding="utf-8",
    )
    template = (
        'python check_path.py "{raw_protein_heme_pdb}"' if kind == "python_script"
        else "from pathlib import Path; assert Path({raw_protein_heme_pdb}).is_file()"
    )
    runner = ModuleRunner(RunConfig("spaces", str(tmp_path), str(tmp_path), raw_protein_heme_pdb=str(source)))

    record = runner.run_step(StepDef("input", kind, command_template=template), tmp_path / "logs")

    assert record.status == "PASS", record.error_message


@pytest.mark.parametrize("kind", ["python_script", "python_inline", "wsl_command"])
def test_placeholder_text_inside_a_filename_remains_literal(tmp_path, monkeypatch, kind):
    if kind == "wsl_command" and sys.platform == "win32" and not shutil.which("wsl"):
        pytest.skip("WSL unavailable")
    source = tmp_path / "input {ligand_resname} 中文.pdb"
    source.write_text("END\n", encoding="utf-8")
    (tmp_path / "check_path.py").write_text(
        "import pathlib, sys\nassert pathlib.Path(sys.argv[1]).is_file(), sys.argv[1]\n", encoding="utf-8",
    )
    templates = {
        "python_script": 'python check_path.py "{raw_protein_heme_pdb}"',
        "python_inline": "from pathlib import Path; assert Path({raw_protein_heme_pdb}).is_file()",
        "wsl_command": "test -f {raw_protein_heme_pdb}",
    }
    monkeypatch.delenv("AMBER_SH", raising=False)
    monkeypatch.delenv("AMBERHOME", raising=False)
    input_path = _win_to_wsl(source) if kind == "wsl_command" and sys.platform == "win32" else str(source)
    runner = ModuleRunner(RunConfig("literal", str(tmp_path), str(tmp_path), raw_protein_heme_pdb=input_path, ligand_resname="NCT"))
    record = runner.run_step(StepDef("literal", kind, command_template=templates[kind]), tmp_path / "logs")
    assert record.status == "PASS", record.error_message


def test_native_linux_uses_bash_without_windows_wsl_launcher(tmp_path, monkeypatch):
    calls = []

    def harmless_process(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="owned probe", stderr="")

    monkeypatch.setattr(runner_module, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(runner_module.subprocess, "run", harmless_process)
    monkeypatch.delenv("AMBER_SH", raising=False)
    monkeypatch.delenv("AMBERHOME", raising=False)
    runner = ModuleRunner(RunConfig("linux", str(tmp_path), str(tmp_path)))
    record = runner.run_step(StepDef("probe", "wsl_command", command_template="printf owned"), tmp_path / "logs")
    assert record.status == "PASS"
    assert calls[0][0] == "bash"


@pytest.mark.parametrize("source", ["explicit", "AMBER_SH", "AMBERHOME"])
def test_runner_sources_explicit_setup_file_without_filename_guessing(tmp_path, monkeypatch, source):
    if sys.platform == "win32" and not shutil.which("wsl"):
        pytest.skip("WSL unavailable")
    if sys.platform != "win32" and not shutil.which("bash"):
        pytest.skip("Bash unavailable")
    directory = tmp_path / "env  中文's path"
    directory.mkdir()
    setup = directory / ("amber.sh" if source == "AMBERHOME" else "custom_setup.sh")
    setup.write_bytes(b"export OWNED_SETUP_OK=resolved\n")
    setup_path = _win_to_wsl(setup) if sys.platform == "win32" else str(setup)
    monkeypatch.delenv("AMBER_SH", raising=False)
    monkeypatch.delenv("AMBERHOME", raising=False)
    config = RunConfig("setup", str(tmp_path), str(tmp_path))
    if source == "explicit":
        config.amber_sh = setup_path
    elif source == "AMBER_SH":
        monkeypatch.setenv("AMBER_SH", setup_path)
    else:
        monkeypatch.setenv("AMBERHOME", setup_path.rsplit("/", 1)[0])
    runner = ModuleRunner(config)
    record = runner.run_step(
        StepDef("source_only", "wsl_command", command_template='test "$OWNED_SETUP_OK" = resolved'), tmp_path / "logs",
    )
    assert record.status == "PASS", record.error_message
