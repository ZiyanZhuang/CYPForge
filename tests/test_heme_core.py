from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cypforge_core import (
    build_heme_mapping_and_leapin,
    build_ligand_mapping_and_leapin,
    check_ligand_pose_frame,
    default_pre_md_protocol_config,
    finalize_complex_protonation_mapping,
    parameterize_protein_heme_complex,
    prepare_complex_pre_md_equilibration,
    prepare_complex_solvation_ionization,
    validate_solvation_tleap_outputs,
    parameterize_selected_ligand_pose,
    prepare_gpu4pyscf_esp_job,
    prepare_heme,
    second_core_source_policy,
    trim_pdb_residue_ranges,
)
import cypforge_core.complex_global_audit as global_audit
from cypforge_core.ligand_gpu4pyscf_esp import resolve_amber_sh as resolve_gpu_amber_sh
from cypforge_core.ligand_gpu4pyscf_esp import resolve_multiwfn_bin
from cypforge_core.ligand_pose_parameterization import resolve_amber_sh as resolve_pose_amber_sh
from cypforge_core.ligand_gpu4pyscf_esp import (
    _write_sdf_order_complex_pose_mol2,
    map_sdf_atoms_to_complex_atoms,
    prepare_complex_sdf_ligand_resp_inputs,
    read_ligand_atoms,
)


REPO = Path(__file__).resolve().parents[1]
_FIXTURE_ROOT = Path(os.environ.get("CYPFORGE_TEST_FIXTURES", "/nonexistent"))
REAL_PDB = (
    _FIXTURE_ROOT
    / "experiment_01_cyp_heme_ligand_9_conditions"
    / "conditions"
    / "01_CYP2A6_nicotine_IC6"
    / "input"
    / "4EJJ_CYP2A6_nicotine_chainA_nowat.pdb"
)
EXAMPLE_NCT_MOL2 = _FIXTURE_ROOT / "examples" / "test_objects" / "4EJJ_NCT_IC6" / "inputs" / "NCT_target_heme_docked_esp.mol2"
EXAMPLE_NCT_CHARGES = _FIXTURE_ROOT / "examples" / "test_objects" / "4EJJ_NCT_IC6" / "inputs" / "NCT_hf631gstar_esp_charges.csv"
MODE11_HEAVY_ONLY = Path(os.environ.get("CYPFORGE_MODE11_FIXTURE", "/nonexistent"))


def test_local_heme_params_read_real_values():
    expected = {
        "IC6": (-1.5976, -0.4024, 0.2492, 0, 0),
        "DIOXY": (-2.5336, -0.4664, 0.0289, 1, 1),
        "CPDI": (-1.6141, -0.3859, 0.262, 1, 0),
    }
    for state, values in expected.items():
        manifest = prepare_heme(state)
        assert (
            manifest["heme_charge"],
            manifest["cyp_patch_charge"],
            manifest["fe_charge"],
            manifest["o1_count"],
            manifest["o2_count"],
        ) == values
        assert manifest["fe_atom_type"] == "fe"
        assert manifest["fe_s_bond"]["raw"].strip().startswith("fe-SH")


def test_heme_state_is_explicit():
    with pytest.raises(ValueError):
        parameterize_protein_heme_complex(REAL_PDB, heme_state="BAD", output_dir="unused")


def test_detect_heme_state_warns_when_manual_disagrees_with_pdb():
    import numpy as np
    from cypforge.heme.mapping import AtomRecord, detect_heme_state

    fe = AtomRecord(serial=1, name="FE", resname="HEM", chain="", resid=466,
                    coord=np.array([0.0, 0.0, 0.0]), element="FE")
    axial_o = AtomRecord(serial=2, name="O1", resname="HEM", chain="", resid=466,
                         coord=np.array([0.0, 0.0, 1.65]), element="O")

    cpdi_atoms = [fe, axial_o]
    ic6_atoms = [fe]

    mismatch = detect_heme_state(cpdi_atoms, manual_state="IC6")
    assert mismatch.state == "IC6"
    assert mismatch.method == "manual"
    assert mismatch.warning and "CPDI" in mismatch.warning

    agreeing = detect_heme_state(cpdi_atoms, manual_state="CPDI")
    assert agreeing.state == "CPDI" and agreeing.warning is None

    ic6_declared = detect_heme_state(ic6_atoms, manual_state="IC6")
    assert ic6_declared.state == "IC6" and ic6_declared.warning is None

    auto = detect_heme_state(cpdi_atoms, manual_state=None)
    assert auto.state == "CPDI" and auto.method == "auto"


def test_core1_optional_transmembrane_trim_removes_explicit_atom_ranges(tmp_path):
    pdb = tmp_path / "input.pdb"
    pdb.write_text(
        "ATOM      1  N   MET A   1       0.000   0.000   0.000  1.00  0.00           N\n"
        "ATOM      2  CA  MET A   1       1.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      3  N   ALA A   2       2.000   0.000   0.000  1.00  0.00           N\n"
        "ATOM      4  N   CYS A   3       3.000   0.000   0.000  1.00  0.00           N\n"
        "HETATM    5  FE  HEM B 500       4.000   0.000   0.000  1.00  0.00          FE\n"
        "END\n",
        encoding="utf-8",
    )

    report = trim_pdb_residue_ranges(pdb, tmp_path / "trimmed.pdb", "A:1-2", confirmed=True)
    trimmed = Path(report["trimmed_pdb"]).read_text(encoding="utf-8")

    assert report["removed_atom_count"] == 3
    assert report["removed_residue_count"] == 2
    assert "MET A   1" not in trimmed
    assert "ALA A   2" not in trimmed
    assert "CYS A   3" in trimmed
    assert "HEM B 500" in trimmed


def test_core1_transmembrane_trim_requires_explicit_confirmation(tmp_path):
    pdb = tmp_path / "input.pdb"
    pdb.write_text(
        "ATOM      1  N   MET A   1       0.000   0.000   0.000  1.00  0.00           N\n"
        "END\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="without explicit human confirmation"):
        trim_pdb_residue_ranges(pdb, tmp_path / "trimmed.pdb", "A:1-1")


def test_core1_parameterization_refuses_unconfirmed_transmembrane_trim(tmp_path):
    pdb = tmp_path / "input.pdb"
    pdb.write_text(
        "ATOM      1  N   MET A   1       0.000   0.000   0.000  1.00  0.00           N\n"
        "END\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="without explicit human confirmation"):
        parameterize_protein_heme_complex(
            pdb,
            heme_state="IC6",
            output_dir=tmp_path / "out",
            trim_transmembrane_ranges="A:1-1",
        )


@pytest.mark.skipif(not REAL_PDB.is_file(), reason="real 4EJJ input PDB is not present (set CYPFORGE_TEST_FIXTURES)")
def test_real_protein_heme_pre_tleap_parameterization(tmp_path):
    expected_oxygen_counts = {
        "IC6": (0, 0),
        "DIOXY": (1, 1),
        "CPDI": (1, 0),
    }
    for state, (o1_count, o2_count) in expected_oxygen_counts.items():
        result = parameterize_protein_heme_complex(
            REAL_PDB,
            heme_state=state,
            output_dir=tmp_path / state,
        )
        prepared_pdb = Path(result["prepared_pdb"])
        assert result["status"] == "success"
        assert prepared_pdb.is_file()
        assert os.path.join("heme_params", state, "CYP.mol2") in result["cyp_mol2"]
        assert os.path.join("heme_params", state, f"{state}.frcmod") in result["frcmod"]

        heme_o1 = 0
        heme_o2 = 0
        cyp_sg = 0
        for line in prepared_pdb.read_text(encoding="utf-8").splitlines():
            if not (line.startswith("ATOM") or line.startswith("HETATM")):
                continue
            atom = line[12:16].strip()
            resname = line[17:20].strip()
            if resname == "HEM" and atom == "O1":
                heme_o1 += 1
            if resname == "HEM" and atom == "O2":
                heme_o2 += 1
            if resname == "CYP" and atom == "SG":
                cyp_sg += 1

        assert (heme_o1, heme_o2) == (o1_count, o2_count)
        assert cyp_sg == 1
        assert result["fe_s_measured"]["fe_s_distance"] > 2.0


@pytest.mark.skipif(not REAL_PDB.is_file(), reason="real 4EJJ input PDB is not present (set CYPFORGE_TEST_FIXTURES)")
def test_real_heme_mapping_and_leapin_uses_contiguous_residue_index(tmp_path):
    heme = parameterize_protein_heme_complex(
        REAL_PDB,
        heme_state="DIOXY",
        output_dir=tmp_path / "heme_prepare",
    )
    manifest = build_heme_mapping_and_leapin(
        prepared_pdb=heme["prepared_pdb"],
        prepare_report_json=heme["prepare_report"],
        output_dir=tmp_path / "mapping_leapin",
    )
    leapin = Path(manifest["output_files"]["leapin"]).read_text(encoding="utf-8")
    cys = manifest["residues"]["proximal_cym"]["leap_resid"]
    heme_resid = manifest["residues"]["heme"]["leap_resid"]

    assert Path(manifest["output_files"]["combined_pdb"]).is_file()
    assert Path(manifest["output_files"]["manifest_json"]).is_file()
    assert manifest["tleap_bond"] == f"bond mol.{cys}.SG mol.{heme_resid}.FE"
    assert f"bond mol.{cys}.SG mol.{heme_resid}.FE" in leapin
    assert "bond mol.439.SG" not in leapin
    assert "\t{ \"oa\" \"O\" \"sp3\" }" in leapin
    assert "\t{ \"ob\" \"O\" \"sp3\" }" in leapin
    assert "saveamberparm mol system_dry.prmtop system_dry.rst7" in leapin


@pytest.mark.skipif(not EXAMPLE_NCT_MOL2.is_file(), reason="example selected ligand pose is not present")
def test_selected_ligand_pose_charge_injection_keeps_pose_coordinates(tmp_path):
    result = parameterize_selected_ligand_pose(
        pose_mol2=EXAMPLE_NCT_MOL2,
        charge_csv=EXAMPLE_NCT_CHARGES,
        formal_charge=0,
        output_dir=tmp_path,
        resname="NCT",
        run_parmchk2=False,
    )
    assert result["status"] == "success"
    assert result["coordinate_policy"].endswith("without geometry optimization")
    out = Path(result["output_mol2"]).read_text(encoding="utf-8")
    source = EXAMPLE_NCT_MOL2.read_text(encoding="utf-8")
    assert "-12.9690" in out and "-16.1320" in out and "-8.0570" in out
    assert "-12.9690" in source and "-16.1320" in source and "-8.0570" in source
    assert "-0.718698" in out
    assert result["atom_count"] == 26
    assert result["injected_atom_count"] == 26
    assert abs(result["partial_charge_sum"]) <= 1.0e-4


@pytest.mark.skipif(not REAL_PDB.is_file() or not EXAMPLE_NCT_MOL2.is_file(), reason="real receptor and ligand pose are not present")
def test_ligand_pose_frame_gate_passes_same_receptor_frame(tmp_path):
    heme = parameterize_protein_heme_complex(
        REAL_PDB,
        heme_state="IC6",
        output_dir=tmp_path / "heme_prepare",
    )
    report = check_ligand_pose_frame(
        current_receptor_pdb=heme["prepared_pdb"],
        docking_receptor_pdb=heme["prepared_pdb"],
        ligand_mol2=EXAMPLE_NCT_MOL2,
        output_dir=tmp_path / "frame",
        ligand_resname="NCT",
    )
    assert report["status"] == "success"
    assert report["heme_anchor_raw_rmsd_a"] == 0.0
    assert Path(report["protein_heme_ligand_check_pdb"]).is_file()


@pytest.mark.skipif(not REAL_PDB.is_file() or not EXAMPLE_NCT_MOL2.is_file(), reason="real receptor and ligand pose are not present")
def test_ligand_pose_frame_gate_fails_shifted_receptor(tmp_path):
    heme = parameterize_protein_heme_complex(
        REAL_PDB,
        heme_state="IC6",
        output_dir=tmp_path / "heme_prepare",
    )
    shifted = tmp_path / "shifted.pdb"
    lines = []
    for line in Path(heme["prepared_pdb"]).read_text(encoding="utf-8").splitlines():
        if line.startswith(("ATOM", "HETATM")) and line[17:20].strip() == "HEM":
            x = float(line[30:38]) + 1.0
            line = f"{line[:30]}{x:8.3f}{line[38:]}"
        lines.append(line)
    shifted.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = check_ligand_pose_frame(
        current_receptor_pdb=heme["prepared_pdb"],
        docking_receptor_pdb=shifted,
        ligand_mol2=EXAMPLE_NCT_MOL2,
        output_dir=tmp_path / "frame_fail",
        ligand_resname="NCT",
        anchor_rmsd_threshold=0.25,
    )
    assert report["status"] == "failed"
    assert report["heme_anchor_raw_rmsd_a"] > 0.25


@pytest.mark.skipif(not MODE11_HEAVY_ONLY.is_file(), reason="mode 11 Vina heavy-only pose is not present")
def test_gpu4pyscf_esp_core_rejects_vina_heavy_only_pose(tmp_path):
    with pytest.raises(ValueError, match="no hydrogens"):
        prepare_gpu4pyscf_esp_job(
            ligand_pose=MODE11_HEAVY_ONLY,
            formal_charge=0,
            output_dir=tmp_path / "esp",
            resname="NCT",
        )


def test_gpu4pyscf_esp_core_prepares_hydrogen_complete_job(tmp_path):
    mol2 = tmp_path / "mini_lig.mol2"
    mol2.write_text(
        """@<TRIPOS>MOLECULE
MINI
3 2 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 C1        0.0000    0.0000    0.0000 C.3       1 LIG      0.000000
      2 H1        1.0900    0.0000    0.0000 H         1 LIG      0.000000
      3 H2       -1.0900    0.0000    0.0000 H         1 LIG      0.000000
@<TRIPOS>BOND
     1    1    2 1
     2    1    3 1
@<TRIPOS>SUBSTRUCTURE
     1 LIG         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )
    result = prepare_gpu4pyscf_esp_job(
        ligand_pose=mol2,
        formal_charge=0,
        output_dir=tmp_path / "esp",
        resname="LIG",
        points_per_atom=6,
    )
    assert result["status"] == "prepared"
    assert result["atom_count"] == 3
    assert result["hydrogen_count"] == 2
    assert Path(result["runner"]).is_file()
    assert Path(result["qm_input_xyz"]).is_file()


def test_second_core_source_policy_separates_geometry_from_force_field_parameters():
    policy = second_core_source_policy()
    assert policy["bond_graph_source"].startswith("ligand SDF/template")
    assert "not inferred from complex PDB coordinates" in policy["bond_order_source"]
    assert policy["initial_coordinate_source"] == "confirmed protein-heme-ligand complex PDB"
    assert policy["force_field_parameter_source"].startswith("GAFF2 plus parmchk2")
    assert "not calculated from PDB bond lengths or angles" in policy["force_field_parameter_source"]
    assert "row-order coordinate transfer is forbidden" in policy["atom_mapping_policy"]


def test_sdf_complex_mapping_renames_mol2_atoms_from_complex_pdb(tmp_path):
    sdf = tmp_path / "lig.sdf"
    sdf.write_text(
        """mini
  CYPForge

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4300    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
   -1.0900    0.0000    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
M  END
$$$$
""",
        encoding="utf-8",
    )
    ligand_pdb = tmp_path / "lig.pdb"
    ligand_pdb.write_text(
        "HETATM    1  HX  LIG L   1      -1.090   0.000   0.000  1.00  0.00           H\n"
        "HETATM    2  C10 LIG L   1       0.000   0.000   0.000  1.00  0.00           C\n"
        "HETATM    3  O7  LIG L   1       1.430   0.000   0.000  1.00  0.00           O\n"
        "END\n",
        encoding="utf-8",
    )
    typed_mol2 = tmp_path / "typed.mol2"
    typed_mol2.write_text(
        """@<TRIPOS>MOLECULE
LIG
3 2 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 C1        9.0000    0.0000    0.0000 c3        1 LIG      0.100000
      2 O1       10.4300    0.0000    0.0000 o         1 LIG     -0.200000
      3 H1        7.9100    0.0000    0.0000 h1        1 LIG      0.100000
@<TRIPOS>BOND
     1    1    2 1
     2    1    3 1
@<TRIPOS>SUBSTRUCTURE
     1 LIG         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )
    mapping = map_sdf_atoms_to_complex_atoms(sdf_template=sdf, ligand_pdb=ligand_pdb)
    output = tmp_path / "mapped.mol2"
    report = _write_sdf_order_complex_pose_mol2(
        typed_sdf_mol2=typed_mol2,
        complex_ligand_pdb=ligand_pdb,
        mapping=mapping,
        output_mol2=output,
        resname="LIG",
    )
    atoms = read_ligand_atoms(output)
    assert [atom["name"] for atom in atoms] == ["C10", "O7", "HX"]
    assert [(atom["x"], atom["y"], atom["z"]) for atom in atoms] == [(0.0, 0.0, 0.0), (1.43, 0.0, 0.0), (-1.09, 0.0, 0.0)]
    assert mapping["connectivity_consistency"] == "passed"
    assert mapping["mapping_policy"].startswith("graph_isomorphism")
    assert mapping["ambiguity_policy"].startswith("fail")
    assert mapping["sdf_atom_id_to_pdb_atom_index"] == {"1": 2, "2": 3, "3": 1}
    assert report["atom_name_policy"].startswith("final MOL2 atom names")
    assert report["written_vs_complex_heavy_atom_rmsd_a"] == 0.0
    assert report["written_vs_complex_heavy_atom_rmsd_tolerance_a"] == 0.05
    assert report["written_vs_complex_heavy_atom_rmsd_check"] == "passed"


def test_sdf_complex_mapping_rigid_fits_sdf_hydrogens_for_heavy_only_complex(tmp_path):
    sdf = tmp_path / "lig.sdf"
    sdf.write_text(
        """mini
  CYPForge

  4  3  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4300    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.3000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
   -1.0900    0.0000    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
  1  4  1  0  0  0  0
M  END
$$$$
""",
        encoding="utf-8",
    )
    ligand_pdb = tmp_path / "lig_heavy_only.pdb"
    ligand_pdb.write_text(
        "HETATM    1  C10 LIG L   1       5.000   6.000   7.000  1.00  0.00           C\n"
        "HETATM    2  O7  LIG L   1       6.430   6.000   7.000  1.00  0.00           O\n"
        "HETATM    3  N4  LIG L   1       5.000   7.300   7.000  1.00  0.00           N\n"
        "END\n",
        encoding="utf-8",
    )
    typed_mol2 = tmp_path / "typed.mol2"
    typed_mol2.write_text(
        """@<TRIPOS>MOLECULE
LIG
4 3 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 C1        0.0000    0.0000    0.0000 c3        1 LIG      0.100000
      2 O1        1.4300    0.0000    0.0000 o         1 LIG     -0.200000
      3 N1        0.0000    1.3000    0.0000 n3        1 LIG     -0.100000
      4 H1       -1.0900    0.0000    0.0000 h1        1 LIG      0.200000
@<TRIPOS>BOND
     1    1    2 1
     2    1    3 1
     3    1    4 1
@<TRIPOS>SUBSTRUCTURE
     1 LIG         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )

    mapping = map_sdf_atoms_to_complex_atoms(sdf_template=sdf, ligand_pdb=ligand_pdb)
    output = tmp_path / "mapped.mol2"
    report = _write_sdf_order_complex_pose_mol2(
        typed_sdf_mol2=typed_mol2,
        complex_ligand_pdb=ligand_pdb,
        mapping=mapping,
        output_mol2=output,
        resname="LIG",
    )
    atoms = read_ligand_atoms(output)

    assert mapping["complex_hydrogen_policy"].startswith("complex ligand is heavy-only")
    assert mapping["mapping"][3]["coordinate_source"] == "sdf_hydrogen_rigid_fit_to_complex_heavy_pose"
    assert [atom["name"] for atom in atoms] == ["C10", "O7", "N4", "H1"]
    assert atoms[0]["x"] == 5.0
    assert atoms[1]["x"] == 6.43
    assert atoms[3]["element"] == "H"
    assert report["written_vs_complex_heavy_atom_rmsd_check"] == "passed"


def test_sdf_complex_mapping_accepts_proven_equivalent_heavy_atom_exchange(tmp_path):
    sdf = tmp_path / "sym.sdf"
    sdf.write_text(
        """symmetric
  CYPForge

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4300    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
   -1.4300    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
M  END
$$$$
""",
        encoding="utf-8",
    )
    ligand_pdb = tmp_path / "sym.pdb"
    ligand_pdb.write_text(
        "HETATM    1  C1  LIG L   1     100.000 100.000 100.000  1.00  0.00           C\n"
        "HETATM    2  O1  LIG L   1     101.430 100.000 100.000  1.00  0.00           O\n"
        "HETATM    3  O2  LIG L   1      98.570 100.000 100.000  1.00  0.00           O\n"
        "END\n",
        encoding="utf-8",
    )

    mapping = map_sdf_atoms_to_complex_atoms(sdf_template=sdf, ligand_pdb=ligand_pdb)
    assert mapping["mapping_source"] == "heavy_hypergraph_fallback"
    assert mapping["heavy_atom_mapping_decision"] == "equivalent_ok"
    assert mapping["fallback_equivalence_proof"]["is_equivalent"] is True
    assert mapping["fallback_equivalence_proof"]["exchanges"][0]["class"] == "same_parent_terminal_equivalent"

    with pytest.raises(ValueError, match="Ambiguous heavy-atom mapping"):
        map_sdf_atoms_to_complex_atoms(sdf_template=sdf, ligand_pdb=ligand_pdb, enable_hypergraph_fallback=False)


def test_sdf_complex_mapping_reports_raw_coordinate_distance_not_qc_rmsd(tmp_path):
    sdf = tmp_path / "lig.sdf"
    sdf.write_text(
        """mini
  CYPForge

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4300    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.3000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
M  END
$$$$
""",
        encoding="utf-8",
    )
    ligand_pdb = tmp_path / "lig.pdb"
    ligand_pdb.write_text(
        "HETATM    1  C10 LIG L   1     100.000 100.000 100.000  1.00  0.00           C\n"
        "HETATM    2  O7  LIG L   1     101.430 100.000 100.000  1.00  0.00           O\n"
        "HETATM    3  N4  LIG L   1     100.000 101.300 100.000  1.00  0.00           N\n"
        "END\n",
        encoding="utf-8",
    )

    mapping = map_sdf_atoms_to_complex_atoms(sdf_template=sdf, ligand_pdb=ligand_pdb)

    assert "template_to_complex_heavy_atom_rmsd_a" not in mapping
    assert "template_to_complex_heavy_atom_max_delta_a" not in mapping
    assert mapping["raw_template_to_complex_heavy_atom_distance_rms_a"] > 100.0
    assert mapping["raw_template_to_complex_coordinate_distance_note"].startswith("Pre-alignment")
    assert mapping["connectivity_consistency"] == "passed"


def test_prepare_complex_sdf_ligand_resp_inputs_handles_heavy_only_complex(tmp_path, monkeypatch):
    sdf = tmp_path / "lig.sdf"
    sdf.write_text(
        """mini
  CYPForge

  4  3  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.4300    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.3000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
   -1.0900    0.0000    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
  1  4  1  0  0  0  0
M  END
$$$$
""",
        encoding="utf-8",
    )
    complex_pdb = tmp_path / "complex.pdb"
    complex_pdb.write_text(
        "HETATM    1  C10 LIG L   1       5.000   6.000   7.000  1.00  0.00           C\n"
        "HETATM    2  O7  LIG L   1       6.430   6.000   7.000  1.00  0.00           O\n"
        "HETATM    3  N4  LIG L   1       5.000   7.300   7.000  1.00  0.00           N\n"
        "END\n",
        encoding="utf-8",
    )

    import cypforge_core.ligand_gpu4pyscf_esp as lg

    def fake_antechamber(*, ligand_sdf, output_dir, output_name, resname, formal_charge, amber_sh):
        Path(output_dir, output_name).write_text(
            """@<TRIPOS>MOLECULE
LIG
4 3 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 C1        0.0000    0.0000    0.0000 c3        1 LIG      0.100000
      2 O1        1.4300    0.0000    0.0000 o         1 LIG     -0.200000
      3 N1        0.0000    1.3000    0.0000 n3        1 LIG     -0.100000
      4 H1       -1.0900    0.0000    0.0000 h1        1 LIG      0.200000
@<TRIPOS>BOND
     1    1    2 1
     2    1    3 1
     3    1    4 1
@<TRIPOS>SUBSTRUCTURE
     1 LIG         1 TEMP              0 ****  ****    0 ROOT
""",
            encoding="utf-8",
        )
        return {"returncode": 0, "stdout": "", "stderr": ""}

    def fake_parmchk2(out, mol2_name, frcmod_name, amber_sh):
        Path(out, frcmod_name).write_text("MASS\nc3 12.01\n", encoding="utf-8")
        return {"returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(lg, "resolve_amber_sh", lambda amber_sh=None: amber_sh or "/amber.sh")
    monkeypatch.setattr(lg, "_run_antechamber_sdf_to_mol2", fake_antechamber)
    monkeypatch.setattr(lg, "_run_parmchk2", fake_parmchk2)

    result = prepare_complex_sdf_ligand_resp_inputs(
        complex_pdb=complex_pdb,
        ligand_resname="LIG",
        ligand_chain="L",
        ligand_template_sdf=sdf,
        formal_charge=0,
        output_dir=tmp_path / "out",
        run_parmchk2=True,
    )

    atoms = read_ligand_atoms(result["resp_input_mol2"])
    assert result["status"] == "prepared"
    assert result["prepare_only_policy"].startswith("No SCF")
    assert result["coordinate_transfer"]["written_vs_complex_heavy_atom_rmsd_check"] == "passed"
    assert [atom["name"] for atom in atoms] == ["C10", "O7", "N4", "H1"]
    assert atoms[3]["element"] == "H"


def test_ligand_mapping_leapin_writes_atom_check_and_ligand_leap_input(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    heme_mol2 = data / "HEM.mol2"
    heme_mol2.write_text(
        """@<TRIPOS>MOLECULE
HEM
1 0 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 FE         0.0000    0.0000    0.0000 fe        1 HEM      0.100000
@<TRIPOS>BOND
@<TRIPOS>SUBSTRUCTURE
     1 HEM         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )
    cyp_mol2 = data / "CYP.mol2"
    cyp_mol2.write_text(
        """@<TRIPOS>MOLECULE
CYP
2 0 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 SG         0.0000    0.0000    0.0000 SH        1 CYP     -0.200000
      2 CB         0.0000    0.0000    0.0000 CT        1 CYP      0.100000
@<TRIPOS>BOND
@<TRIPOS>SUBSTRUCTURE
     1 CYP         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )
    heme_frcmod = data / "IC6.frcmod"
    heme_frcmod.write_text("MASS\nfe 55.845\n\nBOND\nfe-SH 100.0 2.3\n", encoding="utf-8")
    ligand_mol2 = data / "NCT.mol2"
    ligand_mol2.write_text(
        """@<TRIPOS>MOLECULE
NCT
2 1 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 C1         5.0000    0.0000    0.0000 c3        1 NCT      0.100000
      2 H1         6.0000    0.0000    0.0000 h1        1 NCT     -0.100000
@<TRIPOS>BOND
     1    1    2 1
@<TRIPOS>SUBSTRUCTURE
     1 NCT         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )
    ligand_frcmod = data / "NCT.frcmod"
    ligand_frcmod.write_text("MASS\nc3 12.01\nh1 1.008\n", encoding="utf-8")
    report = data / "prepare_report.json"
    report.write_text(
        json.dumps(
            {
                "heme_mapping": {"heme_state": "IC6", "template_mol2_path": str(heme_mol2)},
                "parameters": {"cyp_mol2_path": str(cyp_mol2), "frcmod_path": str(heme_frcmod)},
            }
        ),
        encoding="utf-8",
    )
    complex_pdb = data / "complex.pdb"
    complex_pdb.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\n"
        "ATOM      2  CA  ALA A   1       1.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      3  SG  CYM A   2       2.000   0.000   0.000  1.00  0.00           S\n"
        "HETATM    4  FE  HEM B   3       3.000   0.000   0.000  1.00  0.00          FE\n"
        "HETATM    5  C1  NCT C   4       5.000   0.000   0.000  1.00  0.00           C\n"
        "HETATM    6  H1  NCT C   4       6.000   0.000   0.000  1.00  0.00           H\n"
        "END\n",
        encoding="utf-8",
    )

    manifest = build_ligand_mapping_and_leapin(
        complex_pdb=complex_pdb,
        prepare_report_json=report,
        ligand_mol2=ligand_mol2,
        ligand_frcmod=ligand_frcmod,
        ligand_resname="NCT",
        ligand_chain="C",
        expected_ligand_charge=0,
        output_dir=tmp_path / "ligand_leap",
    )
    leapin = Path(manifest["output_files"]["leapin"]).read_text(encoding="utf-8")
    atom_check = json.loads(Path(manifest["output_files"]["ligand_atom_check_json"]).read_text(encoding="utf-8"))

    assert manifest["status"] == "success"
    assert Path(manifest["output_files"]["combined_pdb"]).is_file()
    assert Path(manifest["output_files"]["manifest_json"]).is_file()
    assert atom_check["status"] == "success"
    assert atom_check["charge_check"] == "passed"
    assert atom_check["pdb_atom_to_mol2_atom_map"][0]["pdb_atom_name"] == "C1"
    assert "loadamberparams NCT.frcmod" in leapin
    assert "NCT = loadmol2 NCT.mol2" in leapin
    assert "saveamberparm mol system_lig_dry.prmtop system_lig_dry.rst7" in leapin
    assert manifest["tleap_bond"] in leapin


def test_ligand_mapping_leapin_accepts_atom_record_heme_ligand_and_blank_chain(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    heme_mol2 = data / "HEM.mol2"
    heme_mol2.write_text(
        """@<TRIPOS>MOLECULE
HEM
1 0 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 FE         0.0000    0.0000    0.0000 fe        1 HEM      0.100000
@<TRIPOS>BOND
@<TRIPOS>SUBSTRUCTURE
     1 HEM         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )
    cyp_mol2 = data / "CYP.mol2"
    cyp_mol2.write_text(
        """@<TRIPOS>MOLECULE
CYP
2 0 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 SG         0.0000    0.0000    0.0000 SH        1 CYP     -0.200000
      2 CB         0.0000    0.0000    0.0000 CT        1 CYP      0.100000
@<TRIPOS>BOND
@<TRIPOS>SUBSTRUCTURE
     1 CYP         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )
    heme_frcmod = data / "IC6.frcmod"
    heme_frcmod.write_text("MASS\nfe 55.845\n\nBOND\nfe-SH 100.0 2.3\n", encoding="utf-8")
    ligand_mol2 = data / "NCT.mol2"
    ligand_mol2.write_text(
        """@<TRIPOS>MOLECULE
NCT
2 1 1 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
      1 C1         5.0000    0.0000    0.0000 c3        1 NCT      0.100000
      2 H1         6.0000    0.0000    0.0000 h1        1 NCT     -0.100000
@<TRIPOS>BOND
     1    1    2 1
@<TRIPOS>SUBSTRUCTURE
     1 NCT         1 TEMP              0 ****  ****    0 ROOT
""",
        encoding="utf-8",
    )
    ligand_frcmod = data / "NCT.frcmod"
    ligand_frcmod.write_text("MASS\nc3 12.01\nh1 1.008\n", encoding="utf-8")
    report = data / "prepare_report.json"
    report.write_text(
        json.dumps(
            {
                "heme_mapping": {"heme_state": "IC6", "template_mol2_path": str(heme_mol2)},
                "parameters": {"cyp_mol2_path": str(cyp_mol2), "frcmod_path": str(heme_frcmod)},
            }
        ),
        encoding="utf-8",
    )
    complex_pdb = data / "complex_atom_records_blank_chain.pdb"
    complex_pdb.write_text(
        "ATOM      1  N   ALA     1       0.000   0.000   0.000  1.00  0.00           N\n"
        "ATOM      2  SG  CYM   410       2.000   0.000   0.000  1.00  0.00           S\n"
        "ATOM      3  FE  HEM   466       3.000   0.000   0.000  1.00  0.00          FE\n"
        "ATOM      4  C1  NCT   467       5.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      5  H1  NCT   467       6.000   0.000   0.000  1.00  0.00           H\n"
        "END\n",
        encoding="utf-8",
    )

    manifest = build_ligand_mapping_and_leapin(
        complex_pdb=complex_pdb,
        prepare_report_json=report,
        ligand_mol2=ligand_mol2,
        ligand_frcmod=ligand_frcmod,
        ligand_resname="NCT",
        ligand_chain="",
        expected_ligand_charge=0,
        output_dir=tmp_path / "ligand_leap",
    )

    assert manifest["status"] == "success"
    assert manifest["residues"]["heme"]["source_chain"] == ""
    assert manifest["residues"]["ligand"]["source_chain"] == ""
    assert manifest["residues"]["heme"]["source_resid"] == 466
    assert manifest["residues"]["ligand"]["source_resid"] == 467


def test_complex_protonation_finalize_records_original_current_mapping_and_resnames(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    original = data / "prepared_original.pdb"
    current = data / "complex_ligand_chainbc.pdb"
    original_lines = []
    current_lines = []
    originals = {55: ("HIS", 84), 275: ("GLU", 304), 299: ("HIS", 328), 386: ("HIS", 415), 410: ("CYP", 439), 419: ("GLU", 448)}
    serial = 1
    for current_resid in range(1, 421):
        resname, original_resid = originals.get(current_resid, ("ALA", current_resid + 29))
        current_resname = "CYM" if resname == "CYP" else ("HIE" if resname == "HIS" else resname)
        original_lines.append(
            f"ATOM  {serial:5d}  N   {resname:>3s} A{original_resid:4d}       0.000   0.000   0.000  1.00  0.00           N"
        )
        current_lines.append(
            f"ATOM  {serial:5d}  N   {current_resname:>3s} A{current_resid:4d}       0.000   0.000   0.000  1.00  0.00           N"
        )
        serial += 1
    current_lines.append("HETATM  999  FE  HEM B 421       0.000   0.000   0.000  1.00  0.00          FE")
    current_lines.append("HETATM 1000  C1  NCT C 422       0.000   0.000   0.000  1.00  0.00           C")
    original.write_text("\n".join(original_lines) + "\nEND\n", encoding="utf-8")
    current.write_text("\n".join(current_lines) + "\nEND\n", encoding="utf-8")
    leapin = data / "ligand_mapping_leapin.in"
    leapin.write_text(
        "mol = loadpdb complex_ligand_chainbc.pdb\n"
        "saveamberparm mol system_lig_dry.prmtop system_lig_dry.rst7\n",
        encoding="utf-8",
    )
    ligand_manifest = data / "ligand_mapping_leapin_manifest.json"
    ligand_manifest.write_text(
        json.dumps({"output_files": {"combined_pdb": str(current), "leapin": str(leapin)}}),
        encoding="utf-8",
    )
    decision = data / "protonation_decision_audit.json"
    decision.write_text(
        json.dumps(
            {
                "recommended_changes": [
                    {"assembled_resid": 419, "original_resid": 448, "from": "GLU", "to": "GLH"},
                    {"assembled_resid": 55, "original_resid": 84, "from": "HIE", "to": "HID"},
                    {"assembled_resid": 299, "original_resid": 328, "from": "HIE", "to": "HID"},
                    {"assembled_resid": 386, "original_resid": 415, "from": "HIE", "to": "HID"},
                ],
                "watchlist_no_immediate_change": [{"assembled_resid": 275, "original_resid": 304, "residue": "GLU"}],
            }
        ),
        encoding="utf-8",
    )

    manifest = finalize_complex_protonation_mapping(
        ligand_mapping_manifest_json=ligand_manifest,
        original_prepared_pdb=original,
        protonation_decision_json=decision,
        output_dir=tmp_path / "final",
    )

    final_pdb = Path(manifest["output_files"]["final_pdb"]).read_text(encoding="utf-8")
    final_leap = Path(manifest["output_files"]["final_leapin"]).read_text(encoding="utf-8")
    assert manifest["status"] == "success"
    assert manifest["expected_final_residue_checks"]["419"]["found_resname"] == "GLH"
    assert manifest["expected_final_residue_checks"]["55"]["found_resname"] == "HID"
    assert manifest["expected_final_residue_checks"]["299"]["found_resname"] == "HID"
    assert manifest["expected_final_residue_checks"]["386"]["found_resname"] == "HID"
    assert manifest["expected_final_residue_checks"]["275"]["found_resname"] == "GLU"
    assert manifest["expected_final_residue_checks"]["410"]["found_resname"] == "CYM"
    assert manifest["protonation_changes"][0]["source_mapping"]["original_resid"] == 448
    assert " GLH A 419" in final_pdb
    assert " HID A  55" in final_pdb
    assert " CYM A 410" in final_pdb
    assert "complex_ligand_protonation_final.pdb" in final_leap
    assert "system_lig_protstate_dry.prmtop" in final_leap


def test_complex_protonation_finalize_noop_uses_manifest_proximal_cym(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    original = data / "prepared_original.pdb"
    current = data / "complex_ligand_chainbc.pdb"
    leapin = data / "ligand_mapping_leapin.in"
    ligand_manifest = data / "ligand_mapping_leapin_manifest.json"
    decision = data / "protonation_decision_audit.json"

    original.write_text(
        "\n".join(
            [
                "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N",
                "ATOM      2  N   CYS A 439       1.000   0.000   0.000  1.00  0.00           N",
                "ATOM      3  SG  CYS A 439       2.000   0.000   0.000  1.00  0.00           S",
                "ATOM      4  N   ALA A 440       3.000   0.000   0.000  1.00  0.00           N",
                "END",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    current.write_text(
        "\n".join(
            [
                "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N",
                "ATOM      2  N   CYM A 409       1.000   0.000   0.000  1.00  0.00           N",
                "ATOM      3  SG  CYM A 409       2.000   0.000   0.000  1.00  0.00           S",
                "ATOM      4  N   ALA A 410       3.000   0.000   0.000  1.00  0.00           N",
                "HETATM    5  FE  HEM B 411       4.000   0.000   0.000  1.00  0.00          FE",
                "HETATM    6  C1  COU C 412       5.000   0.000   0.000  1.00  0.00           C",
                "END",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    leapin.write_text(
        "mol = loadpdb complex_ligand_chainbc.pdb\n"
        "saveamberparm mol system_lig_dry.prmtop system_lig_dry.rst7\n",
        encoding="utf-8",
    )
    ligand_manifest.write_text(
        json.dumps(
            {
                "output_files": {"combined_pdb": str(current), "leapin": str(leapin)},
                "parameter_files": {},
                "residues": {
                    "proximal_cym": {
                        "source_chain": "A",
                        "source_resid": 439,
                        "leap_resid": 409,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    decision.write_text(
        json.dumps({"recommended_changes": [], "watchlist_no_immediate_change": []}),
        encoding="utf-8",
    )

    manifest = finalize_complex_protonation_mapping(
        ligand_mapping_manifest_json=ligand_manifest,
        original_prepared_pdb=original,
        protonation_decision_json=decision,
        output_dir=tmp_path / "final",
    )

    final_pdb = Path(manifest["output_files"]["final_pdb"]).read_text(encoding="utf-8")
    residue_checks = manifest["expected_final_residue_checks"]
    assert manifest["status"] == "success"
    assert set(residue_checks) == {"409"}
    assert residue_checks["409"]["expected_resname"] == "CYM"
    assert residue_checks["409"]["found_resname"] == "CYM"
    assert residue_checks["409"]["source"] == "ligand_mapping_manifest.proximal_cym"
    assert manifest["expected_dry_charge_change"]["expected_new_total_charge"] is None
    assert " CYM A 409" in final_pdb


def test_complex_solvation_ionization_prepares_neutralizing_leap_input(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    final_pdb = data / "complex_ligand_protonation_final.pdb"
    final_pdb.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\nEND\n", encoding="utf-8")
    final_leap = data / "complex_protonation_final_leap.in"
    final_leap.write_text(
        "source leaprc.protein.ff19SB\n"
        "loadamberparams IC6.frcmod\n"
        "HEM = loadmol2 HEM.mol2\n"
        "NCT = loadmol2 NCT.mol2\n"
        "mol = loadpdb complex_ligand_protonation_final.pdb\n"
        "check mol\n"
        "charge mol\n"
        "savepdb mol system_lig_protstate_dry_tleap.pdb\n"
        "saveamberparm mol system_lig_protstate_dry.prmtop system_lig_protstate_dry.rst7\n"
        "quit\n",
        encoding="utf-8",
    )
    copied = []
    for name in ["HEM.mol2", "IC6.frcmod", "NCT.mol2", "NCT.frcmod"]:
        path = data / name
        path.write_text(name + "\n", encoding="utf-8")
        copied.append(str(path))
    protonation_manifest = data / "complex_protonation_finalize_manifest.json"
    protonation_manifest.write_text(
        json.dumps(
            {
                "output_files": {
                    "final_pdb": str(final_pdb),
                    "final_leapin": str(final_leap),
                    "copied_parameter_files": copied,
                    "manifest_json": str(protonation_manifest),
                },
                "expected_dry_charge_change": {"expected_new_total_charge": 6.000002},
            }
        ),
        encoding="utf-8",
    )

    manifest = prepare_complex_solvation_ionization(
        protonation_manifest_json=protonation_manifest,
        output_dir=tmp_path / "solv",
    )
    leap = Path(manifest["output_files"]["leapin"]).read_text(encoding="utf-8")
    assert manifest["status"] == "prepared"
    assert manifest["ionization"]["expected_neutralizing_anion_count"] == 6
    assert "solvateOct mol TIP3PBOX 10.000" in leap
    assert "addIonsRand mol Cl- 0" in leap
    assert "saveamberparm mol system_lig_solv.prmtop system_lig_solv.rst7" in leap
    assert "system_lig_protstate_dry.prmtop" not in leap


def test_complex_solvation_ionization_records_nondefault_box_water_and_force_field_choices(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    final_pdb = data / "complex_ligand_protonation_final.pdb"
    final_pdb.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\nEND\n", encoding="utf-8")
    final_leap = data / "complex_protonation_final_leap.in"
    final_leap.write_text(
        "source leaprc.protein.ff19SB\n"
        "source leaprc.gaff2\n"
        "source leaprc.water.tip3p\n"
        "mol = loadpdb complex_ligand_protonation_final.pdb\n"
        "quit\n",
        encoding="utf-8",
    )
    protonation_manifest = data / "manifest.json"
    protonation_manifest.write_text(
        json.dumps({"output_files": {"final_pdb": str(final_pdb), "final_leapin": str(final_leap)}, "expected_dry_charge_change": {"expected_new_total_charge": 6.0}}),
        encoding="utf-8",
    )
    manifest = prepare_complex_solvation_ionization(
        protonation_manifest_json=protonation_manifest,
        output_dir=tmp_path / "solv",
        protein_force_field="ff14SB",
        water_model="OPCBOX",
        water_leaprc="leaprc.water.opc",
        box_type="box",
        buffer_a=12.0,
    )
    leap = Path(manifest["output_files"]["leapin"]).read_text(encoding="utf-8")
    assert "source leaprc.protein.ff14SB" in leap
    assert "source leaprc.gaff2" in leap
    assert "source leaprc.water.opc" in leap
    assert "solvateBox mol OPCBOX 12.000" in leap
    assert manifest["solvation"]["box_shape"] == "rectangular"
    assert manifest["force_fields"]["protein_force_field"] == "ff14SB"
    assert manifest["force_fields"]["ligand_force_field"] == "gaff2"


def test_complex_solvation_ionization_rejects_gaff_ligand_force_field(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    final_pdb = data / "complex_ligand_protonation_final.pdb"
    final_pdb.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\nEND\n", encoding="utf-8")
    final_leap = data / "complex_protonation_final_leap.in"
    final_leap.write_text(
        "source leaprc.protein.ff19SB\n"
        "source leaprc.gaff2\n"
        "source leaprc.water.tip3p\n"
        "mol = loadpdb complex_ligand_protonation_final.pdb\n"
        "quit\n",
        encoding="utf-8",
    )
    protonation_manifest = data / "manifest.json"
    protonation_manifest.write_text(
        json.dumps({"output_files": {"final_pdb": str(final_pdb), "final_leapin": str(final_leap)}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fixed to gaff2"):
        prepare_complex_solvation_ionization(
            protonation_manifest_json=protonation_manifest,
            output_dir=tmp_path / "solv",
            ligand_force_field="gaff",
        )


def test_complex_solvation_ionization_rejects_water_model_leaprc_mismatch(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    final_pdb = data / "complex_ligand_protonation_final.pdb"
    final_pdb.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\nEND\n", encoding="utf-8")
    final_leap = data / "complex_protonation_final_leap.in"
    final_leap.write_text(
        "source leaprc.protein.ff19SB\n"
        "source leaprc.gaff2\n"
        "source leaprc.water.tip3p\n"
        "mol = loadpdb complex_ligand_protonation_final.pdb\n"
        "quit\n",
        encoding="utf-8",
    )
    protonation_manifest = data / "manifest.json"
    protonation_manifest.write_text(
        json.dumps({"output_files": {"final_pdb": str(final_pdb), "final_leapin": str(final_leap)}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires leaprc.water.opc"):
        prepare_complex_solvation_ionization(
            protonation_manifest_json=protonation_manifest,
            output_dir=tmp_path / "solv",
            water_model="OPCBOX",
            water_leaprc="leaprc.water.tip3p",
        )


def test_complex_pre_md_equilibration_renders_nine_safe_stages(tmp_path):
    solv = tmp_path / "solv"
    solv.mkdir()
    prmtop = solv / "system_lig_solv.prmtop"
    rst7 = solv / "system_lig_solv.rst7"
    prmtop.write_text("%VERSION VERSION_STAMP = V0001.000\n", encoding="utf-8")
    rst7.write_text("dummy restart\n", encoding="utf-8")
    solvation_manifest = solv / "complex_solvation_ionization_manifest.json"
    solvation_manifest.write_text(
        json.dumps(
            {
                "output_files": {
                    "expected_prmtop_after_tleap": str(prmtop),
                    "expected_rst7_after_tleap": str(rst7),
                }
            }
        ),
        encoding="utf-8",
    )

    manifest = prepare_complex_pre_md_equilibration(
        solvation_manifest_json=solvation_manifest,
        output_dir=tmp_path / "pre_md",
    )
    run_script = Path(manifest["output_files"]["run_script"]).read_text(encoding="utf-8")
    first_mdin = Path(manifest["stages"][0]["mdin"]).read_text(encoding="utf-8")
    free_stage = manifest["stages"][-1]

    assert manifest["stage_count"] == 9
    assert manifest["safety_gates"]["validation"]["restrained_stage_count"] == 8
    assert manifest["stages"][0]["reference_restart"] == "system_lig_solv.rst7"
    assert "-ref system_lig_solv.rst7" in run_script
    assert free_stage["uses_position_restraints"] is False
    assert free_stage["reference_restart"] is None
    assert "09_npt_free_equilibration.rst7 -inf" in run_script
    assert "09_npt_free_equilibration.rst7 -inf run/09_npt_free_equilibration.info -x" in run_script
    assert "run/stage_status.tsv" in run_script
    assert "run/run_pre_md.started_at.txt" in run_script
    assert "run/run_pre_md.finished_at.txt" in run_script
    assert "run/run_pre_md.exit_code.txt" in run_script
    assert "probe_rc=$?" in run_script
    assert "cpptraj topology/restart pairing probe failed" in run_script
    assert "bad bond|Unusual bond length" in run_script
    assert "bad/unusual bond-length warnings" in run_script
    assert "restraintmask='!@H='" in first_mdin
    windows_launcher = Path(manifest["output_files"]["windows_wsl_launcher"]).read_text(encoding="utf-8")
    assert "$env:AMBER_SH" in windows_launcher
    assert "$env:AMBERHOME" in windows_launcher


def test_complex_pre_md_equilibration_rejects_wrapped_restrained_stage(tmp_path):
    solv = tmp_path / "solv"
    solv.mkdir()
    prmtop = solv / "system_lig_solv.prmtop"
    rst7 = solv / "system_lig_solv.rst7"
    prmtop.write_text("prmtop\n", encoding="utf-8")
    rst7.write_text("rst7\n", encoding="utf-8")
    solvation_manifest = solv / "manifest.json"
    solvation_manifest.write_text(
        json.dumps({"output_files": {"expected_prmtop_after_tleap": str(prmtop), "expected_rst7_after_tleap": str(rst7)}}),
        encoding="utf-8",
    )
    config = default_pre_md_protocol_config()
    config["stages"][4]["parameters"]["iwrap"] = 1
    config_path = tmp_path / "bad_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="must keep iwrap=0"):
        prepare_complex_pre_md_equilibration(
            solvation_manifest_json=solvation_manifest,
            output_dir=tmp_path / "pre_md",
            protocol_config_json=config_path,
        )


def test_complex_pre_md_equilibration_rejects_restrained_stage_without_ref(tmp_path):
    solv = tmp_path / "solv"
    solv.mkdir()
    prmtop = solv / "system_lig_solv.prmtop"
    rst7 = solv / "system_lig_solv.rst7"
    prmtop.write_text("prmtop\n", encoding="utf-8")
    rst7.write_text("rst7\n", encoding="utf-8")
    solvation_manifest = solv / "manifest.json"
    solvation_manifest.write_text(
        json.dumps({"output_files": {"expected_prmtop_after_tleap": str(prmtop), "expected_rst7_after_tleap": str(rst7)}}),
        encoding="utf-8",
    )
    config = default_pre_md_protocol_config()
    config["stages"][0]["reference"] = None
    config_path = tmp_path / "bad_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="has no reference"):
        prepare_complex_pre_md_equilibration(
            solvation_manifest_json=solvation_manifest,
            output_dir=tmp_path / "pre_md",
            protocol_config_json=config_path,
        )


def test_validate_solvation_tleap_outputs_parses_neutralized_log(tmp_path):
    solv = tmp_path / "solv"
    solv.mkdir()
    for name in ["system_lig_solv.prmtop", "system_lig_solv.rst7", "system_lig_solv_tleap.pdb"]:
        (solv / name).write_text(name + "\n", encoding="utf-8")
    manifest = solv / "complex_solvation_ionization_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "output_files": {
                    "manifest_json": str(manifest),
                    "expected_prmtop_after_tleap": str(solv / "system_lig_solv.prmtop"),
                    "expected_rst7_after_tleap": str(solv / "system_lig_solv.rst7"),
                    "expected_pdb_after_tleap": str(solv / "system_lig_solv_tleap.pdb"),
                },
                "ionization": {"expected_neutralizing_anion_count": 6},
            }
        ),
        encoding="utf-8",
    )
    (solv / "leap.log").write_text(
        "\n".join(
            [
                "Total unperturbed charge:   5.999998",
                "Total unperturbed charge:   5.999998",
                "6 Cl- ions required to neutralize.",
                "Adding 6 counter ions to \"mol\". 22830 solvent molecules will remain.",
                "Total unperturbed charge:  -0.000002",
                "Exiting LEaP: Errors = 0; Warnings = 16; Notes = 0.",
            ]
        ),
        encoding="utf-8",
    )
    result = validate_solvation_tleap_outputs(solvation_manifest_json=manifest)
    assert result["status"] == "success"
    assert result["tleap"]["charges_seen"] == [5.999998, 5.999998, -0.000002]
    assert result["tleap"]["cl_required"] == 6
    assert result["tleap"]["solvent_molecules_after_ionization"] == 22830
    assert (solv / "solvation_ionization_validation.json").is_file()


def test_validate_solvation_tleap_outputs_fails_on_missing_log_and_bad_charge(tmp_path):
    solv = tmp_path / "solv"
    solv.mkdir()
    for name in ["system_lig_solv.prmtop", "system_lig_solv.rst7", "system_lig_solv_tleap.pdb"]:
        (solv / name).write_text(name + "\n", encoding="utf-8")
    manifest = solv / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "output_files": {
                    "manifest_json": str(manifest),
                    "expected_prmtop_after_tleap": str(solv / "system_lig_solv.prmtop"),
                    "expected_rst7_after_tleap": str(solv / "system_lig_solv.rst7"),
                    "expected_pdb_after_tleap": str(solv / "system_lig_solv_tleap.pdb"),
                },
                "ionization": {"expected_neutralizing_anion_count": 6},
            }
        ),
        encoding="utf-8",
    )
    missing = validate_solvation_tleap_outputs(solvation_manifest_json=manifest)
    assert missing["status"] == "fail"
    assert any("Missing leap.log" in reason for reason in missing["failure_reasons"])

    bad_log = solv / "bad.log"
    bad_log.write_text(
        "Total unperturbed charge:  1.000000\n"
        "6 Cl- ions required to neutralize.\n"
        "Total unperturbed charge:  1.000000\n"
        "Exiting LEaP: Errors = 1; Warnings = 0; Notes = 0.\n",
        encoding="utf-8",
    )
    bad = validate_solvation_tleap_outputs(solvation_manifest_json=manifest, leap_log=bad_log)
    assert bad["status"] == "fail"
    assert any("Errors=1" in reason for reason in bad["failure_reasons"])
    assert any("Final charge" in reason for reason in bad["failure_reasons"])


def test_heme_state_rules_are_derived_not_cli_inputs():
    assert global_audit.HEME_STATE_RULES["IC6"] == {"O1": 0, "O2": 0}
    assert global_audit.HEME_STATE_RULES["CPDI"] == {"O1": 1, "O2": 0}
    assert global_audit.HEME_STATE_RULES["DIOXY"] == {"O1": 1, "O2": 1}


def test_cpdi_heme_topology_gate_checks_distal_oxygen_counts(monkeypatch, tmp_path):
    atoms = [
        {"index": 1, "name": "SG", "resid": 410, "resname": "CYM"},
        {"index": 2, "name": "FE", "resid": 466, "resname": "HEM"},
        {"index": 3, "name": "NA", "resid": 466, "resname": "HEM"},
        {"index": 4, "name": "NB", "resid": 466, "resname": "HEM"},
        {"index": 5, "name": "NC", "resid": 466, "resname": "HEM"},
        {"index": 6, "name": "ND", "resid": 466, "resname": "HEM"},
        {"index": 7, "name": "O1", "resid": 466, "resname": "HEM"},
    ]
    bonds = [(1, 2), (2, 3), (2, 4), (2, 5), (2, 6)]
    pdb_atoms = [
        {"name": "SG", "resname": "CYM", "resid": 410, "x": 0.0, "y": 0.0, "z": 2.4, "element": "S"},
        {"name": "FE", "resname": "HEM", "resid": 466, "x": 0.0, "y": 0.0, "z": 0.0, "element": "FE"},
        {"name": "NA", "resname": "HEM", "resid": 466, "x": 2.0, "y": 0.0, "z": 0.0, "element": "N"},
        {"name": "NB", "resname": "HEM", "resid": 466, "x": -2.0, "y": 0.0, "z": 0.0, "element": "N"},
        {"name": "NC", "resname": "HEM", "resid": 466, "x": 0.0, "y": 2.0, "z": 0.0, "element": "N"},
        {"name": "ND", "resname": "HEM", "resid": 466, "x": 0.0, "y": -2.0, "z": 0.0, "element": "N"},
    ]
    monkeypatch.setattr(global_audit, "_parse_prmtop", lambda path: {"atoms": atoms, "bonds": bonds})
    monkeypatch.setattr(global_audit, "_read_pdb_atoms", lambda path: pdb_atoms)
    gate, rows = global_audit._gate_heme_topology({"solvated_prmtop": tmp_path / "x", "final_full_pdb": tmp_path / "y"}, {"parameter_files": {"heme_frcmod": str(tmp_path / "CPDI.frcmod")}})
    assert gate["status"] == "PASS"
    assert {"check": "CPDI distal O1 count", "value": 1, "expected": 1, "status": "PASS"} in rows
    assert {"check": "CPDI distal O2 count", "value": 0, "expected": 0, "status": "PASS"} in rows


def test_tleap_warning_classification_and_gate_status(tmp_path):
    benign = "(UNKNOWN ATOM TYPE: Zn)\n(UNKNOWN ATOM TYPE: hb)\nExiting LEaP: Errors = 0; Warnings = 1; Notes = 0.\n"
    assert global_audit._classify_tleap_log_lines(benign)["BENIGN_FORCEFIELD_LOAD_WARNING"] == ["(UNKNOWN ATOM TYPE: Zn)", "(UNKNOWN ATOM TYPE: hb)"]
    benign_log = tmp_path / "benign.log"
    benign_log.write_text(benign, encoding="utf-8")
    gate, _ = global_audit._gate_tleap_logs({"leap_logs": [benign_log]})
    assert gate["status"] == "PASS"

    close_log = tmp_path / "close.log"
    close_log.write_text("Warning! Close contact of 1.4 angstroms\nExiting LEaP: Errors = 0; Warnings = 1; Notes = 0.\n", encoding="utf-8")
    gate, _ = global_audit._gate_tleap_logs({"leap_logs": [close_log]})
    assert gate["status"] == "WARN"

    fatal_log = tmp_path / "fatal.log"
    fatal_log.write_text("Could not find angle parameter\nExiting LEaP: Errors = 0; Warnings = 0; Notes = 0.\n", encoding="utf-8")
    gate, _ = global_audit._gate_tleap_logs({"leap_logs": [fatal_log]})
    assert gate["status"] == "FAIL"


def test_global_audit_gate_numbers_are_unique():
    gates = [
        global_audit._gate("Gate 1", "residue_mapping", "PASS", ""),
        global_audit._gate("Gate 2", "ligand_mapping_resp_gaff2", "PASS", ""),
        global_audit._gate("Gate 3", "charge_accounting", "PASS", ""),
        global_audit._gate("Gate 4", "heme_cym_topology", "PASS", ""),
        global_audit._gate("Gate 5", "tleap_log_audit", "PASS", ""),
        global_audit._gate("Gate 6", "solvation_ions_box_pbc", "PASS", ""),
        global_audit._gate("Gate 7", "restraint_mask_counts", "PASS", ""),
        global_audit._gate("Gate 8", "pre_md_run", "PASS", ""),
        global_audit._gate("Gate 9", "p450_geometry_free", "PASS", ""),
    ]
    assert len({gate["gate"] for gate in gates}) == len(gates)


def test_ligand_path_resolvers_prefer_env(monkeypatch):
    monkeypatch.delenv("AMBER_SH", raising=False)
    monkeypatch.delenv("AMBERHOME", raising=False)
    monkeypatch.delenv("MULTIWFN_BIN", raising=False)
    assert resolve_gpu_amber_sh("/explicit/amber.sh") == "/explicit/amber.sh"
    assert resolve_pose_amber_sh("/explicit/amber.sh") == "/explicit/amber.sh"
    monkeypatch.setenv("AMBER_SH", "/env/amber.sh")
    assert resolve_gpu_amber_sh() == "/env/amber.sh"
    assert resolve_pose_amber_sh() == "/env/amber.sh"
    monkeypatch.delenv("AMBER_SH")
    monkeypatch.setenv("AMBERHOME", "/amberhome")
    assert resolve_gpu_amber_sh() == str(Path("/amberhome") / "amber.sh")
    monkeypatch.setenv("MULTIWFN_BIN", "/env/Multiwfn_noGUI")
    assert resolve_multiwfn_bin() == "/env/Multiwfn_noGUI"
