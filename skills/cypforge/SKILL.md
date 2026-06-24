---
name: cypforge
description: Strict orchestration shell for CYPForge CYP450 HEME/CYM ligand Amber workflows. Use to run or audit Core 1 heme/CYM preparation, Core 2 ligand SDF/PDB mapping with GAFF2/RESP, Core 3 protonation/solvation/pre-MD, and production-readiness gating.
metadata:
  short-description: CYPForge strict CYP450-heme-ligand workflow shell
---

# CYPForge Mini Skill Shell

This skill shell is an orchestration and audit layer around the existing CYPForge scripts. It is not a replacement molecular simulation package. It must call the existing project scripts, AmberTools, Amber, and cpptraj; capture logs; enforce hard gates; and stop when chemistry or MD constraints fail.

## Non-Negotiable Scientific Rules

1. SDF is the ligand chemistry source: graph, bond order, aromaticity, formal charge, and GAFF2 atom typing source.
2. PDB is the protein/HEME/ligand pose source: coordinates, residue names, atom names, and chain identifiers.
3. GAFF2/parmchk2 define ligand bonded and van der Waals parameters. GAFF is not a silent drop-in replacement.
4. GPU4PySCF/Multiwfn or ESP-LSQ defines RESP/ESP charges.
5. Amber/tLeap/pmemd.cuda/cpptraj are the final construction, charge, MD execution, and trajectory audit tools.
6. Successful `tleap` execution is not proof of chemical correctness.
7. Correct total charge is not proof of correct protonation or per-atom charge mapping.
8. A 20 ns free NPT equilibration is not production readiness.
9. A hard gate failure stops the workflow. Do not continue to the next core.
10. Do not auto-correct residue names unless an explicit decision JSON requires it.
11. Do not infer ligand atom mapping from atom order.
12. Do not use PDB bond order as ligand chemistry truth.
13. Do not hide warnings from `tleap`, `pmemd.cuda`, `cpptraj`, `parmchk2`, PROPKA, `reduce`, or RESP fitting.
14. Do not run production MD from this skill shell.
15. Do not infer, propose, or execute transmembrane helix trimming unless the human user explicitly provides exact chain:residue ranges and explicitly confirms trimming. Automatic TM prediction or visual guessing is forbidden for deletion.

## Environment Assumptions

Default Windows project root:

```powershell
<PROJECT_ROOT>
```

Recommended run root:

```powershell
# Windows default if $env:CYPFORGE_RUNS_DIR is not set: C:\cypforge_runs\<run_name>
# POSIX default if $CYPFORGE_RUNS_DIR is not set:       ~/cypforge_runs/<run_name>
# Override either with $env:CYPFORGE_RUNS_DIR (global) or --run-root (per run).
```

Required PowerShell setup:

```powershell
cd "<PROJECT_ROOT>"
$env:PYTHONPATH="<PROJECT_ROOT>\src"
```

Default Amber through WSL:

```powershell
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP_SCRIPT> && <command>"
```

Required Amber/AmberTools commands:

```text
tleap
pmemd.cuda
cpptraj
antechamber
parmchk2
```

Optional tools:

```text
reduce
propka
pdb2pqr
Multiwfn
GPU4PySCF
```

If `tleap`, `pmemd.cuda`, or `cpptraj` are unavailable, stop before scientific work.

## Skill Modules

Use these modules in order unless resuming from a validated manifest:

1. `environment_check.md`
2. `core1_prepare_heme_cym.md`
3. `core2_prepare_ligand_resp_gaff2.md`
4. `core3_finalize_protonation.md`
5. `core3_solvate_ionize.md`
6. `core3_render_pre_md.md`
7. `core3_run_pre_md.md`
8. `global_audit.md`
9. `equilibration_decision.md`
10. `production_readiness_check.md`

Each module defines inputs, outputs, required files, commands, hard gates, warning gates, failure behavior, audit artifacts, and decision-report requirements.

## Required Execution Discipline

For every command:

```text
record working directory
record full command
record stdout path
record stderr path
record exit code
record generated files
record PASS/WARN/FAIL decision
```

Recommended log layout:

```text
<RUN_ROOT>/
  00_environment_check/
  01_heme_only/
  02_heme_mapping_leapin/
  10_ligand_gpu4pyscf_esp/
  13_ligand_mapping_leapin/
  14_complex_protonation_finalize/
  15_complex_solvation_ionization/
  17_complex_pre_md_equilibration/
  18_global_cyp450_audit/
  decisions/
  logs/
```

## Status Semantics

`PASS` means all hard gates passed and no significant unresolved warnings remain.

`WARN` means hard gates passed, but human review is required before stronger claims or longer simulations.

`FAIL` means stop immediately. Do not proceed to the next core, longer equilibration, production setup, or production MD.

## Absolute Stop Conditions

Stop if any of these occur:

```text
Amber/tLeap/pmemd.cuda/cpptraj unavailable
Python cannot import cypforge_core
ligand atom mapping missing or failed
SDF/PDB ligand element mismatch
RESP charge injection not verified
unresolved parmchk2 ATTN NEEDS REVISION
HEM Fe missing
CYM remains CYS or CYM SG has HG
Fe-S or Fe-N topology cannot be confirmed
transmembrane trimming requested without exact human-provided chain:residue ranges and explicit confirmation
GLH/HID/CYM residue rename fails
dry charge does not match expected model
tleap has critical missing parameter or unknown atom/residue
solvated system is not neutral after ionization
restrained MD command lacks -ref
restrained MD uses iwrap=1
free MD uses -ref
pmemd.cuda reports SHAKE/vlimit/Ewald/NaN/PME fatal pattern
global audit status is FAIL
```

## Human-Readable Reports

Every skill module should write or update a human-readable report with:

```text
module name
inputs
commands executed
files generated
hard gate results
warning gate results
final PASS/WARN/FAIL
next allowed action
files to inspect on failure
```

Do not use vague reassuring language without a named gate and evidence file.
