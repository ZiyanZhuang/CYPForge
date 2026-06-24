# cypforge.production_readiness_check

## Purpose

Prevent premature production MD. This module is conservative and must not run production.

## Inputs

```text
global_audit_dir
extended_equilibration_dir
extended_equilibration_qc_manifest
replica_plan optional
```

## Required Evidence

```text
nine-stage pre-MD run passed or WARN was reviewed
additional 1-5 ns free NPT equilibration completed
extended equilibration normal-end evidence
Fe-S distribution summary
Fe-N distribution summary
heme plane stability summary
ligand pose stability summary
NCT reactive geometry summary
heme propionate salt-bridge network summary
GLH419/HID55/HID299/HID386 network summary
active-site ion invasion audit
ligand mapping and charge audit with no unresolved hard warnings
```

## Hard Gates

`FAIL` if:

```text
nine-stage pre-MD run did not pass hard gates
additional 1-5 ns free NPT equilibration is missing
extended equilibration failed or lacks normal termination
Fe-S distribution is unstable or outside plausible range
Fe-N distribution is unstable or outside plausible range
heme plane is severely distorted
ligand leaves pocket
NCT reactive geometry becomes uninterpretable
active-site ion invasion occurs
GLH419/HID55/HID299/HID386 networks collapse into persistent clash
ligand mapping warning remains unresolved
RESP/GAFF2 charge warning remains unresolved
HEM/CYM topology warning remains unresolved
decision report claims production readiness from nine-stage pre-MD run alone
```

## Warning Gates

`WARN` if:

```text
only one extended equilibration trajectory exists
GLU275 watchlist remains sensitive and no GLH275 control smoke was run
heme propionate salt-bridge network changes substantially but remains plausible
pocket water network changes substantially but remains plausible
pressure is unavailable in pmemd.cuda output and density is used instead
```

## Outputs

```text
production_readiness_state.json
production_readiness_report.md
```

Allowed states:

```text
NOT_READY_FIX_UPSTREAM
NOT_READY_NEEDS_EXTENDED_EQUILIBRATION
NOT_READY_NEEDS_HUMAN_REVIEW
READY_FOR_PRODUCTION_SETUP
```

`READY_FOR_PRODUCTION_SETUP` means the user may generate production packages. It does not mean this skill shell has run production.

## Recommended Production Plan

For serious analysis:

```text
at least 3 replicas
at least 100 ns each
different random seeds
report Fe-S distribution
report Fe-N distribution
report ligand pose clusters
report Fe-reactive atom distance
report heme propionate network occupancy
report GLH/HID network occupancy
report pocket water occupancy
report ligand torsion distributions
do not report only protein RMSD
```

## Failure Behavior

Do not produce production `pmemd.cuda` commands if any hard gate fails. Emit the exact missing evidence or failed metric.

## Scientific Interpretation

Production readiness is an evidence threshold, not an MD command. Passing this check supports production setup; it does not prove mechanistic conclusions or publication-level sampling.
