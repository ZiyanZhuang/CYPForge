#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cypforge_core import prepare_complex_solvation_ionization


def _default_amber_source() -> str:
    if os.environ.get("AMBER_SH"):
        return os.environ["AMBER_SH"]
    if os.environ.get("AMBERHOME"):
        return str(Path(os.environ["AMBERHOME"]) / "amber.sh")
    raise ValueError(
        "Amber environment not configured for stress test. "
        "Set AMBER_SH or AMBERHOME."
    )


DEFAULT_CASES: list[dict[str, Any]] = [
    {"case_id": "default_ff19_gaff2_tip3p_oct10"},
    {"case_id": "ff14sb_tip3p_oct10", "protein_force_field": "ff14SB"},
    {"case_id": "tip3p_oct8", "buffer_a": 8.0},
    {"case_id": "tip3p_oct12", "buffer_a": 12.0},
    {"case_id": "tip3p_box10", "box_type": "box"},
    {"case_id": "spce_oct10", "water_model": "SPCBOX", "water_leaprc": "leaprc.water.spce"},
    {"case_id": "tip4pew_oct10", "water_model": "TIP4PEWBOX", "water_leaprc": "leaprc.water.tip4pew"},
    {"case_id": "opc_oct10", "water_model": "OPCBOX", "water_leaprc": "leaprc.water.opc"},
    {"case_id": "opc3_oct10", "water_model": "OPC3BOX", "water_leaprc": "leaprc.water.opc"},
]


def _windows_to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{rest}"


def _wsl_argv(wsl_user: str | None, command: str) -> list[str]:
    """Build a wsl.exe argv that omits -u when wsl_user is empty/None."""
    argv = ["wsl"]
    if wsl_user:
        argv.extend(["-u", wsl_user])
    argv.extend(["-e", "bash", "-lc", command])
    return argv


def _run_tleap(case_dir: Path, *, amber_source: str, wsl_user: str | None) -> dict[str, Any]:
    wsl_case_dir = _windows_to_wsl_path(case_dir)
    command = f"source {amber_source} && cd '{wsl_case_dir}' && tleap -f complex_solvation_ionization_leap.in > leap.log 2>&1"
    proc = subprocess.run(
        _wsl_argv(wsl_user, command),
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    leap_log = case_dir / "leap.log"
    parsed = _parse_leap_log(leap_log)
    parsed.update(
        {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "prmtop_exists": (case_dir / "system_lig_solv.prmtop").is_file(),
            "rst7_exists": (case_dir / "system_lig_solv.rst7").is_file(),
            "tleap_pdb_exists": (case_dir / "system_lig_solv_tleap.pdb").is_file(),
        }
    )
    parsed["status"] = (
        "success"
        if proc.returncode == 0
        and parsed.get("errors") == 0
        and parsed["prmtop_exists"]
        and parsed["rst7_exists"]
        else "failed"
    )
    if parsed["status"] == "success":
        parsed["cpptraj"] = _run_cpptraj_smoke(case_dir, amber_source=amber_source, wsl_user=wsl_user)
        if parsed["cpptraj"]["status"] != "success":
            parsed["status"] = "failed"
    return parsed


def _run_cpptraj_smoke(case_dir: Path, *, amber_source: str, wsl_user: str | None) -> dict[str, Any]:
    cpptraj_input = case_dir / "cpptraj_solv_smoke.in"
    cpptraj_input.write_text(
        "trajin system_lig_solv.rst7\n"
        "check\n"
        "go\n",
        encoding="utf-8",
    )
    wsl_case_dir = _windows_to_wsl_path(case_dir)
    command = f"source {amber_source} && cd '{wsl_case_dir}' && cpptraj -p system_lig_solv.prmtop -i cpptraj_solv_smoke.in > cpptraj_solv_smoke.log 2>&1"
    proc = subprocess.run(
        _wsl_argv(wsl_user, command),
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    log_path = case_dir / "cpptraj_solv_smoke.log"
    log_text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.is_file() else ""
    bad_bond = "bad bond" in log_text.lower()
    processed = "1 frames" in log_text or "1 frame" in log_text
    return {
        "returncode": proc.returncode,
        "log_exists": log_path.is_file(),
        "processed_frames": processed,
        "contains_bad_bond_warning": bad_bond,
        "status": "success" if proc.returncode == 0 and processed and not bad_bond else "failed",
    }


def _parse_leap_log(leap_log: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "log_exists": leap_log.is_file(),
        "errors": None,
        "warnings": None,
        "notes": None,
        "charges_seen": [],
        "ions_required": None,
        "water_residues_added_before_ion_replacement": None,
        "volume_A3": None,
        "initial_density_g_per_cc": None,
        "fatal_lines": [],
    }
    if not leap_log.is_file():
        return result
    text = leap_log.read_text(encoding="utf-8", errors="ignore")
    for charge in re.findall(r"Total unperturbed charge:\s*([-+0-9.eE]+)", text):
        result["charges_seen"].append(float(charge))
    match = re.search(r"Exiting LEaP: Errors = (\d+); Warnings = (\d+); Notes = (\d+)", text)
    if match:
        result["errors"] = int(match.group(1))
        result["warnings"] = int(match.group(2))
        result["notes"] = int(match.group(3))
    match = re.search(r"(\d+)\s+Cl-\s+ions required to neutralize", text)
    if match:
        result["ions_required"] = int(match.group(1))
    match = re.search(r"Volume:\s*([0-9.]+)\s*A\^3", text)
    if match:
        result["volume_A3"] = float(match.group(1))
    match = re.search(r"Density\s*([0-9.]+)\s*g/cc", text)
    if match:
        result["initial_density_g_per_cc"] = float(match.group(1))
    added = re.findall(r"Added\s+(\d+)\s+residues\.", text)
    if added:
        result["water_residues_added_before_ion_replacement"] = int(added[-1])
    result["fatal_lines"] = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"\b(fatal|unknown residue|missing parameters|Could not open)\b", line, re.IGNORECASE)
    ][:25]
    return result


def _case_options(case: dict[str, Any]) -> dict[str, Any]:
    options = dict(case)
    options.pop("case_id")
    options.pop("expect_success", None)
    options.pop("expectation_reason", None)
    return options


def main() -> int:
    parser = argparse.ArgumentParser(description="Run third-core solvation/ionization stress matrix without changing protonation states.")
    parser.add_argument("--protonation-manifest-json", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-tleap", action="store_true")
    parser.add_argument("--wsl-user", default=None, help="WSL username for tleap; falls back to the WSL distro's default user if omitted")
    parser.add_argument("--amber-source", default=_default_amber_source())
    parser.add_argument("--clean-output-root", action="store_true")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    if args.clean_output_root and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for case in DEFAULT_CASES:
        case_id = case["case_id"]
        case_dir = output_root / case_id
        expect_success = bool(case.get("expect_success", True))
        row: dict[str, Any] = {
            "case_id": case_id,
            "status": "not_started",
            "expect_success": expect_success,
            "expectation_reason": case.get("expectation_reason"),
            "options": _case_options(case),
        }
        try:
            manifest = prepare_complex_solvation_ionization(
                protonation_manifest_json=args.protonation_manifest_json,
                output_dir=case_dir,
                **_case_options(case),
            )
            row["prepare_status"] = manifest["status"]
            row["manifest_json"] = manifest["output_files"]["manifest_json"]
            row["solvation"] = manifest["solvation"]
            row["force_fields"] = manifest["force_fields"]
            row["ionization"] = manifest["ionization"]
            if args.run_tleap:
                row["tleap"] = _run_tleap(case_dir, amber_source=args.amber_source, wsl_user=args.wsl_user)
                row["status"] = row["tleap"]["status"]
            else:
                row["status"] = "prepared"
        except Exception as exc:  # noqa: BLE001 - matrix rows must record individual failures.
            row["status"] = "failed"
            row["error"] = repr(exc)
        row["expectation_met"] = (row["status"] in {"success", "prepared"}) == expect_success
        rows.append(row)

    unexpected_failures = [
        row for row in rows if row["expect_success"] and row["status"] == "failed"
    ]
    unexpected_successes = [
        row for row in rows if not row["expect_success"] and row["status"] in {"success", "prepared"}
    ]
    summary = {
        "schema": "cypforge.third_core_stress_matrix.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "protonation_manifest_json": str(Path(args.protonation_manifest_json)),
        "output_root": str(output_root),
        "protonation_policy": "fixed_upstream_manifest_no_residue_state_changes",
        "run_tleap": args.run_tleap,
        "case_count": len(rows),
        "pass_count": sum(1 for row in rows if row["expectation_met"]),
        "unexpected_failure_count": len(unexpected_failures),
        "unexpected_success_count": len(unexpected_successes),
        "raw_success_count": sum(1 for row in rows if row["status"] in {"success", "prepared"}),
        "raw_failure_count": sum(1 for row in rows if row["status"] == "failed"),
        "cases": rows,
    }
    summary_path = output_root / "third_core_stress_matrix_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not unexpected_failures and not unexpected_successes else 1


if __name__ == "__main__":
    raise SystemExit(main())
