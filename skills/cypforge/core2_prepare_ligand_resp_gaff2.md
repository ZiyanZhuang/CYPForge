# cypforge.core2_prepare_ligand_resp_gaff2

## Purpose

Validate supplied ligand parameters or generate new GAFF2/RESP parameters using SDF as the chemistry source and complex PDB as the pose source. Produce ligand-aware LEaP mapping.

## Inputs

```text
complex_pdb
ligand_template_sdf
ligand_resname
ligand_chain
formal_charge
spin
basis
points_per_atom
fit_method: multiwfn-resp | esp-lsq
pre_resp_relax: pbe-h-only | none
supplied_ligand_mol2: optional; requires supplied_ligand_frcmod
supplied_ligand_frcmod: optional; requires supplied_ligand_mol2
prepare_report_json
heme_resname
run_root
project_root
```

## Required Files

```text
<PROJECT_ROOT>/src/cypforge_core/cli.py
<COMPLEX_PDB>
<LIGAND_TEMPLATE_SDF>
<PREPARE_REPORT_JSON>
```

## Commands

Supplied-parameter path; this validates the files and does not run QM/ESP/RESP:

```powershell
cypforge module ligand prepare `
  --complex-pdb "<COMPLEX_PDB>" `
  --ligand-template-sdf "<LIGAND_TEMPLATE_SDF>" `
  --ligand-resname <LIGAND_RESNAME> `
  --formal-charge <FORMAL_CHARGE> `
  --supplied-mol2 "<SUPPLIED_LIGAND_MOL2>" `
  --supplied-frcmod "<SUPPLIED_LIGAND_FRCMOD>" `
  --output-dir "<RUN_ROOT>\10_ligand_gpu4pyscf_esp"
```

The supplied MOL2 must describe the same SDF graph and retain the confirmed
complex heavy-atom names and pose within 0.05 A RMSD. A generic parameter MOL2
with unrelated coordinates is rejected.

New-charge path with H-only pre-RESP cleanup:

```powershell
cypforge module ligand prepare `
  --complex-pdb "<COMPLEX_PDB>" `
  --ligand-template-sdf "<LIGAND_TEMPLATE_SDF>" `
  --ligand-resname <LIGAND_RESNAME> `
  --ligand-chain <LIGAND_CHAIN> `
  --formal-charge <FORMAL_CHARGE> `
  --spin <SPIN> `
  --basis <BASIS> `
  --points-per-atom <POINTS_PER_ATOM> `
  --fit-method <multiwfn-resp|esp-lsq> `
  --pre-resp-relax pbe-h-only `
  --output-dir "<RUN_ROOT>\10_ligand_gpu4pyscf_esp"
```

Generate ligand-aware LEaP mapping:

```powershell
cypforge module ligand leap `
  --complex-pdb "<COMPLEX_PDB>" `
  --prepare-report-json "<PREPARE_REPORT_JSON>" `
  --ligand-mol2 "<LIGAND_RESP_GAFF2_MOL2>" `
  --ligand-frcmod "<LIGAND_GAFF2_FRCMOD>" `
  --ligand-resname <LIGAND_RESNAME> `
  --ligand-chain <LIGAND_CHAIN> `
  --expected-ligand-charge <FORMAL_CHARGE> `
  --output-dir "<RUN_ROOT>\13_ligand_mapping_leapin" `
  --heme-resname <HEME_RESNAME>
```

## Outputs

```text
<RUN_ROOT>/10_ligand_gpu4pyscf_esp/*.mol2
<RUN_ROOT>/10_ligand_gpu4pyscf_esp/*.frcmod
<RUN_ROOT>/10_ligand_gpu4pyscf_esp/*mapping*.json
<RUN_ROOT>/10_ligand_gpu4pyscf_esp/*mapping*.csv
<RUN_ROOT>/10_ligand_gpu4pyscf_esp/*charge*
<RUN_ROOT>/10_ligand_gpu4pyscf_esp/ligand_parameterization_gate.json
<RUN_ROOT>/13_ligand_mapping_leapin/ligand_mapping_leapin_manifest.json
<RUN_ROOT>/13_ligand_mapping_leapin/ligand_mapping_leapin.in
<RUN_ROOT>/13_ligand_mapping_leapin/core2_decision_report.md
```

## Hard Gates

`FAIL` if:

```text
ligand atom mapping file missing
mapping was inferred from atom order
SDF/PDB ligand element mismatch
SDF/PDB heavy atom count mismatch
formal charge mismatch
only one supplied parameter file was provided
supplied MOL2 atom count, element composition, residue name, or charge sum differs from the SDF/run contract
supplied MOL2 heavy-atom names or pose differs from the confirmed complex PDB
heavy-atom mapping RMSD >= 0.05 A
mol2 atom names do not match PDB ligand atom names
RESP/ESP charge sum differs from formal charge beyond tolerance
RESP charges were injected by unverified index order
ligand residue charge in LEaP differs from expected charge beyond tolerance
parmchk2 reports ATTN NEEDS REVISION without manual audit
GAFF was used as a silent replacement for GAFF2
```

Recommended tolerances:

```text
charge sum tolerance: 1.0e-4 e for mol2/RESP table, 1.0e-3 e for LEaP residue sum
heavy mapping RMSD hard limit: 0.05 A
```

## Warning Gates

`WARN` if:

```text
Multiwfn unavailable and esp-lsq fallback was used
GPU4PySCF unavailable and CPU-only fitting was used by explicit request
RESP per-atom charges contain chemically unusual outliers requiring review
aromaticity or amide bond perception required manual confirmation
symmetry creates multiple valid atom mappings
```

## Failure Behavior

Stop. Do not rescue by atom order. Do not proceed to protonation finalization, solvation, or MD.

## Audit Artifacts

Decision report must include:

```text
complex PDB path
ligand SDF path
ligand residue name and chain
formal charge
fit method
pre-RESP relaxation mode
mapping file path
heavy atom RMSD
charge sum
mol2 path
frcmod path
parmchk2 warning summary
PASS/WARN/FAIL
```

## Scientific Interpretation

Neutral ligand total charge only proves charge-sum consistency. It does not prove correct atom mapping, correct bond order, correct aromaticity, or correct per-atom RESP assignment.
