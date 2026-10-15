"""Stage the prepared host with the explicitly selected, unchanged ligand pose."""

import json
from pathlib import Path

from ..heme_mapping_leapin import _read_entries, _write_pdb
from ..io import sha256_file, write_json
from ..ligand_gpu4pyscf_esp import extract_ligand_from_complex_pdb


def stage_prepared_ligand_complex(run_root: str, ligand_resname: str, ligand_chain: str) -> None:
    root = Path(run_root)
    prepared = root / "01_heme_only/prepared_heme_complex.pdb"
    report_path = root / "01_heme_only/prepare_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    # The effective Core-1 source also preserves explicitly confirmed trimming.
    pose_source = Path(report["parameters"]["pdb_path"])
    output = root / "10_ligand_gpu4pyscf_esp"
    ligand = output / "confirmed_ligand_pose.pdb"
    extract_ligand_from_complex_pdb(
        complex_pdb=pose_source, ligand_resname=ligand_resname,
        ligand_chain=ligand_chain, output_pdb=ligand,
    )
    ligand_atoms = _read_entries(ligand)
    identities = {(atom["chain"], atom["resid"], atom["line"][26:27]) for atom in ligand_atoms}
    if len(identities) != 1:
        raise ValueError("Ligand selector must identify exactly one residue, including insertion code.")
    host_atoms = _read_entries(prepared)
    if any(atom["resname"] == ligand_resname and atom["chain"] == ligand_chain for atom in host_atoms):
        raise ValueError("Selected ligand already occurs in the prepared host.")
    staged = output / "prepared_ligand_complex.pdb"
    _write_pdb(staged, [atom["line"] for atom in host_atoms + ligand_atoms])
    write_json(output / "complex_pose_staging_manifest.json", {
        "schema": "cypforge.complex_pose_staging.v1", "status": "prepared",
        "inputs": {str(path): sha256_file(path) for path in (prepared, report_path, pose_source)},
        "output_files": {"complex_pdb": str(staged), "ligand_pose": str(ligand)},
        "ligand_resname": ligand_resname, "ligand_chain": ligand_chain,
        "host_atom_count": len(host_atoms), "ligand_atom_count": len(ligand_atoms),
        "policy": "Prepared host coordinates and selected ligand coordinates are unchanged; SDF remains chemistry source.",
    })
