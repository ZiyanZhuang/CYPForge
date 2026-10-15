from pathlib import Path
from datetime import datetime, timezone

from cypforge_core.orchestrator import ModuleRunner, RunConfig, StepDef
import cypforge_core.orchestrator.runner as runner_module


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
