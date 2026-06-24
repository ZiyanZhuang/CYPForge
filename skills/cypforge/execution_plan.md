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

Resuming is allowed only from a module whose output manifest exists and whose decision report is `PASS` or explicitly accepted `WARN`.

Do not resume from:

```text
missing manifest
FAIL state
unreviewed WARN state
changed input file without re-running upstream gates
changed protonation decision JSON without re-running Core 3 from finalization
changed ligand SDF or complex PDB without re-running Core 2
changed heme state without re-running Core 1 and downstream modules
```

## Required Manifests

```text
00_environment_check/environment_manifest.json
01_heme_only/prepare_report.json
02_heme_mapping_leapin/heme_mapping_manifest.json
13_ligand_mapping_leapin/ligand_mapping_manifest.json
14_complex_protonation_finalize/protonation_finalize_manifest.json
15_complex_solvation_ionization/solvation_manifest.json
17_complex_pre_md_equilibration/pre_md_manifest.json
17_complex_pre_md_equilibration/pre_md_run_validation.json
18_global_cyp450_audit/00_manifest.json
18_global_cyp450_audit/equilibration_decision_state.json
production_readiness_state.json
```

## Command Logging

Every command must write:

```text
<RUN_ROOT>/logs/<module>/<timestamp>_command.txt
<RUN_ROOT>/logs/<module>/<timestamp>_stdout.txt
<RUN_ROOT>/logs/<module>/<timestamp>_stderr.txt
<RUN_ROOT>/logs/<module>/<timestamp>_exit_code.txt
```

The command log must include:

```text
working directory
full command
environment variables relevant to CYPForge
input file hashes when practical
exit code
```

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
