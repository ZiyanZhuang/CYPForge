# cypforge.equilibration_decision

## Purpose

Interpret the global audit and decide whether the system may enter longer free equilibration. This module must never approve production directly from nine-stage pre-MD.

## Inputs

```text
global_audit_dir
equilibration_decision_report
manifest_json
charge_audit_tsv
ligand_mapping_audit_tsv
heme_cym_topology_audit_tsv
p450_geometry_timeseries_tsv
stage_energy_summary_tsv
```

## Required Files

```text
<GLOBAL_AUDIT_DIR>/00_manifest.json
<GLOBAL_AUDIT_DIR>/10_equilibration_decision_report.md
```

## Allowed Decision States

```text
STOP_FIX_CORE1
STOP_FIX_CORE2
STOP_FIX_PROTONATION
STOP_FIX_SOLVATION
STOP_FIX_PRE_MD
WARN_HUMAN_REVIEW
ALLOW_1_5_NS_FREE_EQUILIBRATION
ALLOW_PRODUCTION_SETUP_ONLY_AFTER_EXTENDED_EQUILIBRATION
```

## Minimum Conditions for Longer Free Equilibration

All must be true:

```text
leap.log has no critical error
dry charge matches expectation
solvated system is neutral
ligand mapping audit passed
RESP/GAFF2 audit passed
HEM-CYM charge sanity passed
HEM-CYM topology passed
manifest-declared proximal CYM has no HG
GLH/HID local H network has no severe clash
Stage 09 free equilibration completed
temperature, density, and volume are stable enough for free equilibration
Fe-S, Fe-N, and heme plane are stable enough for free equilibration
manifest-declared ligand did not escape
no active-site ion invasion
```

## Decision Mapping

```text
Core 1 heme/CYM failure -> STOP_FIX_CORE1
Ligand mapping, RESP, GAFF2, or parmchk2 failure -> STOP_FIX_CORE2
GLH/HID/CYM rename or dry-charge failure -> STOP_FIX_PROTONATION
tleap, neutralization, box, ion, Fe-S topology failure -> STOP_FIX_SOLVATION
mdin/run_pre_md/ref/iwrap/stage failure -> STOP_FIX_PRE_MD
hard gates passed but unresolved warnings remain -> WARN_HUMAN_REVIEW
hard gates passed and warnings reviewed -> ALLOW_1_5_NS_FREE_EQUILIBRATION
after longer equilibration package is prepared but not run -> ALLOW_PRODUCTION_SETUP_ONLY_AFTER_EXTENDED_EQUILIBRATION
```

## Hard Gates

`FAIL` if:

```text
global audit status is FAIL
global audit output files are missing
hard gate table is missing
P450 geometry metrics are missing
decision report attempts to approve production from nine-stage pre-MD
```

## Warning Gates

`WARN` if:

```text
global audit status is WARN
warnings are recorded but not resolved
only one trajectory has been run
Stage 09 duration is below 5 ns
GLU275 watchlist remains scientifically sensitive
```

## Outputs

```text
<GLOBAL_AUDIT_DIR>/equilibration_decision_state.json
<GLOBAL_AUDIT_DIR>/equilibration_decision_state.md
```

## Failure Behavior

Return a stop state and list the exact upstream module to fix. Do not generate production MD commands.

## Scientific Interpretation

Nine-stage pre-MD can authorize only extended equilibration. Production requires additional equilibration and a separate production readiness check.
