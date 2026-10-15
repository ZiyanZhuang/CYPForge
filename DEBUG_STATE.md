# CYPForge 1.1 persistent debugging state

## Scope and boundaries

- Start: 2026-10-15 17:31 Asia/Shanghai (09:31 UTC); approximate budget: 7 hours.
- Repository: `https://github.com/ZiyanZhuang/CYPForge`; baseline `427afd606144d388d92a684082c29cc514018154`.
- Working branch: `release/1.1`; never merge or push to the default branch, force-push, or overwrite a tag/release.
- Target: `v1.1.0` (use `v1.1.1` only if `v1.1.0` already exists).
- The baseline source reported 1.3.0; package/CLI/docs are now aligned at 1.1.0 for the requested independent maintenance line. This does not claim to supersede 1.3.0.
- No software installation, dependency additions, scientific-rule/chemistry changes, license changes, or long MD.
- Scientific smoke endpoint: `core3_render_pre_md`; never launch the 20 ns free NPT stage.
- Regression seams authorized by the task: public CLI, WorkflowManager/ModuleRunner/GateChecker, manifest outputs, ligand/protonation public module APIs, and local docs/diagnosis APIs. One reproduced defect at a time; red test before fix; focused plus full regression; independent commit per defect.

## Baseline and environment

- Windows default Python: 3.13.15; `python -B -m pytest tests -q` exited 1 (`No module named pytest`). Selected existing codex-dev Python 3.12.14/numpy 2.5.2/pytest 9.1.1. Initial baseline on existing Python 3.14.6: **97 passed, 6 skipped**, one existing legacy-wrapper warning. No installation attempted.
- Native `cypforge --version` was absent from PATH. The source entry point uses process-local `PYTHONPATH`; its version and `cypforge.__version__` now both report **1.1.0**. An unrelated existing WSL installation reports 1.3.0 and was not changed.
- Process variables `AMBER_SH`, `AMBERHOME`, `MULTIWFN_BIN`, `CYPFORGE_RUNS_DIR`: unset.
- WSL available: Ubuntu-24.04, default user `zhuang`; existing Python 3.12.3/numpy 2.5.2/pytest 9.1.1. Amber setup under `/home/zhuang/amber26-local/prefix/amber26-pmemd-cuda129-sm120/amber.sh`; AmberTools prefix `ambertools26-ff19sb-lite` provides tleap/cpptraj V7.6.2. An isolated task-local setup file sources that environment and extends its PATH without modifying installed software.
- Multiwfn, antechamber and parmchk2 are absent; no-QM reviewed supplied parameters exercise the valid route that omits those unused fitting probes. pmemd executable availability was checked, never executed as MD. WSL emits an existing localhost-proxy warning; command exit and saved logs remain inspectable.
- Git remote tags: only `v1.2.0`; `release/1.1` absent remotely at baseline.
- `gh release list` initially reported missing authentication. A later read-only live check succeeded using the existing context, with repository push/admin permission metadata; no login or credential extraction was performed. Authenticated tag/Release GETs for v1.1.0/v1.1.1 all returned 404. Unauthenticated API was rate-limited (403), never treated as an existence check.
- Task-owned run directory outside the repository is writable. Working source has no user modifications. Git push dry-run succeeded; actual branch/tag/Release publication remains gated on reviews.
- Current full regression: **255 passed, 6 skipped** native; **251 passed, 10 skipped** WSL. Both have one existing warning. Six shared skips need absent optional external fixtures; WSL's four additional skips are two native Windows launchers, one native Windows/WSL locking test and the Windows path-length boundary.
- Repair totals: **53 defect records with dedicated repair commits: 1 P0, 41 P1, 11 P2** (52 code defects plus one documentation-contract defect). All three sequential independent review gates have passed; no known P0/P1 remains within the exercised scope.

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

### F11 / P1: command formatting changes valid file names containing repeated spaces

- Red: real Python-script and Python-inline steps could not read an existing `input  中文  with  spaces.pdb` (**2 failed**).
- Root cause: final command-wide whitespace normalization modified already-substituted quoted values. The external parser and file APIs were not responsible.
- Fix: remove that normalization; shell/argv/Python parsers already tolerate template whitespace, while literal path whitespace is preserved.
- Green: 5 runner cases passed; full native regression **126 passed, 6 skipped**, one existing warning.
- Commit: `fix: preserve literal whitespace in command arguments`.

### F12 / P1: prep-only marks partial work COMPLETED and blocks resume

- Red: public simulated-engine tests showed the no-MD boundary falsely marked COMPLETED with a completion time, legacy partial COMPLETED checkpoints could not resume, and rechecking preparation erased a later FAIL (**3 red cases**, no MD executed).
- Root cause: `run_until` reused the full-completion state for bounded execution; `resume` rejected that state even with pending modules. CLI then wrote a separate pause outside workflow ownership.
- Fix: use explicit workflow `PREPARED` for a reached preparation boundary, keep `completed_at` empty, and make it resumable. Protonation boundary pauses within the workflow lock. Legacy partial COMPLETED checkpoints resume safely; later failure/progress is preserved. CLI no longer mutates the returned snapshot outside the lock.
- Green: 5 focused cases; full native regression **129 passed, 6 skipped**, one existing warning. README documents new status and existing 0/2/3 workflow exit semantics.
- Real smoke before this fix: init 0; prep without decision 3; recommend 0; apply 0; prep through actual LEaP/render 0. The bundled prepared PDB already contains target GLH/HID states, so explicitly approved selectors were applied idempotently (`A:GLH419=GLH`, `A:HID55/299/386=HID`). No unapproved renames occurred.
- Commit: `fix: keep preparation checkpoints distinct and resumable`.

### F13 / P1: decision layer allows extension after failed or unknown audit

- Red: 5 direct decision cases initially failed; lowercase `failed`, unknown status, and failed child gates produced ALLOW, while a list root crashed.
- Root cause: the decision function independently compared only uppercase FAIL/WARN and treated every other status as success, bypassing normalized manifest gate semantics.
- Fix: reuse the shared GateChecker status interpretation; malformed/unreadable audits become STOP, and child state aliases are handled consistently. Existing decision names, scientific thresholds, and downstream permissions are unchanged.
- Green: 18 gate/decision tests; full native regression **134 passed, 6 skipped**, one existing warning.
- Commit: `fix: normalize audit gates before equilibration decisions`.

### F14 / P1: final decision/readiness manifests cannot satisfy their gate contract

- Red: six cases failed, one passed incidentally; both producers omitted `status`, making PASS/WARN decisions fail the registered output gate. Readiness failure outputs also lacked their explicit status.
- Root cause: producer/consumer schema mismatch at workflow stages 8/9.
- Fix: emit canonical status matching existing documented decision semantics: STOP→FAIL, human review→WARN, allowed decision→PASS; readiness remains FAIL without required extended equilibration, WARN for review, PASS only for setup-ready state. `production_authorized` remains false in every state.
- Green: 25 gate/decision/readiness cases; full native regression **141 passed, 6 skipped**, one existing warning. No new route to production MD.
- Commit: `fix: publish canonical gate status in decision manifests`.

### F15 / P1: empty scientific artifacts satisfy existence-only checks

- Red: 7 public cases accepted empty solvation topology/coordinates/PDB, rendered pre-MD from an empty topology, or validated empty mdout/restart/trajectory against a success TSV.
- Root cause: file existence was treated as usable output.
- Fix: reuse one small file predicate across solvation validation, pre-MD input readiness, and pre-MD output validation to require a nonempty regular file. Failures name missing/empty artifacts. This is a file-integrity gate, not a replacement for chemistry/topology validation.
- Green: 7 focused cases; full native regression **148 passed, 6 skipped**, one existing warning.
- Commit: `fix: reject empty solvation and pre-MD artifacts`.

### F16 / P1: pre-MD validator trusts a success TSV over interrupted mdout

- Red: a nonempty interrupted mdout plus `normal_end=1` TSV validated success.
- Root cause: normal-end evidence came only from the mutable stage table.
- Fix: independently require the same normal-end patterns already enforced by the generated runner (`Total wall time` / `Final Performance Info`) in the actual mdout, in addition to the table flag and existing fatal/error/output checks.
- Green: 8 artifact cases; full native regression **149 passed, 6 skipped**, one existing warning. No MD executed.
- Commit: `fix: verify pre-MD completion markers from actual output`.

### F17 / P1: empty or inconsistent pre-MD stage lists validate success

- Red: zero expected stages, explicitly empty active subset, duplicate TSV row, and unexpected TSV stage all validated success (**4 failed**).
- Root cause: empty active lists silently fell back to all stages, an empty loop counted as success, and a dictionary collapsed duplicate rows while ignoring extras.
- Fix: require a nonempty valid expected-stage list with unique IDs and an exact ordered one-to-one match with observed TSV stages. Declared empty active subsets fail rather than expanding to other stages.
- Green: 12 artifact cases; full native regression **153 passed, 6 skipped**, one existing warning.
- Commit: `fix: enforce complete and unique pre-MD stage evidence`.

### F18 / P1: custom stage IDs produce broken or executable shell syntax

- Red: four public render cases accepted apostrophe, semicolon, command substitution, or newline in stage IDs (newline failed later with an OS error instead of contract validation).
- Root cause: the filename-character blacklist omitted characters interpreted by the generated Bash/printf statements.
- Fix: validate stage IDs as a leading ASCII alphanumeric followed by ASCII alphanumeric, underscore, dot, or hyphen. All bundled nine IDs remain unchanged; unsafe/custom Unicode IDs now receive a clear ValueError before scripts are generated. Protocol scientific parameters are unchanged.
- Green: 16 artifact cases; full native regression **157 passed, 6 skipped**, one existing warning.
- Commit: `fix: validate stage identifiers before shell generation`.

### F19 / P1: agent context deletes nested decision evidence

- Red: public context export turned output paths, formal charge, and failed residue-check mappings into empty dictionaries.
- Root cause: a top-level field whitelist was applied recursively to keys such as residue numbers and artifact names.
- Fix: select essential fields once at the top, then retain their nested keys while bounding depth and large arrays. No new decision or scientific inference is introduced.
- Green: 4 focused context cases; full native regression **158 passed, 6 skipped**, one existing warning. The regression also confirms unselected bulk is omitted and large arrays are still summarized.
- Commit: `fix: preserve nested manifest evidence in agent context`.

### F20 / P2: supported top-level evidence list crashes protonation recommend

- Red: list-form evidence and three malformed-shape cases raised AttributeError; wrapped-object evidence already passed (**4 failed, 1 passed**).
- Root cause: `.get` was called before distinguishing a list from its optional object wrapper; rows were also assumed to be objects.
- Fix: distinguish the two documented forms, reject invalid root/row shapes with ValueError. Advisory behavior and allowed state transitions are unchanged.
- Green: 7 protonation cases; full native regression **163 passed, 6 skipped**, one existing warning; tests verify recommendations do not modify the original structure.
- Commit: `fix: accept list-form protonation evidence safely`.

### F21 / P2: docs sync ignores corrected source/version metadata

- Red: resyncing unchanged text as AmberTools 25 after Amber 24 returned `unchanged`, and queries retained stale attribution.
- Root cause: the unchanged lookup compared only path/content hash.
- Fix: include source and version in that comparison, reusing the existing transactional reindex path when metadata changes.
- Green: 2 local-knowledge cases; full native regression **164 passed, 6 skipped**, one existing warning; no duplicate search result and a truly identical resync remains unchanged.
- Commit: `fix: refresh docs index when provenance metadata changes`.

### F22 / P2: local docs connections retain Windows file locks until GC

- Red: public indexing/query with real tracked SQLite connections left them open (**1 failed**); rollback self-check already passed.
- Root cause: SQLite's connection context manager handles commit/rollback but does not close the connection. Library users experienced nondeterministic file-lock release (CLI process exit eventually releases it).
- Fix: the existing connection boundary now owns a transaction and deterministic finally-close, including schema/query/index exceptions. Both callers reuse it unchanged.
- Green: 4 local-knowledge cases; full native regression **166 passed, 6 skipped**, one existing warning. Immediate database deletion succeeds and a simulated failed reindex preserves old searchable content/metadata.
- Commit: `fix: close local docs connections after every operation`.

### F23 / P2: CLI operational/input failures have inconsistent exits and tracebacks

- Red: 6 public main-entry cases failed: corrupt config returned missing-run code 1, malformed manifests/root types crashed, invalid SQLite raised a traceback.
- Root cause: command dispatch lacked a common operational-error boundary, and run-state loading assumed object-shaped known-schema data.
- Fix: CLI reports operational/parsing/schema failures as `[ERROR]` on stderr with exit 2; genuinely missing runs retain exit 1. Config/manifest reads tolerate UTF-8 BOM. Manifest loading validates schema, collection shapes, workflow status, and module-record status before state-machine use.
- Green: 6 CLI cases; full native regression **172 passed, 6 skipped**, one existing warning. Data remains unchanged on read failure.
- Commit: `fix: report invalid run state and CLI failures consistently`.

### F24 / P1: Windows split-stage launcher targets a nonexistent full-run script

- Red: `stages_range=1-8` and `9` rendered only split scripts but the launcher still invoked `run_pre_md.sh` (**2 failed, 1 passed**).
- Root cause: the launcher target was hard-coded independently of the rendered script manifest.
- Fix: derive the launcher target from the selected generated script. Existing full-run behavior is retained.
- Green: 19 artifact cases; full native and WSL regressions both **175 passed, 6 skipped**, one existing warning. No scripts were executed as MD.
- Commit: `fix: target the selected pre-MD script from Windows launcher`.

### F25 / P1: generated Bash interpolates engine/reference values as syntax

- Red: an engine value containing `$(printf INJECTED)` executed substitution instead of remaining literal; a quoted reference filename made `bash -n` fail (**2 failed**). Tests ran assignment-only snippets or syntax checks, never an engine.
- Root cause: unescaped dynamic text was inserted inside Bash expansion/argv expressions.
- Fix: standard-library shell quoting for the engine default and input/output/reference restart arguments. User-selected scientific parameters and reference policy are unchanged.
- Green: 2 real Bash boundary cases; full native regression **177 passed, 6 skipped**, one existing warning.
- Commit: `fix: quote dynamic values in generated pre-MD Bash`.

### F26 / P1: Windows launcher returns success when its child script fails

- Red: real PowerShell→WSL execution of a harmless replacement script containing only `exit 7` returned process exit 0.
- Root cause: the generated PowerShell file did not propagate the native WSL exit code.
- Fix: explicitly exit with `$LASTEXITCODE` after WSL completes.
- Green: real launcher case passed; full native regression **178 passed, 6 skipped**, one existing warning. The test never invokes an MD engine; WSL/Linux skips this Windows-specific boundary.
- Commit: `fix: propagate WSL failure from the Windows launcher`.

### F27 / P1: concurrent readers cause transient checkpoint/CLI failures

- Red: native pressure observed 57/600 failed saves and 9/200 failures each for status and diagnosis; WSL on DrvFS observed 4/200 status failures. Six deterministic sharing/replacement-window cases failed before the fix.
- Root cause: Windows handles can temporarily deny replacement/read access; WSL DrvFS can briefly return ENOENT/ENODATA during replacement even though JSON bytes are written atomically.
- Fix: shared JSON reads and atomic replacement retry only these filesystem conflicts, bounded to 50 attempts at 10 ms. Invalid JSON and other errors remain failures; persistent access errors still fail, preserving the last committed file. Dynamic manifest readers avoid an existence-check race.
- Green: 11 persistence cases; full native regression **184 passed, 6 skipped**, one existing warning. Independent pressure rerun follows the separate diagnosis atomic-write fix.
- Commit: `fix: retry transient shared-filesystem checkpoint access`.

### F28 / P1: diagnosis/profile overwrites expose partial JSON

- Red: independent concurrent diagnosis readers observed 8 malformed JSON reads natively and 70 on WSL; two interrupted-commit cases failed for diagnosis/profile because they directly overwrote their targets.
- Root cause: these local-knowledge JSON producers bypassed the shared atomic writer.
- Fix: reuse atomic JSON writing for both outputs and shared JSON reading for profiles. Readers see a complete previous or next report; interrupted replacement preserves the previous file.
- Green: 6 local-knowledge cases; full native regression **186 passed, 6 skipped**, one existing warning. Profile updates remain single-writer operations; no new cross-process merge semantics are introduced.
- Commit: `fix: commit diagnosis and profile JSON atomically`.

### F29 / P2: resume reports ERROR but exits successfully

- Red: public CLI resume of an ERROR checkpoint printed `[ERROR]` yet returned 0; no engine was invoked.
- Root cause: execution-command exit handling recognized STOPPED_ON_FAIL but omitted ERROR.
- Fix: run/prep-only/resume consistently return 2 for either failure status. The rejected checkpoint remains byte-for-byte unchanged.
- Green: 7 CLI cases; full native regression **187 passed, 6 skipped**, one existing warning.
- Commit: `fix: return failure for ERROR workflow checkpoints`.

### F30 / P1: Windows and WSL locks do not exclude each other

- Red: real Windows msvcrt and WSL flock/lockf holders both allowed an opposite-OS writer; the new native→WSL regression failed. Same-OS locking had passed, so that evidence alone was insufficient.
- Root cause: byte-range/advisory locks are not interoperable across the Windows/DrvFS boundary.
- Fix: Windows owns an exclusive no-sharing file handle; Linux retains flock. Windows sharing rules block the opposite-OS open in both directions, and handle/process exit releases ownership without deleting the lock inode.
- Green: 12 persistence cases; full native regression **188 passed, 6 skipped**, one existing warning. Dedicated bidirectional/crash-recovery verification follows.
- Commit: `fix: exclude WSL writers with an exclusive Windows lock handle`.

### F31 / P1: pre-MD reruns can falsely pass using stale engine output

- Red: independent nine-stage fake engine rerun returned 0 without writing files yet reused all 23 old artifacts and validated success. A focused no-op-engine test retained the old first-stage restart.
- Root cause: generated reruns reused fixed output filenames and previous completion markers without clearing them before each attempt.
- Fix: invalidate previous completion/exit markers at run start and remove each selected stage's output/restart/trajectory immediately before its engine invocation. The existing `-O` rerun contract already replaces those outputs; prior-stage inputs and unselected stages are preserved.
- Green: 23 artifact cases; full native regression **189 passed, 6 skipped**, one existing warning. Only shell builtins/fake processes executed; no MD.
- Commit: `fix: invalidate stale pre-MD outputs before rerunning stages`.

### F32 / P1: pre-MD validation trusts substituted artifact paths

- Red: changing a stage's TSV mdout/restart to another valid file, then removing its real artifact, still returned success (2 cases). A declared custom run directory also falsely failed trajectory lookup (1 case).
- Root cause: validation trusted table paths instead of matching declared stage identity, and separately hard-coded the trajectory directory.
- Fix: compare table paths to each expected stage's canonical mdout/restart, validate those expected files, and resolve trajectories through the declared run directory. Identity mismatch is a stage and overall failure.
- Green: 26 artifact cases; full native regression **192 passed, 6 skipped**, one existing warning. No simulation executed.
- Commit: `fix: validate pre-MD artifacts against declared stage identity`.

### F33 / P1: documented fatal Amber messages pass pre-MD validation

- Red: six public validation cases retained normal completion markers but contained Ewald bomb, PME error, abnormal termination, missing restraint reference, cannot find inpcrd, or cannot find prmtop; all incorrectly succeeded.
- Root cause: the fatal-message list omitted these already documented hard-stop signatures.
- Fix: include the documented signatures in the existing diagnostic matcher; no scientific parameter or chemical rule changed.
- Green: 32 artifact cases; full native regression **198 passed, 6 skipped**, one existing warning.
- Commit: `fix: reject documented fatal pre-MD diagnostics`.

### F34 / P1: pre-MD continues after a stage has invalid outputs

- Red: real Bash with owned fake engines returned 0 and ran later stages despite an already recognized FATAL message, empty restart, or empty MD trajectory (3 failed cases).
- Root cause: stage continuation checked only engine exit and normal-end text; independent validation happened after all stages.
- Fix: the generated script uses the same fatal signatures as the validator and requires nonempty restart/trajectory before continuing. First invalid output exits 6 and records a failed run. No force-field/protocol parameter changes.
- Green: 35 artifact cases; full native regression **201 passed, 6 skipped**, one existing warning. Fatal/empty-restart probes stop after stage 1, empty-trajectory after stage 5; all executables are harmless shell fakes.
- Commit: `fix: stop pre-MD at the first invalid stage output`.

### F35 / P2: split stage 9 ignores a customized preceding stage name

- Red: both all/split9 render modes overwrote the correct derived input with the default stage-8 filename (2 failed cases); independent fake 1–8→9 execution failed despite the customized restart existing.
- Root cause: hard-coded overrides mutated shared rendered-stage dictionaries after input dependency resolution.
- Fix: delete the redundant overrides and retain the already derived previous-stage restart for scripts and manifest.
- Green: 37 artifact cases; full native regression **203 passed, 6 skipped**, one existing warning.
- Commit: `fix: preserve derived restart dependencies in split pre-MD scripts`.

### F36 / P1: Windows launcher breaks on apostrophes in paths

- Red: real PowerShell→WSL launch with Chinese/repeated-space/apostrophe output directory and `amber's setup.sh` returned 1 before reaching the harmless `exit 7` script.
- Root cause: setup/directory values were inserted inside unescaped Bash single quotes.
- Fix: encode both values as Bash single-quoted literals, escaping embedded apostrophes. Existing launcher targets and exit propagation remain intact.
- Green: 38 artifact cases; full native regression **204 passed, 6 skipped**, one existing warning. Both launcher cases use only a replacement script containing `exit 7`; no MD.
- Commit: `fix: escape apostrophes in Windows launcher paths`.

### F37 / P1: supplied ligand parameters accept NaN charge

- Red: bundled public supplied-parameter route with one MOL2 charge changed to NaN returned success and serialized NaN as a charge sum; positive/negative infinity controls were already rejected.
- Root cause: `abs(NaN - formal_charge) > tolerance` is false.
- Fix: require a finite charge sum before applying the unchanged charge tolerance. No charge fitting, graph mapping, or chemical rule changed.
- Green: 3 supplied-contract cases; full native regression **207 passed, 6 skipped**, one existing warning.
- Commit: `fix: reject nonfinite supplied ligand charge sums`.

### F38 / P1: supplied MOL2's actual bond table bypasses the SDF graph contract

- Red: zero bonds (including header count 0), changed connectivity, nonexistent endpoints, and duplicate bonds were all accepted (4 failed public cases). Independent real LEaP also generated topology for zero/changed connectivity, so exit 0 cannot repair this omission.
- Root cause: the existing identity-safe mapper checked coordinate-inferred connectivity without comparing the supplied file's explicit BOND records.
- Fix: retain the unchanged mapper, then compare actual MOL2 edges against the mapped SDF edges; reject invalid/duplicate atom IDs, self/duplicate bonds, and unknown endpoints. Manifest now records explicit bond count/connectivity evidence. No geometry/chemical inference algorithm changed.
- Green: 9 supplied-contract cases, including nonsequential atom IDs and bundled ar/Kekulé input; full native regression **213 passed, 6 skipped**, one existing warning. Bond-order/aromatic equivalence is a separate check, not claimed by this connectivity result.
- Commit: `fix: check explicit supplied MOL2 connectivity against the SDF`.

### F39 / P1: fatal engine console output is ignored

- Red: fake engine stdout/stderr each emitted CUDA ERROR/illegal memory access with exit 0 and normal mdout; both scripts continued. Two independent console-log validator cases also falsely passed (4 failed cases).
- Root cause: fatal scanning covered only mdout, although documented hard-stop messages can occur on either process stream.
- Fix: capture per-stage stdout/stderr, replay both to the orchestrator logs, declare their filenames in new manifests, and scan all three outputs with the shared matcher before proceeding. Independent validation reads the declared logs and rejects missing logs. Legacy manifests without declared console logs remain readable.
- Green: 42 artifact cases plus updated renderer fixture; full native regression **217 passed, 6 skipped**, one existing warning. Both console-fatal scripts stop after the first fake stage, exit 6.
- Commit: `fix: gate pre-MD engine stdout and stderr diagnostics`.

### F40 / P1: explicit supplied numeric bond orders can contradict SDF

- Red: two unchanged-coordinate MOL2 cases changed a mapped bond to explicit triple order while SDF declared single; both were accepted.
- Root cause: connectivity matching alone did not compare explicit numerical bond orders.
- Fix: reject contradictions when both sources explicitly give 1/2/3. Preserve the existing ar/Kekulé supplied-parameter representation without adding aromatic perception/conversion or changing mapping. Manifest reports comparison count and explicitly states aromatic equivalence is not re-perceived and still relies on reviewed input.
- Green: 11 supplied-contract cases; full native regression **219 passed, 6 skipped**, one existing warning. Bundled positive retains 21 directly comparable numeric bonds and 6 reviewed ar bonds.
- Commit: `fix: reject explicit supplied numeric bond-order conflicts`.

### F41 / P1: environment setup filenames are guessed incorrectly

- Red: real WSL runner probes failed for explicit/env AMBER_SH pointing to a valid `custom_setup.sh`; CLI init persisted AMBERHOME as a setup filename without adding `/amber.sh` (3 failed cases).
- Root cause: runner treated every path not ending `amber.sh` as a directory; init conflated AMBER_SH (file) with AMBERHOME (directory).
- Fix: reuse the existing shared resolver in both callers. Explicit/AMBER_SH filenames remain exact; only AMBERHOME receives a POSIX `/amber.sh` suffix, including when resolved on Windows.
- Green: 17 focused runner/CLI/resolver cases; full native regression **223 passed, 6 skipped**, one existing warning. Real probes source harmless setup files in apostrophe/Chinese/repeated-space paths; no engine invoked.
- Commit: `fix: resolve Amber setup files consistently without basename guessing`.

### F42 / P1: placeholder-looking filename text is substituted twice

- Red: all three public runner kinds changed an existing filename containing literal `{ligand_resname}` into a different nonexistent path (3 failed cases).
- Root cause: sequential string replacements reprocessed values inserted by earlier replacements.
- Fix: prepare the existing kind-specific replacements, then substitute only the original template once. Literal brace text inside user values remains data.
- Green: 11 runner cases; full native regression **226 passed, 6 skipped**, one existing warning. Real file checks covered Python argv, Python inline, and WSL Bash.
- Commit: `fix: substitute command placeholders in a single pass`.

### F43 / P2: existing incomplete runs return success for missing checkpoints

- Red: CLI status/context/resume with run_config present but run_manifest deleted all returned 0 (3 failed cases), including error-shaped context data.
- Root cause: command configuration loading did not require a valid checkpoint and downstream missing-state messages were treated as ordinary success output.
- Fix: the shared existing-run CLI boundary requires a loadable checkpoint, using the protected reader. Missing/corrupt checkpoints return 2 through the common error boundary; no state is recreated or overwritten. Completely missing runs retain exit 1.
- Green: 11 CLI cases; full native regression **229 passed, 6 skipped**, one existing warning.
- Commit: `fix: reject incomplete existing runs at the CLI boundary`.

### F44 / P1: agent context grants equilibration before the decision gate

- Red: context after a PASS or auto-accepted WARN global audit emitted ALLOW_1_5_NS_FREE_EQUILIBRATION while the equilibration-decision module was still PENDING (2 failed cases).
- Root cause: next-action selection treated a completed audit as authorization and bypassed the following fixed-order decision module.
- Fix: direct the agent to the next remaining module instead; final authorization still requires the existing final decision checks. This enforces the existing decision order without changing scientific policy.
- Green: 3 context cases; full native regression **231 passed, 6 skipped**, one existing warning.
- Commit: `fix: keep context actions behind the equilibration decision gate`.

### F45 / P1: explicit run-root selection silently redirects through stale metadata

- Red: status of a copied run silently displayed the original run when either config or manifest retained another run root (2 failed cases). The same configuration boundary is shared by write commands.
- Root cause: persisted absolute roots were trusted over the explicitly selected directory, with no identity consistency check.
- Fix: reject config/requested-root and manifest/configured-root mismatches before execution. Both directories remain unchanged. Moving/copying a run requires deliberate metadata/input-path reconciliation; no implicit migration or rewrite is introduced.
- Green: 13 CLI cases; full native regression **233 passed, 6 skipped**, one existing warning.
- Commit: `fix: reject inconsistent persisted run-root identities`.

### F46 / P1: context loses or trusts unreadable stage evidence

- Red: array/null/numeric roots and non-UTF-8 stage files crashed context; malformed JSON retained a PASS module and allowed progress; missing evidence disappeared; valid BOM JSON was rejected (7 failed cases).
- Root cause: stage readers assumed object roots, incompletely handled decoding errors, silently skipped absent paths, and did not fail closed when evidence became unreadable.
- Fix: shared protected/BOM-aware JSON reading, object validation, structured per-file errors, and derived FAIL/current-module/STOP actions for unreadable evidence. Other valid stage evidence is retained and persisted run state is not rewritten.
- Green: 10 context cases; full native regression **240 passed, 6 skipped**, one existing warning.
- Commit: `fix: fail context progress closed on unreadable stage evidence`.

### F47 / P2: max-retries advertises an option the controller ignores

- Red: CLI accepted positive/negative retry counts and API execution silently ignored a nonzero setting (3 failed cases). Independent fake first-module failure confirmed no retry occurred.
- Root cause: the option was parsed/persisted but never consumed.
- Fix: explicitly reject nonzero automatic retries at init/execution and correct advanced help. Default 0 remains unchanged; failures require review and explicit resume. No automatic re-execution of hard scientific gates is introduced.
- Green: 19 focused CLI/workflow cases; full native regression **243 passed, 6 skipped**, one existing warning.
- Commit: `fix: reject unsupported automatic retry settings`.

### F48 / P1: native Linux orchestration invokes the Windows WSL launcher

- Red: simulated native Linux (no WSL markers) selected `wsl` instead of Bash for an Amber command.
- Root cause: backend selection distinguished WSL from every other host rather than Windows from POSIX, despite documented POSIX/Linux package support.
- Fix: Windows uses WSL; POSIX uses native Bash. Delete the now-unnecessary WSL-environment detector and allow setup-file probes on any POSIX Bash host.
- Green: 12 runner cases; full native regression **244 passed, 6 skipped**, one existing warning. Native-Linux backend selection is simulated; actual execution is verified on Windows→WSL and WSL/Linux.
- Commit: `fix: run Amber commands directly on native Linux`.

### F49 / P1: custom stage outputs can alias the initial/previous restart

- Formal correctness review found a new boundary in F31: legal stage ID `system_lig_solv` made output restart equal the copied initial input, so cleanup deleted input before a fake engine read it (exit 77). Real DrvFS probes confirmed uppercase alias and `custom`/`CUSTOM` cross-stage aliases.
- Red: three public render tests accepted the reserved initial filename and case-equivalent duplicate IDs (**3 failed**).
- Root cause: stage-name validation ignored the fixed initial-file namespace and case-insensitive filesystem aliasing.
- Fix: reserve `system_lig_solv` irrespective of case and require case-folded stage-ID uniqueness before rendering. No scientific parameter or MD behavior changed for valid distinct IDs.
- Green: 45 artifact cases; full native regression **247 passed, 6 skipped**, one existing warning. The source input remains unchanged. Formal round 1 must re-review this fix before progressing.
- Commit: `fix: prevent pre-MD stage outputs from aliasing restart inputs`.

### F50 / P1: applying protonation after preparation retains stale downstream PASS caches

- During regression review, a root-owned one-atom public CLI probe reapplied a valid GLU→GLH decision after six cached PASS modules. Apply rewrote the final PDB/config, but prep-only returned 0/PREPARED without rebuilding the previously consumed topology/inputs. No external tool or real benchmark state was altered.
- Red: four public apply cases accepted downstream PASS/WARN/RUNNING/SKIPPED and changed files; PENDING/FAIL correction controls already succeeded (**4 failed, 2 passed**).
- Root cause: apply checked writer ownership but not whether later modules had already consumed the inputs it was rewriting.
- Fix: under the run lock, reject apply before any decision/PDB/config write when solvation or later modules have consumed/cached inputs; report exit 2 and require a new run. Initial apply and corrections of PENDING/FAIL downstream states remain supported. No automatic invalidation, regeneration or chemical-policy change is introduced.
- Green: 21 CLI cases; full native regression **253 passed, 6 skipped**, one existing warning. Rejected cases preserve every run file byte-for-byte (apart from the persistent lock inode). Formal round 2 must re-review this fix.
- Commit: `fix: reject protonation edits after downstream input consumption`.

### F51 / P2: unique log names exceed ordinary Windows path limits

- Regression review's original longer pytest base produced a 261-character command-log path and FileNotFoundError before step execution. An independent 172-character log directory reproduced the baseline 231-character name succeeding versus the UUID-extended 264-character name failing; this machine has LongPathsEnabled=0.
- Red: native public run_step at that directory failed before harmless print(42), with no subprocess execution.
- Root cause: F02 appended a full UUID to step/time metadata already present in the command log, pushing otherwise usable paths past MAX_PATH.
- Fix: use the complete UUID alone as the basename. Step/time remain in StepRecord and command-log content; attempts remain unique without changing OS settings. This does not promise arbitrary paths beyond native OS limits.
- Green: 13 runner cases; full native regression **254 passed, 6 skipped**, one existing warning. Two attempts retain separate logs in the original long directory. Formal round 2 must rerun its unchanged longer test base.
- Commit: `fix: keep unique runner log filenames short on Windows`.

### F52 / P1: an exit-0 LEaP rerun can validate previous system files

- Root public-step probe used an owned tleap function that returned 0 and printed a normal zero-error/neutral log but wrote no files. Existing old topology/restart/PDB were left intact and public solvation validation falsely returned success. No actual scientific executable ran.
- Red: a regression of that exact ModuleRunner→validation boundary returned success instead of fail (**1 failed**).
- Root cause: each attempt refreshed leap.log but retained the prior three fixed output files; nonempty-file gates could not distinguish those leftovers.
- Fix: after successful cd to the intended solvation directory and immediately before LEaP, remove only its three fixed generated outputs. The existing validator now rejects a no-output attempt even when LEaP returns 0. Source/parameter/manifest files remain intact; the manual skill command matches the controller. Intentional LEaP reruns already overwrite those outputs.
- Green: 46 artifact cases; full native regression **255 passed, 6 skipped**, one existing warning. Formal round 2 must verify this boundary and full regression again before progressing.
- Commit: `fix: invalidate prior solvation outputs before each LEaP attempt`.

### F53 / P2: execution skills require obsolete artifacts and recovery steps

- Formal consistency review reproduced missing required manifest names, timestamp/exit-code files and an obsolete protonation-recovery instruction in execution_plan.md. Connected Core 1/2/environment/decision skills also promised filenames or generated human reports absent from the real producers; Core 1's manual LEaP example selected nonexistent prepared.pdb.
- Red: task-owned `../debug_artifacts/execution_plan_contract_probe.py` compares the plan against all 13 controller output manifests, real frozen-smoke files/logs and route-specific outputs; old guidance fails with three obsolete/five omitted controller paths and the related missing artifacts. Red logs are preserved in `execution_plan_F53_red.txt` and `execution_plan_F53_red_extended.txt`.
- Root cause: execution documentation had drifted from registered producers and F50/F51. No additional runtime artifact is needed.
- Fix: synchronize canonical manifest/prepared filenames, route-specific evidence, optional human reports, actual UUID/StepRecord logging, reviewed retry semantics and the new-run boundary after changed consumed inputs. Scientific gates and code remain unchanged.
- Green: the same external contract probe passes; full native regression **255 passed, 6 skipped**, one existing warning. Round 3 must re-review the frozen doc-only fix before publication.
- Commit: `docs: align execution skills with actual controller artifacts`.
- Same-round completeness check: an independent public toy `apply --decision-json` returned 0, kept its external decision path in config and did not create the default run-root filename (`../debug_artifacts/review3_external_decision_3addf13d/result.json`). The plan's initially unconditional default-path statement was red against that evidence, then clarified for `--set` versus `--decision-json`; the selected config path is authoritative. Contract probe and full 255/6 native suite were repeated. Follow-up commit: `docs: distinguish external protonation decision paths`.

## Module coverage

All **11 requested module areas** explored and exercised. Real scientific preparation reached **6/10** fixed-order modules; remaining execution/audit/decision behavior used explicit simulations/static fixtures, never real MD.

| Area | Evidence |
| --- | --- |
| Ten-stage order, gates, WARN switch | 50 simulated state/stop/resume cases; 4 unknown/conflicting gate controls; 14 additional public CLI probes |
| Solvation/ionization | Real tleap render/run plus independent manifest gate and static prmtop/rst7/cpptraj checks |
| Pre-MD rendering | Real 4EJJ nine input stages; custom IDs, split ranges, quoting and manifest dependencies |
| Pre-MD run/recovery | 38 owned fake-engine observations; first-failure stop, rerun recovery, stale/empty/missing/substituted artifacts and console logs |
| CLI | Init/help-advanced/status/context/prep-only/resume exit 0/1/2/3; invalid JSON/root/schema, missing checkpoint and unsupported retries |
| Environment/WSL | Real sourced setup probes in special-character paths; missing/wrong env controls; route-aware fitting probes; simulated native Linux backend |
| Ligand contracts | Real 4EJJ supplied path; finite charge, SDF/formal charge, names, pose, actual explicit connectivity and comparable numeric orders |
| Protonation | User-confirmed benchmark decision; original blank-chain selectors, idempotent states, evidence-shape negative cases |
| Diagnosis/context | Redaction, nested chemical evidence, corrupted stage evidence, action gating, concurrent exports |
| SQLite FTS5 | Real local indexing/query, changed provenance, rollback on failure and deterministic close/unlink |
| Concurrency/atomicity | Two-OS save/read pressure, ten-process init races, four lock directions, owned holder crash recovery, interrupted replacement |

## Smoke and robustness evidence

Portable no-MD commands and expected review boundary are reproduced in [RELEASE_1.1.md](RELEASE_1.1.md). Native commands used the existing Python 3.12 executable with process-local PYTHONPATH/PYTEST_DISABLE_PLUGIN_AUTOLOAD; WSL commands used the existing cypforge-gpu virtualenv with this checkout's src path.

- First real smoke `quick_4ejj_env_probe`: init 0; after F09/F10 environment/Core1/Core2 PASS and prep-only 3; recommend 0; user explicitly confirmed the repository's 4EJJ choices; apply 0; preparation/render 0. After F12 status is PREPARED with six PASS and four PENDING.
- Special-path smoke `final_4ejj  中文's {ligand_resname}`: init 0, prep-only 3, recommend 0, confirmed apply 0, prep-only/status/context/diagnose all 0. `../debug_artifacts/final_smoke_20261015_183648/commands.json` and summary.json record argv/exits; logs and generated run files remain outside tracked source. Source HEAD recorded at completion: 66114f4; later CLI-only hardening and release-version metadata are separately tested.
- Final frozen-source smoke `final_4ejj  中文's {ligand_resname} reviewed`: source `b780f6322472387482ec11c0a6f6d30fccbc580f`; all source file SHA256 values checked unchanged after every command. init 0, prep-only 3, recommend 0, confirmed apply 0, prep-only/status/context/diagnose all 0; final PREPARED, six PASS/four PENDING. Exact argv, exits, timestamps and source hashes: `../debug_artifacts/final_smoke_20261015_190255/{commands,summary}.json`. This run includes F49–F52 and supersedes earlier smoke as final release evidence.
- Independent real topology calculation on that final run: 71,698 atoms, 21,833 residues, 21,360 waters, 6 Cl−, net charge about -1.84e-7 e. CYM410 SG–HEM466 FE is an explicit topology bond, distance 2.52705 A (RK 39.00, REQ 2.565). Matched prepared-complex heavy atoms: **3,816**; whole-complex rigid-fit RMSD 5.01e-8 A, 12 ligand heavy atoms under the same transform RMSD 5.21e-8 A. cpptraj reads topology/restart and checks one static frame with zero problems. Pre-MD copied topology/restart hashes equal the solvation sources; nine mdin files are nonempty, three generated shell scripts pass bash -n, and the MD run directory remains empty. LEaP rigid reorientation was accounted for; raw unaligned coordinate distance was not misreported as pose drift. Evidence: `../audit_science_final_reviewed.txt` and `../debug_artifacts/audit_science_final_reviewed/`.
- Both native and WSL: 600 saves + 200 status + 200 diagnosis with **0 protected-API errors** after F27/F28, repeated after F30. Independent real CLI: 24/24 calls exit 0 with 1,800/1,800 concurrent saves successful.
- Each OS's ten-process init race yielded exactly one owner; six repeated init attempts preserved config/checkpoint bytes; five same-OS lock contenders were rejected. Native/native, WSL/WSL, native/WSL and WSL/native all reject simultaneous writers and recover when an owned holder exits inside its lock using os._exit(73), bypassing finally. All child processes were reaped.
- Raw filesystem readers still observed transient permission/DrvFS errors, but no partial JSON after the atomic report fix. The protected API retries are bounded, not an unlimited promise for persistently held handles or network storage.
- Fake-engine controls: nine-stage success; stage-4 exit17 stops and rerun recovers; stale no-op rerun fails; substituted stage path fails; custom run directory and renamed stage8→split9 work; all documented fatal diagnostics in mdout/stdout/stderr and empty outputs stop before later stages. Empty console streams are valid, absent declared console logs fail. All 38 observations matched expectations.
- Evidence handoffs: `../audit_stress.txt`, `../audit_premd_after_e99195a.txt`, `../audit_science_contract.txt`, `../audit_controlflow.txt`, `../audit_release_access.txt`, with task-owned probes/results under `../debug_artifacts/`. These are local artifacts, not installed software or uploaded raw MD/force-field outputs.

## Independent reviews

1. Correctness: **No issues found.** after F49, reviewed `02dd4b831734e90e34555b3a7ac120e3139270cc`. Independent full suite: 247 passed/6 skipped. Report `../review1_correctness_after_F49.txt`, SHA256 `18523c3dcd3abe74489d744546602e30f3adcd6cec265a2b2864d9066d5e03ea`.
2. Regression: **No issues found.** after F50–F52, reviewed `b780f6322472387482ec11c0a6f6d30fccbc580f`. Fresh native 255 passed/6 skipped, fresh WSL 251 passed/10 skipped, using the unchanged original long basetemp. Independent no-op/fresh-output/cd-failure LEaP controls, unchanged protonation files on rejection, unique long-path logs and bidirectional locks passed. Report `../review2_regression_after_F52.txt`, SHA256 `5ee85ed0fe4df042c5d9c19ba9c0acc85888061571dcc43b63f5081a80915b67`; prior reports retain each found issue and failed evidence.
3. Consistency/docs/version/CLI: **No issues found.** after F53 and its external-decision clarification, reviewed `44b8b69950f7a0f035959d609e215422bd62b5d6`. Independent 33 public CLI calls, 13 exact output-manifest contracts, route-specific artifacts, 18 local links and all 37 source/wheel bytes passed. External `--decision-json` was independently applied at the final HEAD without a default-path copy. Report `../review3_consistency_after_F53.txt`, SHA256 `75556385b6e2ccdd8212dabb1cb55a2e16fea1ae0863220f47dab469e3b37a42`.

## Build and publication candidate

- Latest native full suite after the final documentation clarification: **255 passed, 6 skipped**, one existing warning. The WSL reviewed suite is **251 passed, 10 skipped** on the identical 37 Python sources; subsequent commits change documentation only.
- Existing-tools offline build: `python -B -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir ../debug_artifacts/dist_release_final .`; exit 0. No package was installed.
- Wheel `cypforge-1.1.0-py3-none-any.whl`, built at documentation revision `17c535579895cc2700f6fd10b263cbbefa720e83`: 181,529 bytes, SHA256 `3eeb3378f56063a7c7d35638717ada5217ab4ca1f4e8ca362330a9678cb9e119`. All 37 packaged Python files are byte-equal to final source. Isolated unpacked import and CLI report 1.1.0; entry point and bundled CPDI HEM data are present. Evidence: `../debug_artifacts/wheel_validation_release_final.json` and its task-owned verification script. Repository skills/benchmarks/audit documents require the checkout and are not bundled into the wheel.
- Final read-only publication precheck: process-local GH_HOST=github.com selects the existing authenticated context; repository push permission is true, tag and Release v1.1.0 return authenticated 404, remote release/1.1 is absent, and remote main remains the exact baseline `427afd606144d388d92a684082c29cc514018154`. No authentication values were extracted or printed.
- Publication sequence: push release/1.1, create/push a new v1.1.0 tag, create its Release with `--verify-tag --target release/1.1 --latest=false`, then read back tag/branch/asset metadata. Attach the wheel, public validation/checksums and independent reports only. A post-publication documentation-only receipt may advance release/1.1 without moving the immutable tag.

## Open limitations and release state

- Default-runtime pytest is absent; existing tested runtimes were used instead. gh authentication is currently available and must be rechecked at publication.
- Aromatic/Kekulé equivalence and GAFF2 per-atom typing remain reviewed scientific input; only explicit comparable numeric bond conflicts were added. No aromatic algorithm, chemical mapping, force-field or protocol parameter was changed.
- No QM fit, real pre-MD/20 ns NPT/production MD or production-readiness claim is made. Optional external fixtures, network filesystems, and Python 3.9–3.11 were not revalidated. Native Linux backend selection is simulated; real Linux execution was tested inside WSL.
- Atomicity is per file, not a transaction across all stage files. Bounded retries may still reject a persistently held file while preserving its prior committed bytes. Copied/moved runs need explicit metadata/input reconciliation; nonzero automatic retries are rejected. Re-render old pre-MD scripts for new gates; deliberate selected-stage reruns overwrite prior stage outputs as already implied by -O.
- Branch/tag/release publication: **complete**; the immutable tag and public Release were read back successfully. The final receipt below supersedes the candidate's prospective publication checklist.

## Final publication receipt

- GitHub Release: [CYPForge 1.1 / v1.1.0](https://github.com/ZiyanZhuang/CYPForge/releases/tag/v1.1.0), Release ID `413718658`, published **2026-10-15 19:16:25 Asia/Shanghai (11:16:25 UTC)**; draft=false, prerelease=false. Created with `--verify-tag --target release/1.1 --latest=false` after all three independent gates passed.
- `git push origin release/1.1`, new `git tag v1.1.0 ba6e4152eaa874ea089b1f8ddedc247168917bcb`, `git push origin refs/tags/v1.1.0`, and `gh release create ... --notes-file RELEASE_1.1.md` all exited 0. No existing tag/release was overwritten; no PR, merge, default-branch push or force-push was performed.
- Remote readback at **19:16:37 Asia/Shanghai**: `release/1.1` and `v1.1.0` both resolved to `ba6e4152eaa874ea089b1f8ddedc247168917bcb`; `main` remained exactly `427afd606144d388d92a684082c29cc514018154`. Release notes matched this checkout's RELEASE_1.1.md.
- All **7 assets** were independently downloaded with `gh release download` into a new task-owned verification directory and compared byte-for-byte: wheel, validation.json, SHA256SUMS, three review reports and the static science report. All API-reported sizes/digests matched. Machine-readable receipt: `../debug_artifacts/publication_receipt.json`; downloaded files: `../debug_artifacts/release_download_verify/`.
- Final tag code is the same 37 Python source files measured by the frozen `b780f63` real smoke and fresh dual-platform regression. Later pre-tag commits contain documentation only. The additional receipt commit changes only this ledger and advances `release/1.1`; **v1.1.0 remains fixed at ba6e415**.
- Final scope assessment: **11/11 requested module areas** explored; real no-MD preparation completed **6/10 fixed-order modules**, with remaining execution/recovery/decision control covered by owned fakes and static fixtures. **53 issues repaired (1 P0/41 P1/11 P2), all three review gates green, no known unresolved P0/P1 in the exercised scope**. Optional fixtures and scientific/dynamics/platform limits above remain explicit.
- Release verification finished approximately **1 hour 45 minutes** after the recorded 17:31 start, within the approximate seven-hour budget. The task met the user's normal exit condition; the final ledger push is an audit-only completion step. No real QM or MD was run.

## GPU integration follow-up — 2026-10-15 21:36 Asia/Shanghai

The user subsequently authorized low-throughput real local-GPU integration.
The preceding no-MD statements describe the v1.1.0 release validation snapshot.
This follow-up keeps its tag/wheel fixed and uses separate diagnostic copies;
the original prepared run and its workflow checkpoint remain unchanged.

### F54 / P1: normal Amber velocity-limit metadata stops healthy GPU MD

- Hardware: local RTX 5060, 8 GB, GPU UUID `GPU-6b0e551b-9dc4-18d8-167f-9595f3f40550`; existing Amber26 CUDA/sm_120 build, no installation or software configuration changes.
- Real reproduction: `../debug_artifacts/gpu_validation_20261015_214009/` ran copied canonical stages 01–05. All four minimizations and the 100 ps NVT stage exited 0 with normal termination. The unchanged generated shell then exited 6 because its fatal pattern matched the normal header `t = 0.00000, dt = 0.00100, vlimit = -1.00000`. No later stage or 20 ns stage ran. Original preparation hashes remained equal.
- Root cause: shared `_FATAL_PATTERNS` matched every standalone `vlimit`, including printed input metadata. Existing Amber26 source unconditionally prints that parameter; its actual violation message is `vlimit exceeded for step ...`.
- Red: two public-validator positive controls and one generated-Bash positive control failed; actual exceeded/fatal negative controls still passed (**3 failed, 7 passed**). Evidence: `../debug_artifacts/gpu_vlimit_red.txt`.
- Fix: match `vlimit +exceeded` in the existing shared pattern list. Both Bash and Python consumers receive the repair; NaN, SHAKE, CUDA, PME and real velocity-limit failures remain hard stops. No integrator, force-field, chemical identity or protocol parameter changes.
- Green: **51 artifact tests passed; native full 260 passed/6 skipped; WSL full 256 passed/10 skipped**, one existing legacy warning. One simultaneous native test run saw a transient Windows rename access denial inside a test fixture; the exact focused test and unchanged full command passed serially without source/fixture changes. Evidence: `../debug_artifacts/gpu_vlimit_native_green.txt` and saved tool outputs.
- Commit: `fix: distinguish Amber velocity-limit metadata from exceeded errors`.
- Published v1.1.0 still contains its original 53 repairs. The current branch now has **54 defect records (1 P0/42 P1/11 P2)**; F54 is an unreleased post-tag fix. The completed GPU evidence follows.

### Completed bounded GPU validation

- Detailed measured evidence and limits: [GPU_VALIDATION.md](GPU_VALIDATION.md). Existing RTX 5060/Amber26 environment only; immutable published tag/wheel unchanged. No new software, scientific parameters or chemical identities were substituted.
- Frozen source `1f81b9b`: original stages 01–08 completed, four minimizations (19,500 requested cycles), 600 ps at 1 fs, all eight engine and wrapper exits 0; independent public validator success for exactly the selected eight stages. Eight finite/valid restarts, 600 MD frames plus four minimization endpoints; sampled Fe–SG and four Fe–N wide-gate failures 0.
- Separate short diagnostics: 20 ps free NPT; 1 fs and 2 fs NVE 10 ps each; 2 fs 5+5 ps split NVE. All five exit 0, 500 sampled frames, all restarts finite, coordination gate failures 0. Three 2/1/1-step microprobes added 0.008 ps and all exited 0. Successful aggregate 650.008 ps; longest lineage 630 ps. Initial F54 reproduction added a separate 100 ps; total attempts 750.008 ps, not one continuous trajectory or independent replicates.
- Original 08 last 100 ps: 310.1039±0.9876 K, density 1.047099±0.001199 g/cm³. Preserve its 401 ps transient of 333.79 K. Free NPT density changed 1.0476→1.0174 over 20 ps; this is still relaxation, not equilibrium. Min04 reached maxcycles with gradient RMS 0.066369, not drms convergence. MC-barostat PRESS=0 is unavailable, not a physical 0-bar observation.
- NVE short descriptive Etot slopes: 1 fs −0.02588, 2 fs +0.12350 kcal/mol/ps. Staggered restart velocity timing prevents calling their shared serialized arrays an identical synchronous phase point. Same-2-fs split prefix 5 ps is exactly identical; first post-restart frame differs microscopically, but by 630 ps CA/ligand differences are about 0.604/0.936 Å after imaging/fitting. The 4-fs microprobe has matching time/box, raw coordinate RMS difference 6.16e−6 Å, CA-fitted difference 2.54e−9 Å. No strict long-time equivalence or causal attribution to chaos is claimed.
- Canonical job `../debug_artifacts/gpu_validation_20261015_214526/` contains plans, commands, input/output hashes, logs, public validation and all QC CSV/plots/dictionaries. Source preparation's **112 files remain byte-equal**, original checkpoint remains PREPARED with six PASS/four PENDING. No canonical 20 ns stage09, QM, production or readiness transition was run.
- F54 independent gate 1: **No issues found.**, `../debug_artifacts/gpu_F54_review.txt`, SHA256 `9ab94be353b5102f151cfc1a8f77363e551ae63f876546ef7d30fb0cd9946958`.
- F54 independent gate 2, after gate 1: **No issues found.**, fresh native **260 passed/6 skipped**, WSL **256 passed/10 skipped**, each platform's 21 extra public-boundary cases passed; `../debug_artifacts/gpu_F54_regression_review.txt`, SHA256 `3ea33bd0bdc766dff4f573aca020df0ac473afded676acbc396265d27ec5890b`.
- Gate 3 consistency review follows this frozen report; only after it passes may the existing `release/1.1` branch advance. This follow-up creates no new tag or Release and never pushes the default branch.
