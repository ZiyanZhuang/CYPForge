<p align="center">
  <img src="assets/cypforge_logo.svg" alt="CYPForge" width="360" />
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-%E2%89%A53.9-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20WSL%20%7C%20Linux-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/version-1.3.0-brightgreen" alt="Version 1.3.0">
</p>

# CYPForge

CYPForge prepares CYP450 protein–heme–ligand systems for Amber molecular dynamics. Feed it a complex PDB and a ligand SDF, and it runs heme/axial-cysteine parameterization, ligand RESP/GAFF2 parameterization, protonation, solvation, ionization, and a 9-stage pre-MD equilibration that finishes with 20 ns of free NPT. Every stage emits a JSON manifest and a hard `PASS` / `WARN` / `FAIL` gate; the workflow stops on `FAIL` and pauses on `WARN` (unless `--auto-accept-warn` is set at init).

You bring Amber/AmberTools and Multiwfn. CYPForge drives them.

---

## Quick start with an AI agent

Use an agent to verify an existing environment and render the bundled benchmark.

### Codex CLI

```powershell
git clone https://github.com/ZiyanZhuang/CYPForge.git
cd CYPForge
codex
```

Then paste:

> Check the configured Python, CYPForge, AmberTools, and Amber environment. Do not install or modify software without approval. Use the supplied 4EJJ structure and ligand parameters, skip QM/ESP/RESP, and execute the benchmark through `core3_render_pre_md`. Do not launch pmemd, sander, equilibration, or production MD.

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
cypforge --version                       # cypforge v1.3.0
python -B -m pytest tests -q             # external-data tests may be skipped
```

`pip install -e .` puts the `cypforge` console script on your `PATH`. Use `cypforge module ...` for individual Core/gate operations; the legacy wrappers remain only for compatibility.

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

On Windows, CYPForge calls `wsl.exe` to run Amber tools. Set `--wsl-user` only when the required Amber environment belongs to a non-default WSL user.

---

## Run a system

```powershell
.\cypforge.cmd init my_run `
  --pdb "<path>\protein_heme_ligand.pdb" `
  --sdf "<path>\ligand.sdf" `
  --heme-state IC6 `
  --ligand-resname LIG

.\cypforge.cmd prep-only my_run          # pauses after Core 2 if protonation is not confirmed
.\cypforge.cmd protonation recommend my_run --ph 7.4
# Review protonation_recommendations.json, then apply only confirmed selectors.
.\cypforge.cmd protonation apply my_run --set <CHAIN>:<CURRENT><RESID>=<TARGET>
.\cypforge.cmd prep-only my_run          # resumes and stops before MD launch
.\cypforge.cmd status my_run
.\cypforge.cmd context my_run > agent_input.json
```

Use `prep-only`, not `resume`, when the endpoint must remain no-MD. `resume`
continues the full workflow and may enter `core3_run_pre_md`.

For the bundled quick test, pass the reviewed charged MOL2 and matching frcmod
as advanced inputs. CYPForge checks the SDF/MOL2 chemistry contract, charge sum,
heavy-atom names, and agreement with the confirmed complex pose before staging
them under the existing Core 2 filenames. It does not run QM, ESP, RESP,
`antechamber`, or `parmchk2` on this path.

```powershell
.\cypforge.cmd init quick_4ejj `
  --pdb "benchmark\4EJJ\4EJJ_CPD1_NCT.pdb" `
  --sdf "benchmark\4EJJ\nicotine.sdf" `
  --heme-state CPDI `
  --ligand-resname NCT `
  --supplied-ligand-mol2 "benchmark\4EJJ\NCT_multiwfn_resp.mol2" `
  --supplied-ligand-frcmod "benchmark\4EJJ\NCT.frcmod"
```

Run `cypforge init --help-advanced` to show chain, residue, charge, QM, force-field, solvent, and executable overrides. Pass `--blank-ligand-chain` (not `--ligand-chain ""`) when the ligand has a blank chain ID.

Review protonation states before Core 3 continues. The selector uses the chain,
current residue name, and residue number from the original prepared PDB:

```powershell
cypforge protonation recommend my_run --ph 7.4
cypforge protonation apply my_run --set <CHAIN>:<CURRENT><RESID>=<TARGET>
```

The recommendation command does not modify the structure. The apply command requires a chain, current residue name, original residue number, and target Amber residue name.

Index user-local manuals and export a redacted run diagnosis when needed:

```powershell
cypforge docs sync amber25.pdf --source amber --document-version 25
cypforge docs query "unknown residue"
cypforge profile set amber_sh=/path/to/amber.sh
cypforge diagnose my_run
```

Profiles accept only tool/runtime keys and are used as defaults by subsequent
`init` commands. Manual files remain local; the SQLite FTS5 index is not part of
the repository or run package.

---

## Workflow

Ten stages, fixed order, enforced by `skills/cypforge/skills_manifest.json` and `src/cypforge_core/orchestrator/models.py`:

1. `environment_check`
2. `core1_prepare_heme_cym` — heme + axial cysteine (CYM)
3. `core2_prepare_ligand_resp_gaff2` — ligand RESP / GAFF2
4. `core3_finalize_protonation`
5. `core3_solvate_ionize` - render LEaP input, run `tleap`, then validate topology, coordinates, charge, and ions
6. `core3_render_pre_md`
7. `core3_run_pre_md` — 9-stage equilibration; stage 09 is 20 ns free NPT
8. `global_audit` - manifest-driven residue, ligand, heme, CYM, ion, charge, and geometry gates
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
- A `tleap` zero exit does not prove correctness. Solvation, pre-MD, and global audit outputs are independently gated by their manifests.
- Raw run folders keep local paths and command lines for reproducibility. Use `cypforge diagnose` before sharing run records because it redacts local paths and secret-like values.

---

## Citations

CYPForge is an orchestration layer that drives well-established upstream tools. If you publish results obtained with it, please cite both the bundled parameter set and the third-party tools that did the actual chemistry.

### Bundled heme parameters

The heme / CYP / iron parameters under `src/cypforge/data/heme_params/` (states `IC6`, `DIOXY`, `CPDI`) come from:

> Shahrokh K, Orendt A, Yost GS, Cheatham TE III. *Quantum mechanically derived AMBER-compatible heme parameters for various states of the cytochrome P450 catalytic cycle.* **J. Comput. Chem.** 2012, 33(2): 119–133. [doi:10.1002/jcc.21922](https://doi.org/10.1002/jcc.21922) · PMID 21997754 · PMCID PMC3242737.

Full provenance: [`src/cypforge/data/heme_params/PROVENANCE.json`](src/cypforge/data/heme_params/PROVENANCE.json).

### Upstream tools

| Tool | Used for | Cite |
| --- | --- | --- |
| **Amber** (pmemd / pmemd.cuda) | MD engine for pre-MD equilibration | Case D.A. *et al.* **Amber 2024**, University of California, San Francisco, 2024. |
| pmemd.cuda (GPU MD) | GPU-accelerated equilibration | Salomon-Ferrer R, Götz A.W, Poole D, Le Grand S, Walker R.C. *Routine microsecond molecular dynamics simulations with AMBER on GPUs. 2. Explicit solvent particle mesh Ewald.* **J. Chem. Theory Comput.** 2013, 9(9): 3878–3888. [doi:10.1021/ct400314y](https://doi.org/10.1021/ct400314y) |
| **AmberTools** — Antechamber | GAFF2 atom typing for the ligand | Wang J, Wang W, Kollman P.A, Case D.A. *Automatic atom type and bond type perception in molecular mechanical calculations.* **J. Mol. Graph. Model.** 2006, 25(2): 247–260. [doi:10.1016/j.jmgm.2005.12.005](https://doi.org/10.1016/j.jmgm.2005.12.005) |
| **AmberTools** — GAFF / GAFF2 | Ligand force field | Wang J, Wolf R.M, Caldwell J.W, Kollman P.A, Case D.A. *Development and testing of a general amber force field.* **J. Comput. Chem.** 2004, 25(9): 1157–1174. [doi:10.1002/jcc.20035](https://doi.org/10.1002/jcc.20035) |
| **PySCF** / **GPU4PySCF** | HF/6-31G* wavefunction for RESP | Sun Q. *et al.* *PySCF: the Python-based simulations of chemistry framework.* **WIREs Comput. Mol. Sci.** 2018, 8(1): e1340. [doi:10.1002/wcms.1340](https://doi.org/10.1002/wcms.1340) · Sun Q. *et al.* *Recent developments in the PySCF program package.* **J. Chem. Phys.** 2020, 153(2): 024109. [doi:10.1063/5.0006074](https://doi.org/10.1063/5.0006074) |
| **Multiwfn** (`Multiwfn_noGUI`) | ESP grid + two-stage RESP fit | Lu T, Chen F. *Multiwfn: A multifunctional wavefunction analyzer.* **J. Comput. Chem.** 2012, 33(5): 580–592. [doi:10.1002/jcc.22885](https://doi.org/10.1002/jcc.22885) · Lu T. *A comprehensive electron wavefunction analysis toolbox for chemists, Multiwfn.* **J. Chem. Phys.** 2024, 161(8): 082503. [doi:10.1063/5.0216272](https://doi.org/10.1063/5.0216272) |
| **RESP** method | Two-stage hyperbolic-restraint charge fit | Bayly C.I, Cieplak P, Cornell W.D, Kollman P.A. *A well-behaved electrostatic potential based method using charge restraints for deriving atomic charges: the RESP model.* **J. Phys. Chem.** 1993, 97(40): 10269–10280. [doi:10.1021/j100142a004](https://doi.org/10.1021/j100142a004) |

### CYPForge itself

A manuscript is in preparation. Until then, cite the repository URL and the released tag (`v1.3.0`).

---

## Documentation

- [`QUICKSTART.md`](QUICKSTART.md) — single-page English walkthrough from clone to first rendered prompt, with agent-driven setup recipes (Claude Code / Codex / Trae).
- [`CYPForge_Agent安装使用说明.md`](CYPForge_Agent安装使用说明.md) — 中文安装与使用说明（init / prep-only / resume、质子化决策 JSON、故障排除）.
- [`benchmark/README.md`](benchmark/README.md) — reproducible agent-driven benchmark (4EJJ / 1Z10 / 1Z11; full / no-outer-shell / no-CYPForge variants).
- [`skills/cypforge/SKILL.md`](skills/cypforge/SKILL.md) — top-level skill contract loaded by agent runners.

---

## License

MIT — see [`LICENSE`](LICENSE).
