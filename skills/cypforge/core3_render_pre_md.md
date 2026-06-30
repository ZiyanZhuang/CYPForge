# cypforge.core3_render_pre_md

## Purpose

Generate the nine-stage conservative CYP450 pre-MD protocol and validate that restrained and free-stage command logic is safe before any MD is run.

## Inputs

```text
solvation_manifest_json
protocol_config_json optional
run_root
project_root
```

## Required Files

```text
<PROJECT_ROOT>/scripts/complex_pre_md_equilibration.py
<SOLVATION_MANIFEST_JSON>
```

## Commands

Default render:

```powershell
cd "<PROJECT_ROOT>"
$env:PYTHONPATH="<PROJECT_ROOT>\src"

python scripts\complex_pre_md_equilibration.py `
  --solvation-manifest-json "<SOLVATION_MANIFEST_JSON>" `
  --output-dir "<RUN_ROOT>\17_complex_pre_md_equilibration"
```

Render from user-edited config:

```powershell
python scripts\complex_pre_md_equilibration.py `
  --solvation-manifest-json "<SOLVATION_MANIFEST_JSON>" `
  --protocol-config-json "<RUN_ROOT>\17_complex_pre_md_equilibration\pre_md_protocol_config.json" `
  --output-dir "<RUN_ROOT>\17_complex_pre_md_equilibration" `
  --no-write-default-config
```

## Nine Stages

```text
01_min_hydrogens
02_min_solvent_ions
03_min_restrained_solute
04_min_soft_restrained
05_heat_nvt_0_310
06_nvt_restrained_hold
07_npt_restrained_density
08_npt_soft_release
09_npt_free_equilibration
```

## Mandatory MD Rules

```text
all restrained stages must pass -ref system_lig_solv.rst7
all restrained stages must use iwrap=0
free stage must use ntr=0
free stage must use iwrap=1
free stage must not pass -ref
restrained solute-heavy mask should be '!(:WAT,Na+,Cl-) & !@H='
mask atom counts must be audited
```

## Outputs

```text
<RUN_ROOT>/17_complex_pre_md_equilibration/pre_md_protocol_config.json
<RUN_ROOT>/17_complex_pre_md_equilibration/mdin/*.in
<RUN_ROOT>/17_complex_pre_md_equilibration/run_pre_md.sh
<RUN_ROOT>/17_complex_pre_md_equilibration/run_pre_md_1_8.sh
<RUN_ROOT>/17_complex_pre_md_equilibration/run_pre_md_9.sh
<RUN_ROOT>/17_complex_pre_md_equilibration/run_pre_md_windows.ps1
<RUN_ROOT>/17_complex_pre_md_equilibration/complex_pre_md_equilibration_manifest.json
```

## Hard Gates

`FAIL` if:

```text
any of the nine mdin files is missing
run_pre_md.sh missing
complex_pre_md_equilibration_manifest.json missing
restrained stage lacks -ref
restrained stage uses iwrap=1
free stage uses -ref
free stage has ntr=1
free stage has iwrap=0 unless explicitly justified for non-wrapped diagnostic output
cpptraj pairing probe command is absent from run script
restraint mask is empty or selects solvent/ions unexpectedly
```

## Warning Gates

`WARN` if:

```text
Stage 09 is shorter than 5 ns
cutoff differs between stages
temperature differs from intended biological temperature
barostat or thermostat settings deviate from configured defaults
mask names do not match actual ion residue names and require manual review
```

## Failure Behavior

Stop before MD execution. Do not allow `pmemd.cuda` to run with unsafe reference/imaging logic.

## Audit Artifacts

Decision report must include:

```text
mdin file list
stage table
ntr/iwrap/ref status for every stage
restraint masks
mask atom counts if available
cpptraj pairing probe presence
PASS/WARN/FAIL
```

## Scientific Interpretation

This module validates MD input construction logic. It does not validate dynamics. Dynamics are only assessed after `core3_run_pre_md` and `global_audit`.
