# cypforge.global_audit

## Purpose

Run the full CYP450-specific global audit after pre-MD run and produce a single PASS/WARN/FAIL decision.

## Inputs

```text
ligand_mapping_manifest_json
protonation_manifest_json
solvation_manifest_json
pre_md_manifest_json
pre_md_run_validation_json
run_root
project_root
```

## Required Files

```text
<PROJECT_ROOT>/scripts/complex_global_audit.py
<LIGAND_MAPPING_MANIFEST_JSON>
<PROTONATION_MANIFEST_JSON>
<SOLVATION_MANIFEST_JSON>
<PRE_MD_MANIFEST_JSON>
<PRE_MD_RUN_VALIDATION_JSON>
```

## Command

```powershell
cd "<PROJECT_ROOT>"
$env:PYTHONPATH="<PROJECT_ROOT>\src"

python scripts\complex_global_audit.py `
  --ligand-mapping-manifest-json "<LIGAND_MAPPING_MANIFEST_JSON>" `
  --protonation-manifest-json "<PROTONATION_MANIFEST_JSON>" `
  --solvation-manifest-json "<SOLVATION_MANIFEST_JSON>" `
  --pre-md-manifest-json "<PRE_MD_MANIFEST_JSON>" `
  --pre-md-run-validation-json "<PRE_MD_RUN_VALIDATION_JSON>" `
  --output-dir "<RUN_ROOT>\18_global_cyp450_audit"
```

## Outputs

```text
<RUN_ROOT>/18_global_cyp450_audit/00_manifest.json
<RUN_ROOT>/18_global_cyp450_audit/01_charge_audit.tsv
<RUN_ROOT>/18_global_cyp450_audit/02_residue_protonation_audit.tsv
<RUN_ROOT>/18_global_cyp450_audit/03_ligand_mapping_audit.tsv
<RUN_ROOT>/18_global_cyp450_audit/04_heme_cym_topology_audit.tsv
<RUN_ROOT>/18_global_cyp450_audit/05_tleap_log_summary.txt
<RUN_ROOT>/18_global_cyp450_audit/06_mask_count_report.txt
<RUN_ROOT>/18_global_cyp450_audit/07_solvation_ion_audit.tsv
<RUN_ROOT>/18_global_cyp450_audit/08_stage_energy_summary.tsv
<RUN_ROOT>/18_global_cyp450_audit/09_p450_geometry_timeseries.tsv
<RUN_ROOT>/18_global_cyp450_audit/10_equilibration_decision_report.md
```

## Hard Gates

`FAIL` if:

```text
ligand mapping did not pass
RESP/GAFF2 charge audit did not pass
HEM/CYM topology did not pass
CYM SG has HG
Fe-S topology missing
Fe-Nporphyrin topology missing
dry charge differs from expected
solvated + ions total charge is not zero
any pre-MD stage failed
critical MD failure pattern found
ion invaded heme active site
manifest-declared ligand is missing from final topology
manifest-declared ligand is not chemically or geometrically plausible
Fe-S distances are unstable or outside hard range
Fe-N distances are unstable or outside hard range
heme plane is severely distorted
GLH/HID/CYM residue rename audit failed
```

## Warning Gates

`WARN` if:

```text
known generic Amber force-field warnings are present and recorded
tleap close-contact warnings persist without missing parameters
GLU275/ASP237/ASP335 watchlist remains unresolved
HIS/GLH local network requires human review
Stage 09 duration is below 5 ns and only supports equilibration-level claims
P450 reactive geometry remains plausible but not production-validated
```

## Failure Behavior

If status is `FAIL`, stop. Print the failing gate and the exact file to inspect. Do not call `equilibration_decision` as an allow gate.

## Audit Artifacts

The final equilibration decision report must include:

```text
global PASS/WARN/FAIL
hard gate table
warning table
charge summary
ligand mapping summary
protonation summary
heme/CYM topology summary
solvation/ion summary
pre-MD completion summary
P450 geometry metrics
next allowed action
```

## Scientific Interpretation

Global `PASS` or `WARN` after nine-stage pre-MD can only support extended free NPT equilibration. It cannot authorize production MD.
