from pathlib import Path

import pytest

from cypforge_core.ligand_gpu4pyscf_esp import stage_supplied_ligand_parameters


@pytest.fixture
def supplied_contract(tmp_path):
    benchmark = Path(__file__).resolve().parents[1] / "benchmark/4EJJ"
    mol2 = tmp_path / "NCT.mol2"
    mol2.write_bytes((benchmark / "NCT_multiwfn_resp.mol2").read_bytes())
    return {
        "supplied_mol2": mol2, "supplied_frcmod": benchmark / "NCT.frcmod",
        "ligand_template_sdf": benchmark / "nicotine.sdf",
        "complex_pdb": benchmark / "4EJJ_CPD1_NCT.pdb", "ligand_resname": "NCT",
        "ligand_chain": "", "formal_charge": 0, "output_dir": tmp_path / "staged",
    }


@pytest.mark.parametrize("charge", ["nan", "inf", "-inf"])
def test_supplied_mol2_rejects_nonfinite_charge(supplied_contract, charge):
    mol2 = supplied_contract["supplied_mol2"]
    lines = mol2.read_text(encoding="utf-8").splitlines()
    atom_row = lines.index("@<TRIPOS>ATOM") + 1
    fields = lines[atom_row].split()
    fields[8] = charge
    lines[atom_row] = " ".join(fields)
    mol2.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        stage_supplied_ligand_parameters(**supplied_contract)


@pytest.mark.parametrize("corruption", ["zero_bonds", "changed_connectivity", "unknown_atom", "duplicate_bond"])
def test_supplied_mol2_checks_its_actual_bond_connectivity(supplied_contract, corruption):
    mol2 = supplied_contract["supplied_mol2"]
    lines = mol2.read_text(encoding="utf-8").splitlines()
    start = lines.index("@<TRIPOS>BOND") + 1
    end = next(index for index in range(start, len(lines)) if lines[index].startswith("@<TRIPOS>"))
    if corruption == "zero_bonds":
        counts = lines[2].split()
        counts[1] = "0"
        lines[2] = " ".join(counts)
        del lines[start:end]
    elif corruption == "duplicate_bond":
        lines.insert(end, lines[start])
    else:
        fields = lines[start].split()
        fields[2] = "4" if corruption == "changed_connectivity" else "999"
        lines[start] = " ".join(fields)
    mol2.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="(?i)MOL2.*bond|bond.*MOL2"):
        stage_supplied_ligand_parameters(**supplied_contract)


@pytest.mark.parametrize("bond_offset", [0, 3])
def test_supplied_mol2_rejects_explicit_numeric_bond_order_conflicts(supplied_contract, bond_offset):
    mol2 = supplied_contract["supplied_mol2"]
    lines = mol2.read_text(encoding="utf-8").splitlines()
    row = lines.index("@<TRIPOS>BOND") + 1 + bond_offset
    fields = lines[row].split()
    fields[3] = "3"
    lines[row] = " ".join(fields)
    mol2.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bond order"):
        stage_supplied_ligand_parameters(**supplied_contract)


@pytest.mark.parametrize("duplicate", [False, True])
def test_supplied_bond_mapping_uses_unique_explicit_atom_ids(supplied_contract, duplicate):
    mol2 = supplied_contract["supplied_mol2"]
    lines = mol2.read_text(encoding="utf-8").splitlines()
    section = ""
    for index, line in enumerate(lines):
        if line.startswith("@<TRIPOS>"):
            section = line
        elif section == "@<TRIPOS>ATOM" and line.strip():
            fields = line.split()
            fields[0] = "101" if duplicate else str(int(fields[0]) + 100)
            lines[index] = " ".join(fields)
        elif section == "@<TRIPOS>BOND" and line.strip():
            fields = line.split()
            fields[1:3] = [str(int(value) + 100) for value in fields[1:3]]
            lines[index] = " ".join(fields)
    mol2.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if duplicate:
        with pytest.raises(ValueError, match="atom IDs"):
            stage_supplied_ligand_parameters(**supplied_contract)
    else:
        assert stage_supplied_ligand_parameters(**supplied_contract)["supplied_mol2_bond_count"] == 27
