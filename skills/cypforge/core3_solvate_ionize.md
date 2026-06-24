# cypforge.core3_solvate_ionize

## Purpose

Build the final solvated and neutralized Amber system using the finalized protein-HEME-CYM-ligand complex.

## Inputs

```text
protonation_manifest_json
protein_force_field: ff14SB | ff19SB
water_leaprc
water_model
box_type: oct | box
buffer_a
neutralizing_anion
run_root
project_root
```

## Required Files

```text
<PROJECT_ROOT>/scripts/complex_solvation_ionization.py
<PROTONATION_MANIFEST_JSON>
```

## Command

```powershell
cd "<PROJECT_ROOT>"
$env:PYTHONPATH="<PROJECT_ROOT>\src"

python scripts\complex_solvation_ionization.py `
  --protonation-manifest-json "<PROTONATION_MANIFEST_JSON>" `
  --output-dir "<RUN_ROOT>\15_complex_solvation_ionization" `
  --protein-force-field ff19SB `
  --water-leaprc leaprc.water.tip3p `
  --water-model TIP3PBOX `
  --box-type oct `
  --buffer-a 10.0 `
  --neutralizing-anion Cl-
```

## Outputs

```text
<RUN_ROOT>/15_complex_solvation_ionization/system_lig_solv.prmtop
<RUN_ROOT>/15_complex_solvation_ionization/system_lig_solv.rst7
<RUN_ROOT>/15_complex_solvation_ionization/system_lig_solv_tleap.pdb
<RUN_ROOT>/15_complex_solvation_ionization/*visual_check*.pdb
<RUN_ROOT>/15_complex_solvation_ionization/solvation_manifest.json
<RUN_ROOT>/15_complex_solvation_ionization/leap.log
<RUN_ROOT>/15_complex_solvation_ionization/core3_solvation_decision_report.md
```

## Hard Gates

`FAIL` if:

```text
system_lig_solv.prmtop missing
system_lig_solv.rst7 missing
leap.log missing
leap.log contains unknown residue
leap.log contains unknown atom type
leap.log contains missing bond/angle/dihedral parameters
leap.log creates unexpected heavy atoms
dry charge differs from expected model charge
solvated + ions total charge is not approximately zero
mode11 dry +6 model is not neutralized by six Cl- ions before optional salt
HEM/CYM combined charge sanity check fails
Fe-S topology missing
Fe-Nporphyrin topology missing
CYM410 SG has HG
ion is placed in heme Fe coordination sphere
```

Critical log grep pattern:

```text
fatal|error|unknown|missing|not found|created a new atom
```

Generic Amber force-field load-time warnings may be `WARN` only if they are known, recorded, and unrelated to the modeled residues.

## Warning Gates

`WARN` if:

```text
leap.log contains close-contact warnings without missing parameters
ion is near heme pocket but not Fe-coordinating
box buffer is below recommended 10 A
water model and leaprc combination is uncommon and requires review
ff14SB selected instead of ff19SB without justification
```

## Failure Behavior

Stop. Do not render MD inputs if tLeap construction, charge, topology, or active-site ion placement fails.

## Audit Artifacts

Decision report must include:

```text
force field
water leaprc and water model
box type
buffer
neutralizing ion count
water count
atom count
dry charge
solvated pre-ion charge
post-ion charge
HEM/CYM charge sanity
Fe-S/Fe-N topology summary
leap.log warning/error summary
PASS/WARN/FAIL
```

## Scientific Interpretation

Solvation success proves that Amber files were created under the selected force-field stack. It does not prove protonation correctness, ligand mapping correctness, or MD stability unless earlier gates and later pre-MD audits pass.
