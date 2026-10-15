import json

from cypforge_core.local_knowledge import build_run_diagnosis, LocalDocsIndex


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


def test_docs_sync_refreshes_source_and_version_when_content_is_unchanged(tmp_path):
    manual = tmp_path / "manual.txt"
    manual.write_text("AMBER MANUAL\nunknown residue\n", encoding="utf-8")
    index = LocalDocsIndex(tmp_path / "docs.sqlite3")
    index.index_file(manual, source="amber", version="24")

    assert index.index_file(manual, source="ambertools", version="25")["status"] == "indexed"
    rows = index.query("unknown")
    assert len(rows) == 1
    assert (rows[0]["source"], rows[0]["version"]) == ("ambertools", "25")
    assert index.index_file(manual, source="ambertools", version="25")["status"] == "unchanged"
