# CYPForge

CYP450 enzyme Amber MD preprocessing framework — an orchestration and audit layer, not a simulation package.

## Architecture

- `src/cypforge_core/` — 13 core orchestration modules (public API)
- `src/cypforge/` — low-level heme/Cys structure handling
- `scripts/` — CLI wrappers (one per core module)
- `skills/cypforge/` — 10 skill `.md` files + `skills_manifest.json` for agent workflow
- `tests/` — pytest test suite
- `docs/` — user manual and technical reports (Chinese)

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

# Core 1: Prepare heme complex
python scripts/heme_only.py --heme-state IC6 --output-dir <dir> <pdb>

# Core 2: Parameterize ligand (requires AMBER_SH and MULTIWFN_BIN)
python scripts/ligand_gpu4pyscf_esp.py --sdf <sdf> --complex-pdb <pdb> ...

# Core 3: Pre-MD equilibration (9 stages, stage 09 = 20ns free NPT)
python scripts/complex_pre_md_equilibration.py --solvation-manifest-json <json> --output-dir <dir>
```

## Skills Agent Workflow

The ordered skill modules in `skills/cypforge/skills_manifest.json`:
`environment_check` → `core1_prepare_heme_cym` → `core2_prepare_ligand_resp_gaff2` → `core3_finalize_protonation` → `core3_solvate_ionize` → `core3_render_pre_md` → `core3_run_pre_md` → `global_audit` → `equilibration_decision` → `production_readiness_check`

## Key Rules

- SDF = ligand chemistry source (graph, bond order, GAFF2 typing)
- PDB = conformation source (coordinates only)
- Stage 09 is now 20ns free NPT equilibration (not a 100ps "smoke test")
- Hard gate FAIL stops the entire workflow
- This shell never runs production MD — it only prepares audited inputs

## Common Issues

- **ImportError**: Ensure `src/` is in PYTHONPATH
- **"Amber environment not configured"**: Set `AMBER_SH` or `AMBERHOME`
- **"Multiwfn path not configured"**: Set `MULTIWFN_BIN`
- **Tests**: `python -B -m pytest tests/test_heme_core.py -v`
