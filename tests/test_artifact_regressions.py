import json
import shutil
import subprocess
import sys

import pytest

from cypforge_core import prepare_complex_pre_md_equilibration, validate_solvation_tleap_outputs
from cypforge_core.complex_pre_md_equilibration import validate_complex_pre_md_run
from cypforge_core.complex_pre_md_equilibration import default_pre_md_protocol_config


@pytest.fixture
def solvation_outputs(tmp_path):
    paths = {key: tmp_path / filename for key, filename in {
        "expected_prmtop_after_tleap": "system.prmtop", "expected_rst7_after_tleap": "system.rst7",
        "expected_pdb_after_tleap": "system.pdb",
    }.items()}
    for path in paths.values():
        path.write_text("opaque fixture\n", encoding="utf-8")
    manifest = tmp_path / "solvation.json"
    manifest.write_text(json.dumps({"status": "prepared", "output_files": {
        "manifest_json": str(manifest), **{key: str(value) for key, value in paths.items()},
    }, "ionization": {}}), encoding="utf-8")
    (tmp_path / "leap.log").write_text(
        "Total unperturbed charge: 0.0\nExiting LEaP: Errors = 0; Warnings = 0; Notes = 0\n", encoding="utf-8",
    )
    return manifest, paths


@pytest.mark.parametrize("empty", ["expected_prmtop_after_tleap", "expected_rst7_after_tleap", "expected_pdb_after_tleap"])
def test_solvation_validation_rejects_empty_generated_artifacts(solvation_outputs, empty):
    manifest, paths = solvation_outputs
    paths[empty].write_bytes(b"")
    assert validate_solvation_tleap_outputs(solvation_manifest_json=manifest)["status"] == "fail"


def test_pre_md_render_rejects_empty_topology(solvation_outputs, tmp_path):
    manifest, paths = solvation_outputs
    paths["expected_prmtop_after_tleap"].write_bytes(b"")
    with pytest.raises((ValueError, FileNotFoundError), match="[Ee]mpty|[Nn]onempty"):
        prepare_complex_pre_md_equilibration(solvation_manifest_json=manifest, output_dir=tmp_path / "rendered")


@pytest.fixture
def pre_md_outputs(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    manifest = tmp_path / "pre_md.json"
    manifest.write_text(json.dumps({
        "output_files": {"manifest_json": str(manifest), "run_dir": str(run)},
        "stages": [{"id": "01_probe", "trajectory": "01_probe.nc"}],
    }), encoding="utf-8")
    for name, content in {
        "run_pre_md.started_at.txt": "start", "run_pre_md.finished_at.txt": "finish", "run_pre_md.exit_code.txt": "0",
        "stage_status.tsv": "stage\tmdout\trestart\texit_code\tnormal_end\n01_probe\trun/01_probe.out\t01_probe.rst7\t0\t1\n",
        "01_probe.out": "Final Performance Info\n", "01_probe.nc": "trajectory fixture",
    }.items():
        (run / name).write_text(content, encoding="utf-8")
    restart = tmp_path / "01_probe.rst7"
    restart.write_text("restart fixture", encoding="utf-8")
    return manifest, {"mdout": run / "01_probe.out", "restart": restart, "trajectory": run / "01_probe.nc"}


@pytest.mark.parametrize("empty", ["mdout", "restart", "trajectory"])
def test_pre_md_validation_rejects_empty_outputs_despite_success_table(pre_md_outputs, empty):
    manifest, paths = pre_md_outputs
    paths[empty].write_bytes(b"")
    assert validate_complex_pre_md_run(pre_md_manifest_json=manifest)["status"] == "fail"


def test_pre_md_validation_checks_normal_end_in_actual_mdout(pre_md_outputs):
    manifest, paths = pre_md_outputs
    paths["mdout"].write_text("Simulation started but was interrupted\n", encoding="utf-8")
    result = validate_complex_pre_md_run(pre_md_manifest_json=manifest)
    assert result["status"] == "fail"
    assert result["stages"][0]["normal_end"] is False


@pytest.mark.parametrize("case", ["zero", "empty_active", "duplicate", "unexpected"])
def test_pre_md_stage_table_must_match_nonempty_active_stage_list(pre_md_outputs, case):
    manifest, _ = pre_md_outputs
    data = json.loads(manifest.read_text(encoding="utf-8"))
    table = manifest.parent / "run/stage_status.tsv"
    if case == "zero":
        data["stages"] = []
    elif case == "empty_active":
        data["active_stages"] = []
    else:
        text = table.read_text(encoding="utf-8")
        extra = text.splitlines()[1] if case == "duplicate" else "unexpected\trun/01_probe.out\t01_probe.rst7\t0\t1"
        table.write_text(text + extra + "\n", encoding="utf-8")
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert validate_complex_pre_md_run(pre_md_manifest_json=manifest)["status"] == "fail"


@pytest.mark.parametrize("stage_id", ["01_min's", "01_min;echo", "01_min\nnext", "$(printfX)"])
def test_protocol_rejects_stage_ids_that_become_shell_syntax(solvation_outputs, tmp_path, stage_id):
    manifest, _ = solvation_outputs
    protocol = default_pre_md_protocol_config()
    protocol["stages"][0]["id"] = stage_id
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid stage id"):
        prepare_complex_pre_md_equilibration(
            solvation_manifest_json=manifest, protocol_config_json=path, output_dir=tmp_path / "rendered",
        )


@pytest.mark.parametrize("selection, expected_script", [
    ("all", "run_pre_md.sh"), ("1-8", "run_pre_md_1_8.sh"), ("9", "run_pre_md_9.sh"),
])
def test_windows_launcher_targets_the_script_rendered_for_selected_stages(solvation_outputs, tmp_path, selection, expected_script):
    manifest, _ = solvation_outputs
    output = tmp_path / "rendered"
    result = prepare_complex_pre_md_equilibration(solvation_manifest_json=manifest, output_dir=output, stages_range=selection)
    assert (output / expected_script).is_file()
    launcher = output / "run_pre_md_windows.ps1"
    assert f"bash {expected_script}" in launcher.read_text(encoding="utf-8")


def _bash_probe(script, *, parse_only=False):
    command = ["wsl", "--exec", "bash"] if sys.platform == "win32" else ["bash"]
    if not shutil.which(command[0]):
        pytest.skip("Bash/WSL is not available for shell boundary verification")
    return subprocess.run([*command, "-n" if parse_only else "-s"], input=script.encode("utf-8"), capture_output=True, timeout=15)


def test_engine_default_is_literal_data_in_generated_shell(solvation_outputs, tmp_path):
    manifest, _ = solvation_outputs
    protocol = default_pre_md_protocol_config()
    protocol["engine"] = "$(printf INJECTED)"
    config = tmp_path / "protocol.json"
    config.write_text(json.dumps(protocol), encoding="utf-8")
    prepare_complex_pre_md_equilibration(solvation_manifest_json=manifest, protocol_config_json=config, output_dir=tmp_path / "rendered")
    script = (tmp_path / "rendered/run_pre_md.sh").read_text(encoding="utf-8")
    # Execute only the variable assignment, never an engine or MD command.
    probe = _bash_probe("unset AMBER_ENGINE\n" + "\n".join(script.splitlines()[:3]) + '\nprintf "%s" "$AMBER_ENGINE"\n')
    assert probe.returncode == 0
    assert probe.stdout.decode("utf-8") == protocol["engine"]


def test_reference_path_quotes_do_not_break_generated_bash(solvation_outputs, tmp_path):
    manifest, _ = solvation_outputs
    protocol = default_pre_md_protocol_config()
    protocol["stages"][0]["reference"] = "reference with space's.rst7"
    config = tmp_path / "protocol.json"
    config.write_text(json.dumps(protocol), encoding="utf-8")
    prepare_complex_pre_md_equilibration(solvation_manifest_json=manifest, protocol_config_json=config, output_dir=tmp_path / "rendered")
    script = (tmp_path / "rendered/run_pre_md.sh").read_text(encoding="utf-8")
    assert _bash_probe(script, parse_only=True).returncode == 0
