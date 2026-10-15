# CYPForge Execution Plan

This plan defines the strict execution order for the CYPForge skill shell. It is intended for an automation agent or CLI controller.

## Ordered Modules

1. `cypforge.environment_check`
2. `cypforge.core1_prepare_heme_cym`
3. `cypforge.core2_prepare_ligand_resp_gaff2`
4. `cypforge.core3_finalize_protonation`
5. `cypforge.core3_solvate_ionize`
6. `cypforge.core3_render_pre_md`
7. `cypforge.core3_run_pre_md`
8. `cypforge.global_audit`
9. `cypforge.equilibration_decision`
10. `cypforge.production_readiness_check`

## Resume Policy

The controller skips completed `PASS` modules and accepted `WARN` modules, then
retries the first pending, failed or interrupted module after review. A failed
gate never authorizes a later module. `--max-retries` supports only 0; review the
cause before an explicit retry. Use `prep-only` for a no-MD continuation;
`resume` can execute MD beyond the `PREPARED` boundary.

Do not resume from:

```text
missing or corrupt run checkpoint
unfixed FAIL state
unreviewed WARN state
changed input file while retaining cached upstream gates
```

Use a new run for changed ligand SDF, complex PDB or heme state so that upstream
gates run again. Apply protonation decisions before downstream consumption;
once solvation or later work has started/cached outputs, `protonation apply`
rejects the edit before writes and requires a new run.

## Required Manifests

```text
01_heme_only/prepare_report.json
02_heme_mapping_leapin/heme_mapping_leapin_manifest.json
10_ligand_gpu4pyscf_esp/complex_pose_staging_manifest.json
10_ligand_gpu4pyscf_esp/ligand_parameterization_gate.json
13_ligand_mapping_leapin/ligand_mapping_leapin_manifest.json
14_complex_protonation_finalize/protonation_finalize_manifest.json
15_complex_solvation_ionization/solvation_manifest.json
15_complex_solvation_ionization/solvation_ionization_validation.json
17_complex_pre_md_equilibration/complex_pre_md_equilibration_manifest.json
17_complex_pre_md_equilibration/complex_pre_md_equilibration_run_validation.json
18_global_cyp450_audit/00_manifest.json
18_global_cyp450_audit/equilibration_decision_state.json
production_readiness_state.json
```

Each path is required when its producing module completes; a `PREPARED` run
has no MD-run, global-audit or final-decision output yet. `run_config.json` and
`run_manifest.json` hold configuration and module/step state. Environment checks
record step results and logs there; they do not generate an environment manifest.
The supplied-parameter route additionally writes
`10_ligand_gpu4pyscf_esp/supplied_ligand_parameters_manifest.json`; new-fit routes
have their own fitting artifacts. `protonation apply --set` writes the default
`protonation_decision.json`; `--decision-json` keeps the caller's reviewed input
path without copying it there. Use `run_config.json`'s
`protonation_decision_json` field to locate the selected decision.

## Command Logging

Completed subprocess attempts use a unique UUID basename:

```text
<RUN_ROOT>/logs/<module>/<attempt_uuid>_command.txt
<RUN_ROOT>/logs/<module>/<attempt_uuid>_stdout.txt
<RUN_ROOT>/logs/<module>/<attempt_uuid>_stderr.txt
```

The command log records:

```text
working directory
full command
step name and kind
start/completion timestamps and status
exit code
```

Exit code and stdout/stderr paths are also stored in the checkpoint StepRecord.
Configuration belongs to `run_config.json`; source hashes are recorded by the
producing stage manifests where available. There is no separate exit-code file.
Failed launches/timeouts can lack console files; inspect the command log and
StepRecord error before continuing. Raw logs/configuration contain local paths;
use `cypforge diagnose` for a redacted shareable report.

## Stop Policy

Stop immediately on any hard gate failure. The next module must not run.

If a module returns `WARN`, the controller may continue only if the warning is explicitly documented as reviewed in the module decision report or in a user-provided review note.

## Production Policy

This skill shell must not run production MD. It may only:

```text
generate audited pre-MD inputs
run nine-stage pre-MD equilibration
run global audit
allow additional 1-5 ns free equilibration as a next action
check whether production setup is reasonable after extended equilibration
```

It must not produce a final claim of production readiness from nine-stage pre-MD alone.

## Minimum Human Reports

Before leaving the workflow, the controller must identify the current state:

```text
STOP_FIX_CORE1
STOP_FIX_CORE2
STOP_FIX_PROTONATION
STOP_FIX_SOLVATION
STOP_FIX_PRE_MD
WARN_HUMAN_REVIEW
ALLOW_1_5_NS_FREE_EQUILIBRATION
READY_FOR_PRODUCTION_SETUP
```

The report must name:

```text
latest completed module
decision state
failed gate or warning gate
exact file to inspect
next allowed action
```
