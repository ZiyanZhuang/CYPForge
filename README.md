<p align="center">
  <img src="assets/cypforge_logo.svg" alt="CYPForge" width="360" />
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-%E2%89%A53.9-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20WSL%20%7C%20Linux-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/version-1.1.0-brightgreen" alt="Version 1.1.0">
</p>

# CYPForge

CYPForge prepares CYP450 protein–heme–ligand systems for Amber molecular dynamics. Feed it a complex PDB and a ligand SDF, and it runs heme/axial-cysteine parameterization, ligand RESP/GAFF2 parameterization, protonation, solvation, ionization, and a 9-stage pre-MD equilibration that finishes with 20 ns of free NPT. Every stage emits a JSON manifest and a hard `PASS` / `WARN` / `FAIL` gate; the workflow stops on `FAIL` and pauses on `WARN` (unless `--auto-accept-warn` is set at init).

You bring Amber/AmberTools and Multiwfn. CYPForge drives them.

---

## Quick start with an AI agent

The fastest path: hand the work to Codex CLI or Claude Code and let it install, configure, and render the bundled benchmark.

### Codex CLI

```powershell
git clone https://github.com/ZiyanZhuang/CYPForge.git
cd CYPForge
codex
```

Then paste:

> Install CYPForge with `pip install -e ".[qm,test]"`, detect my WSL username and the paths to `amber.sh` and `Multiwfn_noGUI`, write `benchmark/config.json` with those values, render `benchmark/build/full_4EJJ.md`, and execute that prompt up to `core3_render_pre_md`. Do not launch pmemd, sander, or any production MD.

### Claude Code

```powershell
git clone https://github.com/ZiyanZhuang/CYPForge.git
cd CYPForge
claude
```

Same prompt as above. Claude Code's PowerShell + WSL bridge is the smoothest path on Windows.

Ready-to-paste prompts (install / config / benchmark run) live in [`QUICKSTART.md`](QUICKSTART.md) §7.

---

## Manual setup

Requirements: Python ≥ 3.9, WSL with Amber/AmberTools on Windows, Multiwfn (no-GUI build) for Core 2 RESP.

```powershell
git clone https://github.com/ZiyanZhuang/CYPForge.git
cd CYPForge
pip install -e ".[qm,test]"

# sanity check
cypforge --version                       # cypforge v1.1.0
python -B -m pytest tests -q             # 65 passed, 6 skipped is normal
```

`pip install -e .` puts the `cypforge` console script on your `PATH`. The legacy `cypforge.cmd` wrapper and `python scripts/cypforge_run.py …` still work.

---

## Configuration

Set once per shell (or persist in your PowerShell profile / `.bashrc`):

```powershell
$env:AMBER_SH      = "/home/<wsl-user>/amber25/amber.sh"
$env:MULTIWFN_BIN  = "/home/<wsl-user>/Multiwfn/Multiwfn_noGUI"
# optional: override default run-root location
# $env:CYPFORGE_RUNS_DIR = "D:\cypforge_runs"
```

| Variable | Default | When required |
| --- | --- | --- |
| `AMBER_SH` (or `AMBERHOME`) | none | always |
| `MULTIWFN_BIN` | none | when running Core 2 RESP |
| `CYPFORGE_RUNS_DIR` | `C:\cypforge_runs` (Win) / `~/cypforge_runs` (POSIX) | only to override the default |
| `PYTHONPATH` | none | only when running scripts without `pip install -e .` |

On Windows, CYPForge calls `wsl.exe` to run Amber tools. `--wsl-user` (or `$env:WSL_USER`) is required — there is no default WSL user.

---

## Run a system

```powershell
.\cypforge.cmd init my_run `
  --pdb "<path>\protein_heme_ligand.pdb" `
  --sdf "<path>\ligand.sdf" `
  --heme-state IC6 --heme-resname HEM `
  --protein-chain A --heme-chain A --axial-cys-resid 442 `
  --ligand-resname NCT --blank-ligand-chain `
  --formal-charge 0 --spin 1 `
  --wsl-user <your-wsl-user> `
  --amber-sh "/path/to/amber.sh" `
  --multiwfn-bin "/path/to/Multiwfn_noGUI"

.\cypforge.cmd prep-only my_run          # stops before MD launch
.\cypforge.cmd status my_run
.\cypforge.cmd context my_run > agent_input.json
.\cypforge.cmd resume my_run             # after fixing a FAIL or accepting a WARN
```

Pass `--blank-ligand-chain` (not `--ligand-chain ""`) when the ligand has a blank chain ID.

---

## Workflow

Ten stages, fixed order, enforced by `skills/cypforge/skills_manifest.json` and `src/cypforge_core/orchestrator/models.py`:

1. `environment_check`
2. `core1_prepare_heme_cym` — heme + axial cysteine (CYM)
3. `core2_prepare_ligand_resp_gaff2` — ligand RESP / GAFF2
4. `core3_finalize_protonation`
5. `core3_solvate_ionize`
6. `core3_render_pre_md`
7. `core3_run_pre_md` — 9-stage equilibration; stage 09 is 20 ns free NPT
8. `global_audit`
9. `equilibration_decision`
10. `production_readiness_check`

| Layer | Path | Purpose |
| --- | --- | --- |
| Orchestration | `src/cypforge_core/` | Workflow manager, module runner, gate checker, agent context builder |
| Chemistry | `src/cypforge/` | Heme/CYM structure handling, axial-Cys identification, Fe–S geometry |
| CLI wrappers | `scripts/` | One command-line entry point per workflow module |
| Skills | `skills/cypforge/` | Ordered `.md` skill files + `skills_manifest.json` for agent execution |
| Tests | `tests/` | pytest suite |

---

## Scientific rules

- **SDF is the ligand chemistry source** — graph, bond order, aromaticity, formal charge, GAFF2 atom typing.
- **PDB is the conformation source** — coordinates only. PDB bond order is not chemistry truth.
- The final Amber topology must retain heme **Fe** and the **CYM** SG–Fe topology.
- Ligand atom mapping must be identity-safe; never assume PDB / SDF / MOL2 row order is equivalent.
- A `tleap` zero exit does not prove correctness. Every stage is independently gated by its manifest.

---

## Heme parameter attribution

The heme / CYP / iron parameters under `src/cypforge/data/heme_params/` (states `IC6`, `DIOXY`, `CPDI`) come from:

> Shahrokh K, Orendt A, Yost GS, Cheatham TE III. *Quantum mechanically derived AMBER-compatible heme parameters for various states of the cytochrome P450 catalytic cycle.* **J. Comput. Chem.** 2012, 33(2): 119–133. [doi:10.1002/jcc.21922](https://doi.org/10.1002/jcc.21922) · PMID 21997754 · PMCID PMC3242737.

Please cite this paper when publishing results that use these parameters. Full provenance: `src/cypforge/data/heme_params/PROVENANCE.json`.

---

## Documentation

- [`QUICKSTART.md`](QUICKSTART.md) — single-page English walkthrough from clone to first rendered prompt, with agent-driven setup recipes (Claude Code / Codex / Trae).
- [`CYPForge_Agent安装使用说明.md`](CYPForge_Agent安装使用说明.md) — 中文安装与使用说明（init / prep-only / resume、质子化决策 JSON、故障排除）.
- [`benchmark/README.md`](benchmark/README.md) — reproducible agent-driven benchmark (4EJJ / 1Z10 / 1Z11; full / no-outer-shell / no-CYPForge variants).
- [`skills/cypforge/SKILL.md`](skills/cypforge/SKILL.md) — top-level skill contract loaded by agent runners.

---

## License

MIT — see [`LICENSE`](LICENSE).
