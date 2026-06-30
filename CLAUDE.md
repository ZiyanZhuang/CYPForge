# CYPForge

CYP450 enzyme Amber MD preprocessing framework — an orchestration and audit layer, not a simulation package.

## Architecture

- `src/cypforge_core/` — core orchestration and audit modules
- `src/cypforge/` — low-level heme/Cys structure handling
- `scripts/` — CLI wrappers (one per core module)
- `skills/cypforge/` — 10 skill `.md` files + `skills_manifest.json` for agent workflow
- `tests/` — pytest test suite

## Workflow (3 Cores)

1. **Core 1** — Heme/CYM preparation: `scripts/heme_only.py`, `scripts/heme_mapping_leapin.py`
2. **Core 2** — Ligand GAFF2/RESP parameterization: `scripts/ligand_gpu4pyscf_esp.py`, `scripts/ligand_mapping_leapin.py`, `scripts/ligand_pose_parameterize.py`
3. **Core 3** — Protonation → solvation → pre-MD (20ns free equilibration) → audit → decision

## Environment

These are **required** (no hardcoded fallbacks):

```powershell
$env:PYTHONPATH = "<project_root>\src"
$env:AMBER_SH = "/path/to/amber.sh"        # or set AMBERHOME
$env:MULTIWFN_BIN = "/path/to/Multiwfn_noGUI"  # only needed for Core 2 RESP
```

WSL is used to run Amber/pmemd.cuda/cpptraj on Windows. The `_win_to_wsl()` function converts Windows paths to `/mnt/<drive>/...` format.

## Quick Start

```powershell
cd "<project_root>"
$env:PYTHONPATH = "<project_root>\src"

cypforge init <run_name> --pdb <complex.pdb> --sdf <ligand.sdf> --heme-state IC6
cypforge prep-only <run_name>
# Review and apply protonation decisions, then run prep-only again.
```

## Skills Agent Workflow

The ordered skill modules in `skills/cypforge/skills_manifest.json`:
`environment_check` → `core1_prepare_heme_cym` → `core2_prepare_ligand_resp_gaff2` → `core3_finalize_protonation` → `core3_solvate_ionize` → `core3_render_pre_md` → `core3_run_pre_md` → `global_audit` → `equilibration_decision` → `production_readiness_check`

## Key Rules

- SDF = ligand chemistry source (graph, bond order, GAFF2 typing)
- PDB = conformation source (coordinates only)
- Supplied MOL2/frcmod inputs skip QM only after charge, chemistry, atom-name, and complex-pose checks pass
- `prep-only` is the no-MD continuation command; `resume` may enter `core3_run_pre_md`
- Stage 09 is now 20ns free NPT equilibration (not a 100ps "smoke test")
- Hard gate FAIL stops the entire workflow
- This shell never runs production MD — it only prepares audited inputs

## Common Issues

- **ImportError**: Ensure `src/` is in PYTHONPATH
- **"Amber environment not configured"**: Set `AMBER_SH` or `AMBERHOME`
- **"Multiwfn path not configured"**: Set `MULTIWFN_BIN`
- **Tests**: `python -B -m pytest tests/test_heme_core.py -v`
