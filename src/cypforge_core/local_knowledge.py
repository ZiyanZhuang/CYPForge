from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_HOME = Path.home() / ".cypforge"
SOURCE_REGISTRY = {
    "amber": {
        "url": "https://ambermd.org/Manuals.php",
        "license_note": "Keep locally; verify the applicable Amber or AmberTools license before redistribution.",
    },
    "pyscf": {
        "url": "https://pyscf.org/user/index.html",
        "license_note": "Official PySCF user documentation.",
    },
    "ambertools": {
        "url": "https://ambermd.org/AmberTools.php",
        "license_note": "Keep locally; verify the license of each AmberTools component before redistribution.",
    },
    "gpu4pyscf": {
        "url": "https://github.com/pyscf/gpu4pyscf",
        "license_note": "Official GPU4PySCF repository documentation.",
    },
    "multiwfn": {
        "url": "http://sobereva.com/multiwfn/",
        "license_note": "Keep locally; verify the Multiwfn license before redistribution.",
    },
    "cypforge": {
        "url": "https://github.com/ZiyanZhuang/CYPForge",
        "license_note": "Project documentation distributed with CYPForge.",
    },
}

PROFILE_KEYS = {
    "amber_sh",
    "multiwfn_bin",
    "wsl_user",
    "python_exe",
    "pyscf_python",
    "gpu4pyscf_python",
    "runs_dir",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore

            return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        except ImportError:
            pdftotext = shutil.which("pdftotext")
            if not pdftotext:
                raise RuntimeError("PDF indexing requires pypdf or the pdftotext executable.")
            completed = subprocess.run(
                [pdftotext, "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or "pdftotext failed")
            return completed.stdout
    text = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".html", ".htm"}:
        text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
    return text


def _chunks(text: str, max_chars: int = 2400) -> Iterable[tuple[str, str]]:
    heading = "Document"
    buffer: list[str] = []
    size = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if len(line) < 120 and (line.startswith("#") or line.isupper()):
            heading = line.lstrip("# ") or heading
        if buffer and size + len(line) + 1 > max_chars:
            yield heading, "\n".join(buffer)
            buffer, size = [], 0
        buffer.append(line)
        size += len(line) + 1
    if buffer:
        yield heading, "\n".join(buffer)


class LocalDocsIndex:
    def __init__(self, database: str | Path | None = None):
        self.database = Path(database) if database else DEFAULT_HOME / "docs" / "index.sqlite3"
        self.database.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS documents ("
            "id INTEGER PRIMARY KEY, source TEXT, version TEXT, path TEXT, sha256 TEXT, "
            "url TEXT, license_note TEXT, indexed_at TEXT)"
        )
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
            "document_id UNINDEXED, source, version, heading, content, tokenize='unicode61')"
        )
        return connection

    def index_file(self, path: str | Path, *, source: str, version: str = "") -> dict[str, Any]:
        source_key = source.lower()
        source_meta = SOURCE_REGISTRY.get(source_key, {"url": "", "license_note": "User-supplied local document."})
        document = Path(path).expanduser().resolve()
        if not document.is_file():
            raise FileNotFoundError(document)
        text = _extract_text(document)
        if not text.strip():
            raise ValueError(f"No indexable text extracted from {document}")
        digest = _sha256(document)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM documents WHERE path=? AND sha256=?", (str(document), digest)
            ).fetchone()
            if existing:
                return {"status": "unchanged", "document_id": existing[0], "path": str(document), "sha256": digest}
            old_ids = [row[0] for row in connection.execute("SELECT id FROM documents WHERE path=?", (str(document),))]
            for old_id in old_ids:
                connection.execute("DELETE FROM chunks WHERE document_id=?", (old_id,))
            connection.execute("DELETE FROM documents WHERE path=?", (str(document),))
            cursor = connection.execute(
                "INSERT INTO documents(source,version,path,sha256,url,license_note,indexed_at) VALUES(?,?,?,?,?,?,?)",
                (source_key, version, str(document), digest, source_meta["url"], source_meta["license_note"], _utc_now()),
            )
            document_id = int(cursor.lastrowid)
            rows = [(document_id, source_key, version, heading, content) for heading, content in _chunks(text)]
            connection.executemany(
                "INSERT INTO chunks(document_id,source,version,heading,content) VALUES(?,?,?,?,?)", rows
            )
        return {
            "status": "indexed",
            "document_id": document_id,
            "path": str(document),
            "sha256": digest,
            "chunk_count": len(rows),
        }

    def query(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        terms = re.findall(r"[A-Za-z0-9_.+-]{2,}", query)
        if not terms:
            return []
        expression = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:20])
        sql = (
            "SELECT c.source,c.version,c.heading,snippet(chunks,4,'[',']',' ... ',18),"
            "d.path,d.url,d.sha256,bm25(chunks) "
            "FROM chunks c JOIN documents d ON d.id=c.document_id "
            "WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?"
        )
        with self._connect() as connection:
            rows = connection.execute(sql, (expression, int(limit))).fetchall()
        return [
            {
                "source": row[0], "version": row[1], "heading": row[2], "snippet": row[3],
                "path": row[4], "url": row[5], "sha256": row[6], "score": row[7],
            }
            for row in rows
        ]


def load_profile(path: str | Path | None = None) -> dict[str, Any]:
    profile_path = Path(path) if path else DEFAULT_HOME / "profile.json"
    if not profile_path.is_file():
        return {"schema": "cypforge.user_profile.v1", "values": {}}
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(data.get("values", {}), dict):
        raise ValueError(f"Invalid CYPForge profile: {profile_path}")
    return data


def update_profile(assignments: list[str], path: str | Path | None = None) -> dict[str, Any]:
    profile_path = Path(path) if path else DEFAULT_HOME / "profile.json"
    profile = load_profile(profile_path)
    values = profile.setdefault("values", {})
    for assignment in assignments:
        if "=" not in assignment:
            raise ValueError(f"Invalid profile assignment '{assignment}'; expected KEY=VALUE")
        key, value = assignment.split("=", 1)
        key = key.strip()
        normalized_key = key.lower().replace("-", "_")
        if normalized_key not in PROFILE_KEYS:
            allowed = ", ".join(sorted(PROFILE_KEYS))
            raise ValueError(f"Unsupported profile key {key!r}; allowed keys: {allowed}")
        values[normalized_key] = value.strip()
    profile["schema"] = "cypforge.user_profile.v1"
    profile["updated_at_utc"] = _utc_now()
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {**profile, "profile_path": str(profile_path)}


def build_run_diagnosis(run_root: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    root = Path(run_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    config_path = root / "run_config.json"
    manifest_path = root / "run_manifest.json"
    if not config_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("A CYPForge run requires run_config.json and run_manifest.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    replacements = {
        str(root): "<RUN_ROOT>",
        str(root).replace("\\", "/"): "<RUN_ROOT>",
        str(Path.home()): "<HOME>",
        str(Path.home()).replace("\\", "/"): "<HOME>",
    }
    project_root = str(config.get("project_root", ""))
    if project_root:
        replacements[project_root] = "<PROJECT_ROOT>"
        replacements[project_root.replace("\\", "/")] = "<PROJECT_ROOT>"

    def redact_text(value: str) -> str:
        redacted = value
        for source, replacement in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            if source:
                redacted = redacted.replace(source, replacement)
        redacted = re.sub(
            r"(?i)\b(password|secret|token|api[_-]?key|access[_-]?key)\s*[:=]\s*[^\s,;]+",
            lambda match: f"{match.group(1)}=<REDACTED>",
            redacted,
        )
        redacted = re.sub(r"(?i)\b[A-Z]:[\\/][^\s\"'<>|]+", "<LOCAL_PATH>", redacted)
        redacted = re.sub(
            r"(?<![:\w])/(?:home|Users|data|mnt|opt|tmp|var|private)/[^\s\"'<>|]+",
            "<LOCAL_PATH>",
            redacted,
        )
        return redacted

    def redact_object(value: Any, key: str = "") -> Any:
        key_lower = key.lower()
        if any(part in key_lower for part in ("password", "secret", "token", "api_key", "access_key", "private_key")):
            return "<REDACTED>"
        if isinstance(value, dict):
            return {str(child_key): redact_object(child_value, str(child_key)) for child_key, child_value in value.items()}
        if isinstance(value, list):
            return [redact_object(item, key) for item in value]
        if isinstance(value, str):
            if any(part in key_lower for part in ("path", "root", "pdb", "sdf", "mol2", "frcmod", "bin", "amber_sh")):
                return Path(value).name if value else value
            return redact_text(value)
        return value

    failures: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".log", ".out", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        hits = [line.strip() for line in text.splitlines() if re.search(r"\b(error|fatal|traceback|nan)\b", line, re.I)]
        if hits:
            failures.append({"path": str(path.relative_to(root)), "matches": [redact_text(hit) for hit in hits[:20]]})
    public_config = redact_object(config)
    report = {
        "schema": "cypforge.run_diagnosis.v1",
        "created_at_utc": _utc_now(),
        "run_name": config.get("run_name", root.name),
        "workflow_status": manifest.get("workflow_status"),
        "config_public": public_config,
        "modules": redact_object(manifest.get("modules", {})),
        "failure_signatures": failures,
        "rerun": [
            f"cypforge status {config.get('run_name', root.name)} --run-root <RUN_ROOT>",
            f"cypforge context {config.get('run_name', root.name)} --run-root <RUN_ROOT>",
        ],
    }
    output_path = Path(output) if output else root / "run_diagnosis.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
