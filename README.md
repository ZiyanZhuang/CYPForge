# CYPForge

CYPForge is an Amber molecular-dynamics preprocessing framework for cytochrome P450 (CYP450) protein–heme–ligand complexes. It is **not** a replacement for Amber, AmberTools, or cpptraj; it is a strict orchestration and audit shell built on top of an existing simulation toolchain. The codebase decomposes CYP450 preprocessing into ten reproducible, gated modules executed in a fixed order, every stage emits a JSON manifest, and every stage produces a hard `PASS` / `WARN` / `FAIL` gate. The workflow stops on `FAIL` and pauses on `WARN` unless `--auto-accept-warn` is passed at init.

## What CYPForge is not

- **Not a simulation engine.** It never calls `pmemd.cuda`, `pmemd`, or `sander` for production MD. The shell only prepares audited inputs and (optionally) runs a fixed 9-stage pre-MD equilibration where the final stage 09 is a 20 ns free NPT equilibration.
- **Not a substitute for AmberTools.** `tleap`, `cpptraj`, `antechamber`, and `parmchk2` must be installed and reachable (on Windows, via WSL).
- **Not a one-click tool.** Many inputs require explicit per-system decisions (heme oxidation state, axial cysteine residue ID, protonation decisions, ligand formal charge). The shell refuses to guess.

## Architecture

| Layer | Path | Purpose |
| --- | --- | --- |
| Orchestration | `src/cypforge_core/` | Workflow manager, module runner, gate checker, agent context builder |
| Chemistry | `src/cypforge/` | Heme/CYM structure handling, axial-cys identification, Fe–S geometry |
| CLI wrappers | `scripts/` | One command-line entry point per workflow module |
| Skills | `skills/cypforge/` | Ordered `.md` skill files + `skills_manifest.json` for agent execution |
| Tests | `tests/` | pytest suite for orchestration + heme core |

The workflow has three cores:

- **Core 1** — heme/CYM preparation (`scripts/heme_only.py`, `scripts/heme_mapping_leapin.py`)
- **Core 2** — ligand GAFF2/RESP parameterization (`scripts/ligand_gpu4pyscf_esp.py`, `scripts/ligand_mapping_leapin.py`)
- **Core 3** — protonation finalization → solvation/ionization → pre-MD input rendering → pre-MD run → global audit → equilibration decision → production-readiness check

## Install

CYPForge requires Python ≥ 3.9. WSL with Amber/AmberTools is required to run anything beyond the dry import.

```powershell
git clone https://github.com/ZiyanZhuang/CYPForge.git
cd CYPForge
pip install -e ".[qm,test]"
```

External prerequisites that `pip` cannot install for you:

- **Amber / AmberTools** — must provide `tleap`, `pmemd.cuda`, `cpptraj`, `antechamber`, `parmchk2`. Point `AMBER_SH` (or `AMBERHOME`) at the Amber initialization script.
- **Multiwfn** — only needed for Core 2 RESP fitting. Point `MULTIWFN_BIN` at the `Multiwfn_noGUI` binary.
- **WSL on Windows** — `wsl.exe` is invoked to run Amber tools. Set `--wsl-user <your-wsl-user>` or `$env:WSL_USER` per machine; **there is no default WSL user**.

Environment variables (PowerShell):

```powershell
$env:PYTHONPATH = "<PROJECT_ROOT>\src"
$env:AMBER_SH = "<path-to>/amber.sh"
$env:MULTIWFN_BIN = "<path-to>/Multiwfn_noGUI"
```

## Quick start

```powershell
cd <PROJECT_ROOT>

# Initialize a run (writes run_config.json + run_manifest.json)
.\cypforge.cmd init my_run `
  --pdb "<path>\protein_heme_ligand.pdb" `
  --sdf "<path>\ligand.sdf" `
  --heme-state IC6 --heme-resname HEM `
  --protein-chain A --heme-chain A --axial-cys-resid 442 `
  --ligand-resname NCT --blank-ligand-chain `
  --formal-charge 0 --spin 1 `
  --wsl-user <your-wsl-user> `
  --amber-sh "<path-to>/amber.sh" `
  --multiwfn-bin "<path-to>/Multiwfn_noGUI"

# Safe path: stops before any MD launch
.\cypforge.cmd prep-only my_run

# Inspect state
.\cypforge.cmd status my_run
.\cypforge.cmd context my_run > agent_input.json

# Resume after fixing a FAIL / accepting a WARN
.\cypforge.cmd resume my_run
```

Use `--blank-ligand-chain` (not `--ligand-chain ""`) when the ligand has a blank chain ID. The CLI's `--blank-ligand-chain` flag is the supported way to express this.

## Workflow modules

The agent skill order is fixed and enforced by `skills/cypforge/skills_manifest.json` and `src/cypforge_core/orchestrator/models.py`:

1. `cypforge.environment_check`
2. `cypforge.core1_prepare_heme_cym`
3. `cypforge.core2_prepare_ligand_resp_gaff2`
4. `cypforge.core3_finalize_protonation`
5. `cypforge.core3_solvate_ionize`
6. `cypforge.core3_render_pre_md`
7. `cypforge.core3_run_pre_md`
8. `cypforge.global_audit`
9. `cypforge.equilibration_decision`
10. `cypforge.production_readiness_check`

## Scientific rules

- **SDF is the ligand chemistry source** — graph, bond order, aromaticity, formal charge, and GAFF2 atom typing.
- **PDB is the conformation source** — coordinates only. Do not use PDB bond order as chemistry truth.
- The final Amber topology must retain heme **Fe**, and **CYM**'s SG–Fe topology must be confirmed.
- Ligand atom mapping must be identity-safe; never assume PDB / SDF / MOL2 row order is equivalent.
- A `tleap` zero exit does **not** prove correctness. Every stage is independently gated by its manifest.

## Heme parameter attribution

The heme/CYP/iron parameters under `src/cypforge/data/heme_params/` (states `IC6`, `DIOXY`, `CPDI`) are derived from:

> Shahrokh K, Orendt A, Yost GS, Cheatham TE III. *Quantum mechanically derived AMBER-compatible heme parameters for various states of the cytochrome P450 catalytic cycle.* **J. Comput. Chem.** 2012, 33(2): 119–133. [doi:10.1002/jcc.21922](https://doi.org/10.1002/jcc.21922) · PMID 21997754 · PMCID PMC3242737.

When publishing results that use these parameters, please cite the above paper. The complete provenance ledger, including the partial local consistency check status, lives at `src/cypforge/data/heme_params/PROVENANCE.json`.

## Status and known limitations

- **Windows-first.** Linux native support is best-effort; the orchestrator is tested mainly against WSL invocation paths.
- **Console-script entry point.** `pip install -e .` installs a `cypforge` command (declared in `pyproject.toml` as `cypforge = "cypforge_core.cli:main"`); the legacy `cypforge.cmd` batch wrapper and `python scripts\cypforge_run.py …` still work.
- **`wsl_user` is required** for any WSL step. Pass `--wsl-user` at init; the prior hardcoded default has been removed.
- The `--blank-ligand-chain` rewrite logic in `_format_cmd` (`src/cypforge_core/orchestrator/runner.py`) and the protonation-decision JSON gate may evolve; treat both as load-bearing pieces of the contract between the shell and the chemistry layer.

## Documentation

- [`QUICKSTART.md`](QUICKSTART.md) — **start here.** Single-page English walkthrough from clone to first rendered prompt, with agent-driven setup recipes (Claude Code / Codex / Trae).
- [`README.md`](README.md) — this file (English overview).
- [`CYPForge_Agent安装使用说明.md`](CYPForge_Agent安装使用说明.md) — 中文安装与使用说明（covers init/prep-only/resume, protonation decision JSON, agent workflow, troubleshooting in depth).
- [`benchmark/README.md`](benchmark/README.md) — reproducible agent-driven benchmark (4EJJ / 1Z10 / 1Z11; full / no-outer-shell / no-CYPForge variants).
- [`skills/cypforge/SKILL.md`](skills/cypforge/SKILL.md) — top-level skill contract loaded by agent runners.

## License

MIT — see [`LICENSE`](LICENSE).
