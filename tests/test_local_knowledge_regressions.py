import json

from cypforge_core.local_knowledge import build_run_diagnosis


def test_diagnosis_redacts_secret_variants_and_complete_spaced_paths(tmp_path):
    config = {
        "run_name": "privacy", "api-key": "FAKE_CONFIG_CREDENTIAL", "apiKey": "FAKE_CAMEL_CREDENTIAL",
        "input_path": r"C:\outside\Private Project\Sensitive.pdb",
    }
    manifest = {"modules": {"core": {
        "headers": {"Authorization": "Bearer FAKE_HEADER_CREDENTIAL"},
        "command": "tool --api-key=FAKE_COMMAND_CREDENTIAL --password='FAKE phrase-sensitive'",
    }}}
    (tmp_path / "run_config.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "stage.log").write_text(
        "FATAL Authorization: Bearer FAKE_LOG_CREDENTIAL\n"
        'FATAL Authorization: "Bearer FAKE_QUOTED_CREDENTIAL"\n'
        r"FATAL input=C:\outside\Private Project\Sensitive.pdb" "\n"
        "ERROR input=/srv/private project/Hidden.pdb\n",
        encoding="utf-8",
    )

    report = build_run_diagnosis(tmp_path)
    serialized = json.dumps(report)
    assert "FAKE_" not in serialized
    assert "phrase-sensitive" not in serialized
    assert "Private Project" not in serialized
    assert "private project" not in serialized
    assert "Hidden.pdb" not in serialized
    assert report["config_public"]["input_path"] == "Sensitive.pdb"
