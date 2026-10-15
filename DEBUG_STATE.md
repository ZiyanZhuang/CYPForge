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

### F01 / P0: repeated or concurrent init overwrites an existing run

- Reproduction: `python -B -m pytest tests/test_persistence.py -q` initially **3 failed**: second initialization did not raise, both concurrent initializers reported success, CLI returned 0 for an occupied directory.
- Root cause: `WorkflowManager.init_run` used `mkdir(exist_ok=True)` before overwriting both persistent JSON files. All callers (`CYPForgeOrchestrator.init/run_until`, CLI, legacy shim, tests) were checked.
- Fix: exclusive directory creation is the shared ownership boundary; CLI reports an occupied run root with `[ERROR]` and exit 2. Existing run contents remain untouched, including an existing empty directory (choose a new path).
- Green: 3 focused tests passed; complete native regression **100 passed, 6 skipped**, one existing legacy-wrapper deprecation warning. Runtime: existing Conda `codex-dev` Python 3.12.14, numpy 2.5.2, pytest 9.1.1; process-local source `PYTHONPATH`, plugin autoload disabled. No installation.
- Commit: `fix: prevent init from overwriting existing runs` (this entry is included in that commit).

### F02 / P2: retries within one second overwrite prior command/stdout/stderr logs

- Red: frozen-clock public `ModuleRunner.run_step` test initially **1 failed, 1 passed**; both attempts shared the same stdout path and the earlier evidence was overwritten.
- Root cause: log prefix used only second-resolution UTC plus the step name. Checked `run_step` callers in the orchestrator.
- Fix: append a standard-library UUID per attempt; no change to scientific execution or timestamp fields.
- Green: 2 focused tests passed (including a real Python subprocess from a Chinese/spaced run path); full native regression **102 passed, 6 skipped**, one existing warning.
- Commit: `fix: retain separate logs for repeated step attempts`.

### F03 / P1: interrupted writes can truncate persistent JSON

- Red: failed-replacement checkpoint test initially **1 failed**; the existing code directly overwrote the checkpoint rather than using a replacement boundary.
- Root cause: shared `io.write_text/write_json`, workflow config/checkpoints, CLI protonation state and ligand gate, and derived decision files used direct writes. Call sites and the shared `_write_text` alias used by generated stage manifests were inspected.
- Fix: shared text writer uses a same-directory unique temporary file, flush/fsync, close, and `os.replace`; temporary file is cleaned on failure. JSON writers and direct orchestration/CLI state writes reuse it.
- Green: failed replacement preserves the previous checkpoint byte-for-byte and leaves no temporary file; 4 persistence tests passed; full native regression **103 passed, 6 skipped**, one existing warning.
- Limit: file-level atomicity does not serialize two independent workflow writers or make config+manifest a cross-file transaction. Concurrent workflow ownership is checked next.
- Commit: `fix: atomically persist run state and generated manifests`.

### F04 / P1: two controllers can execute the same run concurrently

- Red: two public `run_until` calls overlapped at an external subprocess boundary and both executed environment probes; concurrent-execution test initially failed.
- Root cause: complete JSON snapshots had no workflow ownership boundary. Atomic replacement alone cannot prevent repeated tool launches or lost state updates.
- Fix: run-level nonblocking OS file lock (Windows `msvcrt`, POSIX `fcntl`) covers orchestration execution and CLI protonation mutation. Read-only status/context/diagnose remain available. Lock file is retained to avoid inode races; OS ownership is released even on process death.
- Green: 5 persistence tests passed; full native regression **104 passed, 6 skipped**, one existing warning.
- Follow-up: verify process-death recovery and cross-process contention on both platforms; inspect prep-only endpoint state before final release.
- Commit: `fix: serialize workflow execution and protonation writes`.

### F05 / P1: shareable diagnosis leaks credential variants and path fragments

- Independent audit and public API red test used synthetic credentials only. Initial report exposed `api-key`, `Authorization: Bearer`, and a Windows path suffix after the first space; arbitrary POSIX `/srv` paths were also exposed. Expanded red case covered camel-case keys and quoted secrets containing spaces.
- Root cause: inconsistent key normalization, no authorization handling, whitespace-terminated path patterns, and host-dependent Windows basename parsing.
- Fix: normalized secret-key matching; quoted/unquoted credential and authorization redaction; conservative full-path redaction (including spaced/UNC paths); host-independent basename extraction. Raw run records remain local and unchanged.
- Green: 3 diagnosis tests passed; full native regression **105 passed, 6 skipped**, one existing warning.
- Limit: diagnostic output intentionally removes trailing path-containing context conservatively; this is a focused redaction repair, not a guarantee that arbitrary unknown secret formats can be recognized.
- Commit: `fix: redact credentials and complete paths from diagnoses`.

### F06 / P1: malformed or conflicting gate manifests can pass or crash

- Red: 13 public GateChecker cases initially failed: PASS/success hid child FAIL/WARN, unknown child statuses passed, wrong JSON root/child types crashed, invalid UTF-8 escaped the failed-gate boundary.
- Root cause: top-level status returned before child checks, sub-statuses defaulted to PASS without normalization, and read/summary boundaries assumed valid object shapes.
- Fix: recursively combine declared statuses with FAIL precedence; unknown status, missing child status, wrong shape, or declared empty child list fails closed. Decode BOM-bearing UTF-8 and convert unreadable encodings to FAIL evidence. Summary tolerates malformed values without masking the failure.
- Green: 13 focused cases passed; full native regression **118 passed, 6 skipped**, one existing warning. No chemical thresholds changed.
- Commit: `fix: fail closed on malformed and conflicting gate manifests`.

### F07 / P1: host log decoding misreports completed WSL/Python steps

- Red: real WSL `printf` returned FAIL with `data must be str, not NoneType`; native non-UTF8 subprocess test lost exit code 7 (recorded None), with GBK reader-thread UnicodeDecodeError.
- Root cause: subprocess text decoding inherited the Windows locale; WSL startup diagnostics contain mixed encodings and child programs may emit non-UTF8 bytes. Reader failure caused missing output strings before exit-code persistence.
- Fix: explicit UTF-8 with replacement on all three runner subprocess boundaries (Python script, WSL, Python inline), preserving logs and return code even for undecodable bytes.
- Green: 3 runner tests; full native regression **119 passed, 6 skipped**, one existing warning; real WSL `printf` **PASS, exit 0**, both logs exist. Mixed-encoding warning bytes may display replacement characters; no command success is inferred from log decoding.
- Commit: `fix: preserve subprocess results across output encoding errors`.

### F08 / P1: blank-chain protonation selectors cannot be applied

- Independent audit and real public recommend → selector builder → finalize roundtrip reproduced failure for an original blank chain; true chain A passed (**1 failed, 1 passed** before fix).
- Root cause: display alias `A` was saved as `original_chain`, contradicting the original PDB identity during finalization.
- Fix: save the mapped original chain in the decision; keep the existing selector display and explicit transition rules. No residue-state choice or chemistry changed.
- Green: 3 focused cases passed; full native regression **121 passed, 6 skipped**, one existing warning.
- User explicitly confirmed the bundled 4EJJ changes for no-MD smoke: GLU419→GLH; HIE55/299/386→HID; watchlist unchanged.
- Commit: `fix: retain blank-chain identity in protonation decisions`.

### F09 / P1: supplied-parameter route requires tools it never executes

- Red: normal route remained FAIL as required when `antechamber` was unavailable; the reviewed supplied-MOL2/frcmod route also failed (**1 failed, 1 passed**), contradicting its no-parameter-generation contract. Real 4EJJ smoke reproduced the block after successful Python/tleap/pmemd.cuda/cpptraj probes.
- Root cause: the static default tool-probe list was used regardless of selected Core-2 execution route.
- Fix: for a complete supplied pair only, omit the two unused `antechamber/parmchk2` probes in the per-run environment definition. All required active-route tool checks and all downstream ligand chemistry/identity gates remain. Normal generation still requires all five tools. Environment skill documentation synchronized; no scientific rule or chemical algorithm changed.
- Green: 2 route tests; full native regression **123 passed, 6 skipped**. Real smoke now passes environment and Core 1, then detects a separate missing-ligand input-routing defect in Core 2 (next issue).
- Commit: `fix: probe tools required by the selected ligand route`.

### F10 / P1: Core 2 receives a ligand-free Core-1 host

- Red: real bundled no-QM Core1→Core2 public workflow test failed; Core 1 intentionally drops non-host/non-heme residues, while both Core-2 commands incorrectly consumed that ligand-free file. Real smoke reported `No NCT chain ... atoms found`.
- Root cause: missing orchestration staging between the prepared host and confirmed ligand pose. Simply using the raw PDB would lose Core-1 heme/CYM preparation and confirmed trimming.
- Fix: one audited orchestration staging step reuses existing ligand extraction/PDB writers, preserves all prepared host coordinates, and appends exactly one selected ligand identity from Core 1's effective input. Both Core-2 consumers use this staged file. Source checksums/counts are manifested; protonation keeps the original prepared-host numbering source. New inline-call values are Python literals via `repr`; existing two inline consumers updated accordingly.
- Green: real no-QM workflow test passed; full native regression **124 passed, 6 skipped**. Independent analysis also verified 7581 host + 26 ligand atoms, ligand heavy-pose RMSD 0, and 465 consistent protein-residue mappings. No chemistry algorithm or heme/CYM preparation policy changed.
- Commit: `fix: stage the confirmed ligand with the prepared Core-1 host`.

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
