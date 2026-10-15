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
