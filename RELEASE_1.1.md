# CYPForge 1.1

Independent maintenance release **v1.1.0** on **release/1.1**, based on
`427afd606144d388d92a684082c29cc514018154` (source package version 1.3.0).
This line does not merge into or supersede the default branch. Existing 1.2/1.3
source history is retained. Neither the v1.1.0 tag nor its GitHub Release existed
at the authenticated pre-publication check; publication must recheck both.

## Repairs

52 reproduced defects have separate repair commits and red/green records in
[DEBUG_STATE.md](https://github.com/ZiyanZhuang/CYPForge/blob/release/1.1/DEBUG_STATE.md):
**1 P0, 41 P1, 10 P2**.

- **P0:** repeated/concurrent initialization could reset an existing run (F01).
- **P1, persistence:** atomic checkpoint/config/report commits, bounded retries
  for Windows/DrvFS read conflicts, exclusive Windows/WSL run ownership, retained
  diagnostics redaction, and crash recovery (F03–F05, F27–F28, F30).
- **P1, workflow/gates:** fail closed on unknown/conflicting/invalid gates,
  preserve nested evidence, correct PAUSED/PREPARED/resume, normalize final
  decision statuses, reject substituted/missing/empty artifacts, and keep context
  actions behind their decision gate (F06, F12–F19, F32, F44–F46).
- **P1, no-QM preparation:** route-aware environment checks, identity-preserving
  Core 1→2 ligand staging, original-chain protonation selection, finite supplied
  charges, actual MOL2 bond connectivity and explicit numeric bond-order conflict
  checks, and reject changed decisions after downstream inputs were consumed
  (F08–F10, F37–F38, F40, F50).
- **P1, execution:** preserve subprocess exit/log encoding and literal paths;
  harden script/launcher quoting, split targets/dependencies and exit codes;
  invalidate old selected outputs; stop at the first bad stage, including fatal
  stdout/stderr; resolve setup filenames and native Linux Bash correctly
  (F07, F11, F24–F26, F31, F33–F34, F36, F39, F41–F42, F48–F49, F52).
- **P2:** keep separate same-second logs; validate advisory protonation input;
  refresh docs provenance; close/rollback SQLite transactions; standardize CLI
  errors and missing-state exits; preserve custom split-stage names; explicitly
  reject unsupported nonzero retry counts; retain unique logs at the measured
  Windows path boundary (F02, F20–F23, F29, F35, F43, F47, F51).

No new dependencies, force-field/protocol changes, aromatic perception algorithm,
software installation, or license changes were introduced.

## Regression and pressure evidence

- Windows/Python 3.12.14: **255 passed, 6 skipped**.
- WSL Ubuntu 24.04/Python 3.12.3: **251 passed, 10 skipped**.
- Each suite has one existing legacy-wrapper deprecation warning. Six tests need
  absent optional external fixtures; WSL also skips four native Windows cases
  (two launchers, cross-OS lock ownership and the Windows path-length boundary).
- Original baseline: 97 passed, 6 skipped. Every repair ran its focused tests and
  the full native suite; the ledger records each intermediate result.
- Native and WSL pressure each completed 600 checkpoint saves, 200 status calls,
  and 200 diagnosis calls without API errors after the persistence fixes. A
  separate 24-process real CLI batch and 1,800 concurrent saves also passed.
- Ten-process initialization races produced exactly one owner; six repeated init
  attempts preserved files. Four native/WSL lock directions rejected concurrent
  writers and recovered after an owned holder exited inside the lock with
  `os._exit(73)`. All owned child processes were reaped.
- Fifty simulated ten-stage control-flow cases covered WARN acceptance, first
  FAIL, reviewed resume, and interrupted RUNNING states. Additional CLI/gate
  probes exercised exit 0/2/3 and invalid/unknown/conflicting gate data.
- Thirty-eight owned fake-engine observations covered nine-stage success,
  failure/recovery, stale no-op reruns, substituted paths, fatal console streams,
  empty/missing outputs, custom directories and split-stage names. Chinese,
  repeated-space, apostrophe and brace paths were exercised. No real engine ran.

Reproduce the suite using an existing Python environment with pytest and numpy:

```powershell
$env:PYTHONPATH = "$PWD\src"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -B -m pytest tests -q
```

## Real 4EJJ smoke, no MD

The installed Amber/AmberTools environment provided `tleap`, `cpptraj` V7.6.2 and
the configured pmemd executable. Multiwfn, antechamber and parmchk2 were absent;
the reviewed supplied-parameter route did not need them. The default Windows
Python lacked pytest, so an existing Python 3.12 environment was selected without
installation. All runtime environment changes were process-local.

Commands below are the portable form of the measured smoke. Set AMBER_SH to the
existing WSL setup file and CYPFORGE_RUNS_DIR to a new writable run directory.
The final measured run name was `final_4ejj  中文's {ligand_resname} reviewed`,
using frozen source revision `b780f6322472387482ec11c0a6f6d30fccbc580f`.

```powershell
$env:PYTHONPATH = "$PWD\src"
$run = "final_4ejj  中文's {ligand_resname} reviewed"
python -B -m cypforge_core.cli init $run `
  --pdb benchmark/4EJJ/4EJJ_CPD1_NCT.pdb `
  --sdf benchmark/4EJJ/nicotine.sdf --heme-state CPDI `
  --ligand-resname NCT --blank-ligand-chain `
  --supplied-ligand-mol2 benchmark/4EJJ/NCT_multiwfn_resp.mol2 `
  --supplied-ligand-frcmod benchmark/4EJJ/NCT.frcmod
python -B -m cypforge_core.cli prep-only $run
python -B -m cypforge_core.cli protonation recommend $run --ph 7.4
# Only after the user explicitly accepted these benchmark decisions:
python -B -m cypforge_core.cli protonation apply $run `
  --set A:GLH419=GLH --set A:HID55=HID --set A:HID299=HID --set A:HID386=HID
python -B -m cypforge_core.cli prep-only $run
python -B -m cypforge_core.cli status $run
python -B -m cypforge_core.cli context $run
python -B -m cypforge_core.cli diagnose $run
```

Observed exits: init 0; first prep-only 3 (review pause); recommend/apply 0;
second prep-only/status/context/diagnose 0. User confirmation reused the recorded
4EJJ GLU419→GLH and HIE55/299/386→HID decisions; the supplied structure already
had those target names, so application used idempotent current-state selectors.
No new protonation inference was silently applied.

Endpoint: **PREPARED**, six modules PASS through core3_render_pre_md, four modules
PENDING starting with core3_run_pre_md. The nine input stages were rendered only.
Important manifests under the run root:

- `run_manifest.json`
- `10_ligand_gpu4pyscf_esp/supplied_ligand_parameters_manifest.json`
- `protonation_decision.json`
- `14_complex_protonation_finalize/protonation_finalize_manifest.json`
- `15_complex_solvation_ionization/solvation_ionization_validation.json`
- `17_complex_pre_md_equilibration/complex_pre_md_equilibration_manifest.json`

Independent static calculation on the real prepared system found **71,698 atoms,
21,833 residues, 21,360 waters, 6 Cl−**, net charge approximately
**−1.84×10⁻⁷ e**, and the **CYM410 SG–HEM466 FE topology bond** at **2.52705 Å**.
Whole-complex rigid alignment preserved the ligand heavy-atom pose (RMSD
**5.21×10⁻⁸ Å**). cpptraj read the paired topology/restart and its one-frame static
check reported zero problems. These observations do not establish equilibration.

## Compatibility and limits

- Package/CLI version is 1.1.0 on this branch even though its source baseline
  reported 1.3.0. Select this branch/tag explicitly; an ordinary package upgrade
  from a numerically newer installation does not select this maintenance line.
- init now rejects every existing directory. Complete preparation reports
  PREPARED; reviewed resume also supports older partial COMPLETED checkpoints.
- Config/checkpoint/requested run roots must agree. Copied/moved runs require
  explicit metadata and absolute-path reconciliation. Nonzero max_retries is
  rejected; failures must be reviewed before manual resume.
- Applying protonation decisions after solvation or later work has started/cached
  outputs is rejected before writes; changed decisions require a new run.
- AMBER_SH is an exact WSL/POSIX setup filename; only AMBERHOME is a directory.
  Regenerate old pre-MD scripts for the new console/output checks. A selected
  rerun invalidates its previous stage outputs, consistent with the existing -O
  overwrite behavior; preserve results before deliberately rerunning them.
- LEaP attempts clear only their three fixed generated system files before
  execution, so an exit-0 no-op cannot validate stale artifacts. Custom stage IDs
  must be case-insensitively unique and cannot be `system_lig_solv`.
- Artifact JSON writes are atomic per file, not a transaction over every stage
  file. Retries are bounded to approximately 0.5 seconds; a persistently held
  file still fails explicitly and preserves the last committed target. Raw
  unprotected filesystem readers may observe transient Windows/DrvFS errors.
- Local NTFS/DrvFS locking was tested. Network filesystems were not. Native Linux
  backend selection was simulated; actual Linux execution was checked inside WSL.
- Aromatic/Kekulé equivalence and GAFF2 per-atom typing remain reviewed scientific
  input. Numeric conflict checks do not claim complete aromatic validation.
- No QM/ESP/RESP fit, real pre-MD, 20 ns NPT, production MD, dynamics stability,
  or production-readiness claim is part of this release validation. No real
  pmemd/sander execution occurred. Python 3.9–3.11 compatibility remains declared
  but was not re-run in this audit.

## Independent review gates

1. Correctness: **No issues found.**, after F49; independently reviewed `02dd4b8`.
2. Regression with fresh native/WSL suites: **No issues found.**, after F50–F52;
   independently reviewed `b780f63`, including the original long test directory.
3. Consistency/docs/version/CLI: pending.

Publication is gated on three sequential independent `No issues found.` results.
