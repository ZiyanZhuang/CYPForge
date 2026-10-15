# CYPForge 1.1 persistent debugging state

## Scope and boundaries

- Start: 2026-10-15 17:31 Asia/Shanghai (09:31 UTC); approximate budget: 7 hours.
- Repository: `https://github.com/ZiyanZhuang/CYPForge`; baseline `427afd606144d388d92a684082c29cc514018154`.
- Working branch: `release/1.1`; never merge or push to the default branch, force-push, or overwrite a tag/release.
- Target: `v1.1.0` (use `v1.1.1` only if `v1.1.0` already exists).
- Current source reports 1.3.0; the requested 1.1 line is an independent maintenance release, not a claim to supersede 1.3.0.
- No software installation, dependency additions, scientific-rule/chemistry changes, license changes, or long MD.
- Scientific smoke endpoint: `core3_render_pre_md`; never launch the 20 ns free NPT stage.
- Regression seams authorized by the task: public CLI, WorkflowManager/ModuleRunner/GateChecker, manifest outputs, ligand/protonation public module APIs, and local docs/diagnosis APIs. One reproduced defect at a time; red test before fix; focused plus full regression; independent commit per defect.

## Baseline and environment (in progress)

- Windows default Python: 3.13.15; `python -B -m pytest tests -q` exits 1 (`No module named pytest`). Existing alternative runtimes are being checked; no installation attempted.
- `cypforge --version`: command absent from PATH. Source entry point will be used with process-local `PYTHONPATH`.
- Process variables `AMBER_SH`, `AMBERHOME`, `MULTIWFN_BIN`, `CYPFORGE_RUNS_DIR`: unset.
- WSL available: Ubuntu-24.04, default user `zhuang`; found Amber setup under `/home/zhuang/amber26-local/prefix/amber26-pmemd-cuda129-sm120/amber.sh`; tools not yet verified after sourcing.
- Git remote tags: only `v1.2.0`; `release/1.1` absent remotely at baseline.
- `gh release list`: blocked by missing gh authentication. Credential-helper capability will be checked without printing credentials.
- Native run-directory writability and complete pytest baseline: pending.

## Findings and fixes

None accepted yet. Each entry will record priority, red/green evidence, root cause, changed scope, full regression, and commit.

## Module coverage

Pending: ten-stage ordering/gates; solvation; pre-MD rendering; pre-MD run/recovery (simulated engine only); CLI; environment/WSL quoting; ligand supplied-parameter contract; protonation selectors; diagnosis/context; SQLite FTS5; concurrency/atomicity.

## Smoke and robustness evidence

Pending. Local raw logs and run artifacts will remain outside the tracked source tree; this file records portable commands and measured summaries.

## Independent reviews

1. Correctness: pending.
2. Regression, including full pytest: pending.
3. Consistency/docs/version/CLI: pending.

## Open limitations and release state

- Missing default-runtime pytest and gh session are environment findings, not yet final blockers.
- No scientific or production-readiness claim is made by unit tests or no-MD smoke.
- Branch/tag/release publication: pending.
