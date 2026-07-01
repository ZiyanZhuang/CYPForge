# Changelog

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

## 1.1.0

- Initial public release.
