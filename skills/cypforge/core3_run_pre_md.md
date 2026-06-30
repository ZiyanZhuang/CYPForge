# cypforge.core3_run_pre_md

## Purpose

Run the nine-stage pre-MD workflow through WSL Amber and stop at the first failed stage.

## Inputs

```text
pre_md_dir
wsl_user
amber_setup_script
```

## Required Files

```text
<PRE_MD_DIR>/run_pre_md.sh
<PRE_MD_DIR>/complex_pre_md_equilibration_manifest.json
<PRE_MD_DIR>/mdin/01_min_hydrogens.in
...
<PRE_MD_DIR>/mdin/09_npt_free_equilibration.in
```

## Command

Foreground:

```powershell
$PREMD="<PRE_MD_DIR>"
$PREMD_WSL=(wsl -u <WSL_USER> -e wslpath -a "$PREMD")

wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP_SCRIPT> && cd '$PREMD_WSL' && bash run_pre_md.sh"
```

Background:

```powershell
$PREMD="<PRE_MD_DIR>"
$PREMD_WSL=(wsl -u <WSL_USER> -e wslpath -a "$PREMD")

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
  "-NoProfile",
  "-Command",
  "wsl -u <WSL_USER> -e bash -lc `"source <AMBER_SETUP_SCRIPT> && cd '$PREMD_WSL' && bash run_pre_md.sh > run_pre_md.stdout 2> run_pre_md.stderr`""
)
```

## Outputs

```text
<PRE_MD_DIR>/run/*.out
<PRE_MD_DIR>/*.rst7
<PRE_MD_DIR>/run/*.nc
<PRE_MD_DIR>/run/stage_status.tsv
<PRE_MD_DIR>/run/run_pre_md.started_at.txt
<PRE_MD_DIR>/run/run_pre_md.finished_at.txt
<PRE_MD_DIR>/run/run_pre_md.exit_code.txt
<PRE_MD_DIR>/complex_pre_md_equilibration_run_validation.json
```

## Hard Fail Patterns

`FAIL` if any output, stderr, or validation log contains:

```text
SHAKE failure
vlimit exceeded
illegal memory access
nan
NaN
Ewald bomb
missing restraint reference
cannot find inpcrd
cannot find prmtop
PME error
abnormal termination
```

Also `FAIL` if:

```text
any stage lacks normal termination
expected restart for next stage is missing
expected NetCDF trajectory for MD stages is missing
Stage 09 free equilibration did not run after all prior stages passed
```

## Warning Gates

`WARN` if:

```text
temperature or density is noisy but not fatal
pressure is reported as unavailable by pmemd.cuda
restraint energy remains high late in restrained release
Stage 09 completes but trajectory metrics require human review
```

## Failure Behavior

Stop at first failed stage. Do not skip stages. Do not rerun from a later stage without explicit user instruction and a recorded restart source.

## Audit Artifacts

Decision report must include:

```text
stage completion table
normal termination markers
final restart path
final trajectory path
fatal pattern scan
temperature and density summary if available
PASS/WARN/FAIL
```

## Scientific Interpretation

A completed nine-stage pre-MD run includes free NPT equilibration. It does not authorize production. It provides input for global CYP450-specific audit and possible extended NPT equilibration.
