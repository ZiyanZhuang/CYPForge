from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .heme_mapping_leapin import _read_entries, _write_text


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _rewrite_resname(line: str, resname: str) -> str:
    return line[:17] + f"{resname:>3s}" + line[20:]


def _source_residue_map(entries: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    mapping: dict[int, dict[str, Any]] = {}
    current_leap_resid = 0
    seen: set[tuple[str, int, str]] = set()
    for entry in entries:
        if entry["record"] != "ATOM":
            continue
        key = (entry["chain"], entry["resid"], entry["resname"])
        if key not in seen:
            seen.add(key)
            current_leap_resid += 1
            mapping[current_leap_resid] = {
                "current_resid": current_leap_resid,
                "current_resname": "CYM" if entry["resname"] == "CYP" else entry["resname"],
                "original_chain": entry["chain"],
                "original_resid": entry["resid"],
                "original_resname": entry["resname"],
            }
    return mapping


def _parse_protonation_changes(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    changes = data.get("recommended_changes", [])
    if not isinstance(changes, list):
        raise ValueError(f"Invalid recommended_changes in {path}")
    parsed: list[dict[str, Any]] = []
    for change in changes:
        parsed.append(
            {
                "current_resid": int(change["assembled_resid"]),
                "original_chain": str(change.get("original_chain", "")),
                "original_resid": int(change["original_resid"]),
                "from": str(change["from"]),
                "to": str(change["to"]),
                "priority": str(change.get("priority", "unspecified")),
                "reason": str(change.get("reason", "")),
            }
        )
    return parsed


def _pdb_residue_summary(path: Path, residues: list[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for entry in _read_entries(path):
        if entry["resid"] not in residues:
            continue
        row = out.setdefault(
            entry["resid"],
            {
                "current_resid": entry["resid"],
                "resname": entry["resname"],
                "atom_count": 0,
                "atoms": [],
            },
        )
        row["atom_count"] += 1
        row["atoms"].append(entry["atom"])
    return out


def _preleap_resname_matches(found: str, expected_from: str) -> bool:
    if found == expected_from:
        return True
    return expected_from in {"HID", "HIE", "HIP"} and found == "HIS"


def _expected_residue_checks(
    ligand_manifest: dict[str, Any],
    decision_data: dict[str, Any],
    changes: list[dict[str, Any]],
    residue_summary: dict[int, dict[str, Any]],
) -> dict[int, dict[str, str]]:
    expected: dict[int, dict[str, str]] = {}
    for change in changes:
        expected[change["current_resid"]] = {
            "expected_resname": change["to"],
            "source": "recommended_changes",
        }

    for row in decision_data.get("expected_residue_checks", []):
        resid = int(row["assembled_resid"])
        expected[resid] = {
            "expected_resname": str(row["resname"]),
            "source": "expected_residue_checks",
        }

    for row in decision_data.get("watchlist_no_immediate_change", []):
        if "assembled_resid" not in row or "residue" not in row:
            continue
        resid = int(row["assembled_resid"])
        expected.setdefault(
            resid,
            {
                "expected_resname": str(row["residue"]),
                "source": "watchlist_no_immediate_change",
            },
        )

    proximal = ligand_manifest.get("residues", {}).get("proximal_cym", {})
    if "leap_resid" in proximal:
        expected.setdefault(
            int(proximal["leap_resid"]),
            {
                "expected_resname": "CYM",
                "source": "ligand_mapping_manifest.proximal_cym",
            },
        )

    return expected


TITRATABLE_RESNAMES = {
    "CYS", "CYM", "CYX", "CYP",
    "HIS", "HID", "HIE", "HIP",
    "GLU", "GLH",
    "ASP", "ASH",
    "LYS", "LYN",
    "TYR",
    "ARG",
}

EXPLICIT_PROTONATION_RESNAMES = {
    "CYM", "CYX", "CYP", "HID", "HIE", "HIP", "GLH", "ASH", "LYN",
}

ALLOWED_PROTONATION_TRANSITIONS = {
    "CYS": {"CYS", "CYM", "CYX"},
    "CYM": {"CYS", "CYM", "CYX"},
    "CYX": {"CYS", "CYM", "CYX"},
    "CYP": {"CYS", "CYM", "CYX"},
    "HIS": {"HID", "HIE", "HIP"},
    "HID": {"HID", "HIE", "HIP"},
    "HIE": {"HID", "HIE", "HIP"},
    "HIP": {"HID", "HIE", "HIP"},
    "GLU": {"GLU", "GLH"},
    "GLH": {"GLU", "GLH"},
    "ASP": {"ASP", "ASH"},
    "ASH": {"ASP", "ASH"},
    "LYS": {"LYS", "LYN"},
    "LYN": {"LYS", "LYN"},
    "TYR": {"TYR"},
    "ARG": {"ARG"},
}


def _find_titratable_residues(pdb_path: Path) -> list[dict[str, Any]]:
    """Scan a PDB for titratable residues and report their current state."""
    by_resid: dict[tuple[int, int, str], dict[str, Any]] = {}
    chain_field = ""

    for line in pdb_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        resid = int(line[22:26])
        chain = (line[21].strip() or "A")
        resname = line[17:20].strip()
        if resname not in TITRATABLE_RESNAMES:
            continue
        key = (resid, chain, resname)
        row = by_resid.setdefault(key, {
            "resid": resid,
            "chain": chain,
            "resname": resname,
            "record_type": "ATOM" if line.startswith("ATOM") else "HETATM",
            "atom_count": 0,
        })
        row["atom_count"] += 1

    return sorted(by_resid.values(), key=lambda r: (r["chain"], r["resid"]))


def recommend_protonation_states(
    *,
    ligand_mapping_manifest_json: str | Path,
    original_prepared_pdb: str | Path,
    output_dir: str | Path,
    ph: float = 7.4,
    evidence_json: str | Path | None = None,
) -> dict[str, Any]:
    """Write a review list without changing residue names.

    Explicit Amber protonation names are retained as recommendations. Generic
    titratable residue names remain unresolved unless an external pKa/H++
    evidence record supplies a target state. This function never applies a
    recommendation.
    """
    ligand_manifest_path = Path(ligand_mapping_manifest_json)
    original_pdb_path = Path(original_prepared_pdb)
    for path, label in (
        (ligand_manifest_path, "ligand mapping manifest"),
        (original_pdb_path, "original prepared PDB"),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label}: {path}")

    ligand_manifest = _read_json(ligand_manifest_path)
    combined_pdb = Path(ligand_manifest["output_files"]["combined_pdb"])
    if not combined_pdb.is_file():
        raise FileNotFoundError(f"Ligand mapping combined PDB is not readable: {combined_pdb}")

    source_map = _source_residue_map(_read_entries(original_pdb_path))
    external: dict[tuple[str, int], dict[str, Any]] = {}
    if evidence_json:
        evidence_path = Path(evidence_json)
        if not evidence_path.is_file():
            raise FileNotFoundError(f"Missing protonation evidence JSON: {evidence_path}")
        evidence_data = _read_json(evidence_path)
        records = evidence_data.get("recommendations", evidence_data)
        if not isinstance(records, list):
            raise ValueError("Protonation evidence must be a list or contain a recommendations list.")
        for row in records:
            chain = str(row.get("chain", "")).strip() or "A"
            resid = int(row["resid"])
            current = str(row.get("current_resname", "")).upper()
            target = str(row["recommended_resname"]).upper()
            if current:
                allowed = ALLOWED_PROTONATION_TRANSITIONS.get(current, {current})
                if target not in allowed:
                    raise ValueError(f"Unsupported protonation transition {chain}:{current}{resid}={target}")
            identity = (chain, resid)
            if identity in external:
                raise ValueError(f"Duplicate protonation evidence for {chain}:{resid}")
            external[identity] = dict(row)

    recommendations: list[dict[str, Any]] = []
    for residue in _find_titratable_residues(combined_pdb):
        current = residue["resname"]
        assembled_resid = int(residue["resid"])
        mapped = source_map.get(assembled_resid)
        if mapped is None:
            raise ValueError(f"No original residue identity for assembled residue {assembled_resid} {current}")
        original_chain = mapped["original_chain"] or "A"
        original_resid = int(mapped["original_resid"])
        mapped_current = str(mapped["current_resname"])
        compatible = (
            current == mapped_current
            or (mapped_current == "HIS" and current in {"HID", "HIE", "HIP"})
            or (mapped_current == "CYM" and current in {"CYP", "CYM"})
        )
        if not compatible:
            raise ValueError(
                f"Residue identity mismatch for assembled {assembled_resid}: "
                f"original={original_chain}:{mapped_current}{original_resid}; combined={current}"
            )
        evidence = external.get((original_chain, original_resid))
        if evidence:
            evidence_current = str(evidence.get("current_resname", "")).upper()
            if evidence_current and evidence_current not in {current, mapped_current, mapped["original_resname"]}:
                raise ValueError(
                    f"Protonation evidence identity mismatch for {original_chain}:{original_resid}: "
                    f"evidence={evidence_current}; current={current}"
                )
            target = str(evidence["recommended_resname"]).upper()
            allowed = ALLOWED_PROTONATION_TRANSITIONS.get(current, {current})
            if target not in allowed:
                raise ValueError(
                    f"Unsupported protonation transition {original_chain}:{current}{original_resid}={target}"
                )
            disposition = "candidate_change" if target != current else "retain_current"
            source = str(evidence.get("source", "external_evidence"))
            rationale = str(evidence.get("reason", "External protonation evidence."))
        elif current in EXPLICIT_PROTONATION_RESNAMES:
            target = "CYM" if current == "CYP" else current
            disposition = "retain_current"
            source = "explicit_input_residue_name"
            rationale = "The input already specifies an Amber protonation-state residue name."
        else:
            target = None
            disposition = "manual_review"
            source = "none"
            rationale = "No site-specific pKa or hydrogen-bond evidence was supplied."
        recommendations.append({
            "selector": f"{original_chain}:{current}{original_resid}",
            "chain": original_chain,
            "resid": original_resid,
            "assembled_resid": assembled_resid,
            "original_chain": original_chain,
            "original_resid": original_resid,
            "current_resname": current,
            "recommended_resname": target,
            "disposition": disposition,
            "evidence_source": source,
            "reason": rationale,
            "requires_user_confirmation": True,
        })

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "protonation_recommendations.json"
    report = {
        "schema": "cypforge.protonation_recommendations.v1",
        "status": "review_required",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "ph": ph,
        "input_files": {
            "ligand_mapping_manifest_json": str(ligand_manifest_path),
            "combined_pdb": str(combined_pdb),
            "original_prepared_pdb": str(original_pdb_path),
            "evidence_json": str(evidence_json) if evidence_json else None,
        },
        "recommendations": recommendations,
        "summary": {
            "residue_count": len(recommendations),
            "candidate_change_count": sum(r["disposition"] == "candidate_change" for r in recommendations),
            "manual_review_count": sum(r["disposition"] == "manual_review" for r in recommendations),
        },
        "policy": "Recommendations are advisory. CYPForge applies no residue rename without a user-approved decision.",
        "output_file": str(output_path),
    }
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def build_protonation_decision_from_selectors(
    *,
    original_prepared_pdb: str | Path,
    selectors: list[str],
    output_json: str | Path,
) -> dict[str, Any]:
    """Validate ``CHAIN:CURRENT123=TARGET`` selectors and write a decision JSON."""
    original_path = Path(original_prepared_pdb)
    if not original_path.is_file():
        raise FileNotFoundError(f"Missing original prepared PDB: {original_path}")
    source_map = _source_residue_map(_read_entries(original_path))
    by_original: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in source_map.values():
        key = (row["original_chain"] or "A", row["original_resid"], row["current_resname"])
        if key in by_original:
            raise ValueError(f"Non-unique original residue identity: {key}")
        by_original[key] = row
    changes: list[dict[str, Any]] = []
    selected_residues: set[int] = set()
    import re
    pattern = re.compile(r"^([^:]):([A-Za-z]{3})(-?\d+)=([A-Za-z]{3})$")
    for selector in selectors:
        match = pattern.fullmatch(selector.strip())
        if not match:
            raise ValueError(f"Invalid selector '{selector}'; expected CHAIN:CURRENT123=TARGET")
        chain, current, resid_text, target = match.groups()
        current, target, resid = current.upper(), target.upper(), int(resid_text)
        mapped = by_original.get((chain, resid, current))
        if mapped is None and current == "CYM":
            mapped = by_original.get((chain, resid, "CYP"))
        if mapped is None:
            candidates = [row for row in source_map.values() if (row["original_chain"] or "A") == chain and row["original_resid"] == resid]
            found = sorted({row["current_resname"] for row in candidates})
            raise ValueError(f"Selector {selector} does not match the input residue; found={found or 'missing'}")
        allowed = ALLOWED_PROTONATION_TRANSITIONS.get(current, {current})
        if target not in allowed:
            raise ValueError(f"Unsupported protonation transition {selector}")
        if mapped["current_resid"] in selected_residues:
            raise ValueError(f"Duplicate protonation selector for assembled residue {mapped['current_resid']}")
        selected_residues.add(mapped["current_resid"])
        changes.append({
            "assembled_resid": mapped["current_resid"],
            "original_chain": chain,
            "original_resid": resid,
            "from": current,
            "to": target,
            "priority": "user_confirmed",
            "reason": f"User-confirmed selector {selector}",
        })
    decision = {
        "schema": "cypforge.protonation_decision.v1",
        "status": "user_confirmed",
        "recommended_changes": changes,
        "expected_residue_checks": [
            {"assembled_resid": row["assembled_resid"], "resname": row["to"]}
            for row in changes
        ],
        "watchlist_no_immediate_change": [],
        "policy": "Only the listed user-confirmed residue-state changes may be applied.",
    }
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return decision


def analyze_protonation_state(
    *,
    ligand_mapping_manifest_json: str | Path,
    original_prepared_pdb: str | Path,
    protonation_decision_json: str | Path | None = None,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Analyze current protonation state without modifying any files.

    Produces a structured report of:
    - All titratable residues found in the PDB
    - What changes the decision JSON would recommend
    - What the post-change state would be
    - The effective net charge impact of proposed changes

    No files are written beyond the analysis report manifest.
    """
    ligand_manifest_path = Path(ligand_mapping_manifest_json)
    original_pdb_path = Path(original_prepared_pdb)
    out_dir = Path(output_dir)
    for path, label in [
        (ligand_manifest_path, "ligand mapping manifest"),
        (original_pdb_path, "original prepared PDB"),
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label}: {path}")

    ligand_manifest = _read_json(ligand_manifest_path)
    source_combined_pdb = Path(ligand_manifest["output_files"]["combined_pdb"])
    if not source_combined_pdb.is_file():
        raise FileNotFoundError(f"Ligand mapping combined PDB is not readable: {source_combined_pdb}")

    titratable = _find_titratable_residues(source_combined_pdb)
    changes: list[dict[str, Any]] = []
    decision_data: dict[str, Any] = {}
    if protonation_decision_json:
        decision_path = Path(protonation_decision_json)
        if decision_path.is_file():
            decision_data = _read_json(decision_path)
            changes = _parse_protonation_changes(decision_path)

    change_by_resid = {row["current_resid"]: row for row in changes}

    residues_analysis: list[dict[str, Any]] = []
    charge_delta = 0
    for residue in titratable:
        analysis = dict(residue)
        change = change_by_resid.get(residue["resid"])
        if change:
            analysis["proposed_change"] = {
                "from": change["from"],
                "to": change["to"],
                "priority": change["priority"],
                "reason": change["reason"],
                "would_change": change["to"] != residue["resname"],
            }
            analysis["current_matches_expected"] = _preleap_resname_matches(residue["resname"], change["from"])
        else:
            analysis["proposed_change"] = None
            analysis["current_matches_expected"] = True
        residues_analysis.append(analysis)

    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "cypforge.protonation_analysis.v1",
        "status": "success",
        "analyze_only": True,
        "input_files": {
            "ligand_mapping_manifest_json": str(ligand_manifest_path),
            "source_combined_pdb": str(source_combined_pdb),
            "original_prepared_pdb": str(original_pdb_path),
            "protonation_decision_json": str(protonation_decision_json) if protonation_decision_json else None,
        },
        "pdb_summary": {
            "total_titratable_residues": len(titratable),
            "by_type": {
                resname: sum(1 for r in titratable if r["resname"] == resname)
                for resname in sorted({r["resname"] for r in titratable})
            },
        },
        "proposed_changes": {
            "total": len(changes),
            "active_changes": [
                c for c in changes
                if c["from"] != c["to"]
            ],
            "noop_changes": [
                c for c in changes
                if c["from"] == c["to"]
            ],
        },
        "residues": residues_analysis,
        "expected_dry_charge_delta": decision_data.get("expected_dry_charge_change") if decision_data else None,
        "policy": (
            "Analysis only - no PDB files, LEaP inputs, or parameter files were modified. "
            "To apply the proposed changes, re-run without --analyze-only and provide a "
            "protonation decision JSON with 'auto-apply' intent."
        ),
    }
    report_path = out_dir / "protonation_analysis_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def finalize_complex_protonation_mapping(
    *,
    ligand_mapping_manifest_json: str | Path,
    original_prepared_pdb: str | Path,
    protonation_decision_json: str | Path,
    output_dir: str | Path,
    keep_watchlist: bool = True,
) -> dict[str, Any]:
    """Apply final protein residue-state renames to ligand-aware LEaP inputs.

    This is the third-core integration stage. It consumes the already mapped
    ligand/heme LEaP package and only changes protein residue names selected by
    the protonation audit. It does not modify heme, proximal-cysteine, or ligand
    parameter files.
    """
    ligand_manifest_path = Path(ligand_mapping_manifest_json)
    original_pdb_path = Path(original_prepared_pdb)
    decision_path = Path(protonation_decision_json)
    out_dir = Path(output_dir)
    for path, label in [
        (ligand_manifest_path, "ligand mapping manifest"),
        (original_pdb_path, "original prepared PDB"),
        (decision_path, "protonation decision JSON"),
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label}: {path}")

    ligand_manifest = _read_json(ligand_manifest_path)
    source_combined_pdb = Path(ligand_manifest["output_files"]["combined_pdb"])
    source_leapin = Path(ligand_manifest["output_files"]["leapin"])
    if not source_combined_pdb.is_file() or not source_leapin.is_file():
        raise FileNotFoundError("Ligand mapping output PDB/leapin is not readable.")

    decision_data = _read_json(decision_path)
    changes = _parse_protonation_changes(decision_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_map = _source_residue_map(_read_entries(original_pdb_path))
    applied: list[dict[str, Any]] = []
    errors: list[str] = []
    change_by_resid = {row["current_resid"]: row for row in changes}

    final_lines: list[str] = []
    mismatch_keys: set[tuple[int, str, str]] = set()
    for raw in source_combined_pdb.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not raw.startswith(("ATOM", "HETATM")):
            final_lines.append(raw)
            continue
        resid = int(raw[22:26])
        resname = raw[17:20].strip()
        change = change_by_resid.get(resid)
        if change is None:
            final_lines.append(raw)
            continue
        if raw.startswith("HETATM"):
            errors.append(f"Refusing to rename HETATM residue {resid} {resname}")
            final_lines.append(raw)
            continue
        if not _preleap_resname_matches(resname, change["from"]):
            mismatch = (resid, change["from"], resname)
            if mismatch not in mismatch_keys:
                mismatch_keys.add(mismatch)
                errors.append(f"Residue {resid} expected {change['from']} before rename, found {resname}")
            final_lines.append(raw)
            continue
        final_lines.append(_rewrite_resname(raw, change["to"]))

    final_pdb = out_dir / "complex_ligand_protonation_final.pdb"
    _write_text(final_pdb, "\n".join(final_lines).rstrip() + "\n")

    final_leapin = out_dir / "complex_protonation_final_leap.in"
    leap_text = source_leapin.read_text(encoding="utf-8")
    leap_text = leap_text.replace(source_combined_pdb.name, final_pdb.name)
    leap_text = leap_text.replace("system_lig_dry", "system_lig_protstate_dry")
    _write_text(final_leapin, leap_text)

    copied_parameter_files: list[str] = []
    for source_key in ("heme_mol2", "heme_frcmod", "ligand_mol2", "ligand_frcmod"):
        source = ligand_manifest.get("parameter_files", {}).get(source_key)
        if not source:
            continue
        src_path = Path(source)
        if not src_path.is_file():
            errors.append(f"Missing parameter file {source_key}: {src_path}")
            continue
        target = out_dir / src_path.name
        shutil.copyfile(src_path, target)
        copied_parameter_files.append(str(target))

    candidate_check_resids = set(change_by_resid)
    candidate_check_resids.update(
        int(row["assembled_resid"])
        for row in decision_data.get("expected_residue_checks", [])
        if "assembled_resid" in row
    )
    candidate_check_resids.update(
        int(row["assembled_resid"])
        for row in decision_data.get("watchlist_no_immediate_change", [])
        if "assembled_resid" in row
    )
    proximal = ligand_manifest.get("residues", {}).get("proximal_cym", {})
    if "leap_resid" in proximal:
        candidate_check_resids.add(int(proximal["leap_resid"]))
    final_resids = sorted(candidate_check_resids)
    residue_summary = _pdb_residue_summary(final_pdb, final_resids)
    expected_final = _expected_residue_checks(ligand_manifest, decision_data, changes, residue_summary)
    expected_checks: dict[str, Any] = {}
    for resid, expected_row in expected_final.items():
        expected = expected_row["expected_resname"]
        found = residue_summary.get(resid, {}).get("resname")
        expected_checks[str(resid)] = {
            "expected_resname": expected,
            "found_resname": found,
            "status": "passed" if found == expected else "failed",
            "source": expected_row["source"],
        }
        if found != expected:
            errors.append(f"Final residue {resid} expected {expected}, found {found}")

    for change in changes:
        mapped = source_map.get(change["current_resid"])
        if mapped is None:
            errors.append(f"No original/current mapping for current residue {change['current_resid']}")
            continue
        if mapped["original_resid"] != change["original_resid"]:
            errors.append(
                f"Residue mapping mismatch for current {change['current_resid']}: "
                f"decision original {change['original_resid']} != mapped original {mapped['original_resid']}"
            )
        if change.get("original_chain") and mapped["original_chain"] != change["original_chain"]:
            errors.append(
                f"Residue mapping mismatch for current {change['current_resid']}: "
                f"decision chain {change['original_chain']} != mapped chain {mapped['original_chain']}"
            )
        applied.append({**change, "source_mapping": mapped})

    manifest = {
        "schema": "cypforge.complex_protonation_finalize.v1",
        "status": "failed" if errors else "success",
        "input_files": {
            "ligand_mapping_manifest_json": str(ligand_manifest_path),
            "source_combined_pdb": str(source_combined_pdb),
            "source_leapin": str(source_leapin),
            "original_prepared_pdb": str(original_pdb_path),
            "protonation_decision_json": str(decision_path),
        },
        "output_files": {
            "final_pdb": str(final_pdb),
            "final_leapin": str(final_leapin),
            "manifest_json": str(out_dir / "protonation_finalize_manifest.json"),
            "copied_parameter_files": copied_parameter_files,
        },
        "protonation_changes": applied,
        "watchlist_policy": "record_only" if keep_watchlist else "ignored",
        "watchlist_no_immediate_change": decision_data.get("watchlist_no_immediate_change", []),
        "expected_final_residue_checks": expected_checks,
        "residue_summary": {str(k): v for k, v in sorted(residue_summary.items())},
        "expected_dry_charge_change": decision_data.get(
            "expected_dry_charge_change",
            {
                "old_total_charge": None,
                "expected_new_total_charge": None,
                "reason": "No global residue-charge delta is inferred by default; provide expected_dry_charge_change in the decision JSON when solvation ion-count prediction is required.",
            },
        ),
        "parameter_policy": "Heme, axial-cysteine, and ligand mol2/frcmod files are copied from second-core ligand mapping outputs and are not regenerated here.",
        "errors": errors,
    }
    _write_text(Path(manifest["output_files"]["manifest_json"]), json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    if errors:
        raise ValueError(f"Complex protonation finalization failed: {errors}")
    return manifest
