# cypforge.environment_check

## Purpose

Verify that the CYPForge source tree, Python import path, run root, WSL Amber environment, and required CLI tools are available before any scientific work.

## Inputs

```text
project_root
run_root
wsl_user
amber_setup_script
required_tools
optional_tools
```

Recommended defaults:

```powershell
$PROJECT_ROOT="<PROJECT_ROOT>"
# Windows default: C:\cypforge_runs\<run_name>; POSIX: ~/cypforge_runs/<run_name>.
# Set $env:CYPFORGE_RUNS_DIR (or use --run-root) to override.
$RUN_ROOT="<run-root>"
$WSL_USER="<your-wsl-user>"
$AMBER_SETUP="<wsl-home>/amber25/amber.sh"
$REQUIRED_TOOLS=@("tleap","pmemd.cuda","cpptraj","antechamber","parmchk2")
$OPTIONAL_TOOLS=@("reduce","propka","pdb2pqr","Multiwfn")
```

## Required Files

```text
<PROJECT_ROOT>/src/cypforge_core
```

## Commands

```powershell
cd "<PROJECT_ROOT>"
$env:PYTHONPATH="<PROJECT_ROOT>\src"
New-Item -ItemType Directory -Force "<RUN_ROOT>\00_environment_check" | Out-Null

python -c "import cypforge_core; print('OK')"

wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && tleap -h"
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && pmemd.cuda -h"
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && cpptraj -h | head"
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && antechamber -h | head"
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && parmchk2 -h | head"
```

Optional probes:

```powershell
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && command -v reduce || true"
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && command -v propka || true"
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && command -v pdb2pqr || true"
wsl -u <WSL_USER> -e bash -lc "source <AMBER_SETUP> && command -v Multiwfn || true"
python -c "import gpu4pyscf; print('GPU4PySCF OK')"
```

## Outputs

```text
<RUN_ROOT>/00_environment_check/environment_manifest.json
<RUN_ROOT>/00_environment_check/tool_versions.txt
<RUN_ROOT>/00_environment_check/environment_decision_report.md
```

## Hard Gates

`FAIL` if:

```text
project_root does not exist
scripts directory missing
src/cypforge_core missing
Python cannot import cypforge_core
run_root cannot be created
tleap unavailable
pmemd.cuda unavailable
cpptraj unavailable
antechamber unavailable
parmchk2 unavailable
```

## Warning Gates

`WARN` if:

```text
reduce unavailable
propka unavailable
pdb2pqr unavailable
Multiwfn unavailable
GPU4PySCF unavailable when GPU RESP was requested
project path contains non-ASCII characters and WSL command path conversion has not been tested
```

## Failure Behavior

Stop before Core 1. Do not prepare heme, ligand, solvation, or MD files.

## Audit Artifacts

The manifest must record:

```text
project_root
run_root
wsl_user
amber_setup_script
PYTHONPATH
tool probe commands
tool probe exit codes
tool version snippets
PASS/WARN/FAIL status
```

## Scientific Interpretation

This module only verifies executable availability. It does not validate chemistry, force fields, topology, or MD stability.
