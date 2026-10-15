# Changelog

## 1.1.0 — independent maintenance release (2026-10-15)

This `release/1.1` line is based on revision `427afd6`, whose package version was
1.3.0. It is an explicitly separate maintenance line, not a replacement of the
default branch. The older 1.1.0 source-history entry below is retained; no remote
1.1.0 tag or GitHub Release existed when this release was prepared.

- Prevent repeated/concurrent initialization from overwriting runs; persist JSON
  atomically, retry transient Windows/DrvFS conflicts, and exclude concurrent
  Windows/WSL writers with automatic lock release on process exit.
- Fail unknown/conflicting/invalid gate data closed; preserve nested context
  evidence and block progress on unreadable stage manifests or pending decisions.
- Repair supplied-parameter environment routing and Core 1→2 ligand staging;
  retain identity-safe mapping and the original PDB pose without QM/RESP.
- Correct original-chain protonation selectors and PREPARED/PAUSED/resume states.
- Reject changed protonation decisions after downstream input consumption;
  require a new run instead of silently retaining stale topology/input caches.
- Reject nonfinite charges, invalid explicit MOL2 connectivity and directly
  conflicting numeric bond orders; retain reviewed aromatic representations.
- Harden pre-MD artifacts, exact stage coverage, stale-output invalidation,
  fatal stdout/stderr handling, first-bad-stage stop, split restart dependencies,
  and Windows launcher target/quoting/exit propagation. No MD ran for this release.
- Prevent case-equivalent stage names from aliasing initial/previous restarts,
  clear stale LEaP system outputs per attempt, and keep unique log basenames short
  enough for the measured Windows path boundary without changing OS settings.
- Make CLI errors/exits consistent, reject incomplete or mismatched run roots
  and unsupported nonzero retry counts, and preserve special-character paths.
- Repair redaction, local docs provenance/transaction cleanup, and diagnosis/profile
  atomic writes. Native Linux uses Bash directly.
- Align execution-skill manifests, prepared filenames, route-specific artifacts,
  UUID logs, optional human reports and recovery guidance with actual producers.
- Validate real 4EJJ preparation with configured AmberTools through input rendering,
  plus static topology/coordinate/CYM–Fe checks and owned fake-engine stress tests.
  See [RELEASE_1.1.md](RELEASE_1.1.md) and [DEBUG_STATE.md](DEBUG_STATE.md) for
  commands, per-defect red/green evidence, reviews, compatibility, and limits.

## 1.3.0

- Added the `cypforge module ...` interface for standard Core/gate execution, covering Core 1 heme preparation/LEaP, Core 2 ligand preparation/LEaP, Core 3 protonation, solvation, pre-MD rendering/validation, and global audit operations.
- Updated Outer Shell command templates so reproducibility documentation can use the installed `cypforge` entry point instead of direct low-level script invocation.
- Kept legacy wrappers as compatibility shims while making `cypforge` the documented user-facing entry point.

## 1.2.0

- Fixed the Core 3 execution chain so solvation now renders LEaP input, runs `tleap`, and validates the generated topology/coordinates before pre-MD rendering.
- Fixed `core3_run_pre_md` so the generated Amber stages are followed by `validate_complex_pre_md_run.py`, producing the manifest expected by the global audit.
- Hardened pre-MD execution: stage scripts now stop when normal Amber termination is missing, and validation ignores benign uses of the word `error` while still catching fatal MD failures.
- Removed 4EJJ/NCT-specific assumptions from the generic global audit path; ligand, heme, CYM, ion, and charge checks are now derived from run manifests.
- Fixed command quoting and strict boolean parsing for paths, trim ranges, and persisted run configuration values.
- Reduced the default `init` example to run name, PDB, SDF, and heme state while retaining all existing advanced options.
- Added `cypforge init --help-advanced` without changing the established `init`, `prep-only`, `resume`, and `status` workflow.
- Added a reviewed MOL2/frcmod Core 2 route that skips QM/ESP/RESP only after chemistry, charge, atom-name, and confirmed-pose checks pass.
- Added advisory protonation recommendations and user-confirmed residue-state selectors based on original PDB residue identities.
- Added local SQLite FTS5 manual indexing, user-approved tool profiles, and redacted run diagnosis export.
- Added a no-MD pause before protonation review and retained `prep-only` as the no-MD continuation command.
- Added canonical Core 2 gate output so pre-RESP warnings remain visible to the outer-shell gate.
- Added bundled 4EJJ reviewed ligand parameters and regression coverage for the no-QM route.

## 1.1.0 — historical source-history entry

- Initial public release.
