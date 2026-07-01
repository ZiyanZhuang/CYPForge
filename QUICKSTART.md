# CYPForge Quick Start

This is a single-page, runnable walkthrough that takes you from a fresh clone
to a rendered agent prompt for the bundled 4EJJ benchmark case. It is the
fastest way to verify your local CYPForge + Amber + WSL + Multiwfn environment.

Allow more than 20 minutes for the first environment review and walkthrough.
Subsequent no-QM checks are normally faster.

---

## 1. Prerequisites

| Component | Purpose | How to verify |
| --- | --- | --- |
| Python ≥ 3.9 (3.9 / 3.10 / 3.11 / 3.12 tested) | Run the orchestrator and the prompt renderer | `python --version` |
| WSL (Windows hosts) | Run Amber / AmberTools / pmemd.cuda inside a Linux env | `wsl --status` |
| Amber / AmberTools (in WSL) | Provides `tleap`, `pmemd.cuda`, `cpptraj`, `antechamber`, `parmchk2` | `wsl -- bash -lc 'source ~/amber*/amber.sh && which tleap'` |
| Multiwfn (in WSL, *no-GUI* build) | RESP/ESP fitting in Core 2 (optional if you skip ligand parameterization) | `wsl -- bash -lc 'ls ~/Multiwfn*/Multiwfn_noGUI'` |
| `git`, `pip` | Standard | — |

> CYPForge is a **preprocessing and audit shell** — it does not bundle Amber.
> Install Amber yourself; CYPForge only orchestrates the tools you already have.

---

## 2. Clone and install

```powershell
# PowerShell
git clone https://github.com/ZiyanZhuang/CYPForge.git
cd CYPForge
pip install -e ".[test]"
# Add the qm and docs extras only when those functions are required:
# pip install -e ".[qm,docs,test]"
```

After install, the `cypforge` console script is on your `PATH`:

```powershell
cypforge --version
# cypforge v1.3.0  (CYPForge 1.3.0)
```

Run the test suite to confirm the install:

```powershell
$env:PYTHONPATH = "$PWD\src"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -B -m pytest tests -q
# External-data tests may be skipped when their optional fixtures are absent.
```

---

## 3. Point CYPForge at your tools

Set these once per shell (or persist them in your PowerShell profile):

```powershell
$env:PYTHONPATH    = "$PWD\src"
$env:AMBER_SH      = "/home/<your-wsl-user>/amber25/amber.sh"
$env:MULTIWFN_BIN  = "/home/<your-wsl-user>/Multiwfn_*/Multiwfn_noGUI"
# Optional: override the default run-root location
# $env:CYPFORGE_RUNS_DIR = "D:\cypforge_runs"
```

| Variable | Default | When to override |
| --- | --- | --- |
| `AMBER_SH` | none — **required** | always |
| `MULTIWFN_BIN` | none — required for Core 2 RESP | always when fitting ligand charges |
| `CYPFORGE_RUNS_DIR` | `C:\cypforge_runs` (Win) / `~/cypforge_runs` (POSIX) | when you want runs on a non-default drive |
| `PYTHONPATH` | none | only when running scripts without `pip install -e .` |

---

## 4. Configure the benchmark (one-time per machine)

The benchmark prompts are **path-agnostic templates**. You provide your local
paths once in `benchmark/config.json` (gitignored) and the renderer substitutes
them into the prompts.

```powershell
cd benchmark
copy config.example.json config.json
notepad config.json    # or your editor of choice
```

Fill in these six top-level keys:

```jsonc
{
  "project_root":         "E:/path/to/CYPForge",
  "benchmark_input_root": "E:/path/to/CYPForge/benchmark",
  "run_root_base":        "C:/cypforge_agent_runs",
  "wsl_user":             "<your-wsl-user>",
  "amber_sh":             "/home/<your-wsl-user>/amber25/amber.sh",
  "multiwfn_bin":         "/home/<your-wsl-user>/Multiwfn_<ver>/Multiwfn_noGUI"
}
```

> **Agent-assisted environment check.** If you use
> [Claude Code](https://claude.com/claude-code),
> [OpenAI Codex CLI](https://github.com/openai/codex), or
> [Trae](https://www.trae.ai/), ask:
>
> > "Inspect the existing Python, WSL/Linux, Amber/AmberTools, and Multiwfn
> > configuration. Do not install or modify software without approval. Report
> > detected paths, then write `benchmark/config.json` only after I confirm
> > them."
>
> The agent should report missing tools as environment findings, not silently
> install replacements.

The bundled `cases.*` block is already populated with verified residue / atom /
chain / charge / heme-state facts for 4EJJ, 1Z10, and 1Z11. **You do not need
to edit it** unless you change the input PDB/SDF.

---

## 5. Render a benchmark prompt

```powershell
cd ..    # back to project root
python benchmark\render_prompt.py --case 4EJJ --variant full
# → benchmark/build/full_4EJJ.md
```

Three cases × three ablation variants are available:

| Case | Heme state | Ligand | Axial Cys (in PDB) |
| --- | --- | --- | --- |
| `4EJJ` | CPDI (Fe=O, Compound I) | nicotine (NCT) | `CYM 410` (blank chain) |
| `1Z10` | IC6 (resting Fe) | coumarin (COU) | `CYP A 439` |
| `1Z11` | IC6 (resting Fe) | 8-methoxypsoralen (8MO) | `CYP A 439` |

| Variant | What the agent is allowed to use |
| --- | --- |
| `full` | Full CYPForge: outer shell, skills, all module scripts. Stops before `core3_run_pre_md`. |
| `no_outer_shell` | Low-level scripts only; outer shell, orchestrator, and skills are forbidden. The agent must reconstruct the workflow from `scripts/*.py` and `src/`. |
| `no_cypforge` | AmberTools-only ablation. **No CYPForge code or outputs.** A scientifically correct hard-stop is an acceptable outcome. |

Render any combination:

```powershell
python benchmark\render_prompt.py --case 1Z10 --variant no_outer_shell
python benchmark\render_prompt.py --case 1Z11 --variant no_cypforge
```

Each invocation prints the output path on stdout and writes
`benchmark/build/<variant>_<case>.md`.

> The renderer aborts immediately if your `config.json` still has a `<set to
> …>` placeholder. This is intentional — you'll see exactly which key is
> missing.

---

## 6. Hand the rendered prompt to an agent

The rendered file is a **self-contained, machine-specific** prompt. Paste it
into the agent of your choice and watch it execute.

Recommended runners:

| Tool | Why we recommend it | Link |
| --- | --- | --- |
| **Claude Code** | Best Windows/WSL bridge, native PowerShell + Bash tooling, strong long-context behavior for the 10-stage workflow. | <https://claude.com/claude-code> |
| **OpenAI Codex CLI** | Lightweight CLI, good for the `no_cypforge` ablation where the agent has to reason from AmberTools docs only. | <https://github.com/openai/codex> |
| **Trae** | IDE-integrated experience; good if you want to step through manifest decisions interactively. | <https://www.trae.ai/> |

Common usage pattern (any of the three):

```text
1. Open the agent in the cloned CYPForge directory.
2. Paste the contents of benchmark/build/full_4EJJ.md as the first message.
3. Let the agent execute. Authorize WSL invocations when prompted.
4. The agent will write everything under
   C:\cypforge_agent_runs\full_4EJJ\
5. Read system_chemistry_intake.md and the per-stage manifests for the audit
   trail.
```

The prompts already encode the no-MD endpoint, the timing/ledger discipline,
hard-gate rules, and the per-case scientific facts the agent must verify. You
should not need to add anything.

---

## 7. Letting an agent set up CYPForge end-to-end

The prompts below assume that the environment has already been configured.

**Prompt A — environment verification and config**

> "I just cloned CYPForge at `<absolute-path>`. Please:
> 1. Inspect my existing Python, WSL/Linux, Amber/AmberTools, and Multiwfn paths.
> 2. Do not install or modify software without approval.
> 3. Run the local test suite and report pass/skip/fail.
> 4. After I confirm the detected paths, copy `benchmark/config.example.json` to `benchmark/config.json` and
>    fill in `project_root`, `benchmark_input_root`, `run_root_base`,
>    `wsl_user`, `amber_sh`, `multiwfn_bin` with the detected values.
> 5. Render the requested full or no-outer-shell prompt. Do not run MD."

**Prompt B — run the bundled benchmark**

> "Render `benchmark/build/full_4EJJ.md` and execute it from start to the
> no-MD endpoint. Do not launch pmemd / sander / production MD. Stop at
> `core3_render_pre_md` and summarize the generated manifests."

The first environment review may exceed 20 minutes. Repeated runs can reuse
the confirmed profile and run records.

---

## 8. Common gotchas (learned during local config testing)

1. **Non-ASCII paths.** CYPForge tolerates Chinese (and other non-ASCII)
   characters in the project root path. But avoid piped-Python one-liners on
   native Windows tools — they can mangle Unicode. Use real `.py` files
   instead.
2. **Multiwfn versioning.** The version-suffixed directory (e.g.
   `Multiwfn_2026.2.2_bin_Linux_noGUI`) is **inside** `~/Multiwfn/`, not
   directly in `$HOME`. If `which Multiwfn_noGUI` fails, grep `~/.bashrc` for
   the `Multiwfnpath` export.
3. **Blank ligand chain.** When the PDB ligand has no chain ID, pass
   `--blank-ligand-chain` to `cypforge init`, **not** `--ligand-chain ""`.
   The empty string is interpreted as the literal chain character `" "` by
   some shells.
4. **Heme-state cross-check.** If you declare `--heme-state IC6` but the PDB
   contains an axial oxo / dioxygen, `detect_heme_state` will emit a warning
   instead of silently accepting your declaration. Read the warning before
   continuing — it usually means the input is a CPDI/DIOXY intermediate.
5. **The benchmark PDBs are *not* raw RCSB X-ray files.** They are
   CYPForge-prepared intermediates committed for reproducibility — the axial
   Cys is already renamed (`CYM` for 4EJJ, `CYP` for 1Z10/1Z11). The
   `no_cypforge` ablation prompt makes this explicit so an AmberTools-only
   agent knows what to expect. See `benchmark/README.md` §"PDB preprocessing
   status".

---

## 9. Where to go from here

- **Read** [`README.md`](README.md) for the architecture overview and the
  scientific rules CYPForge enforces.
- **Read** [`CYPForge_Agent安装使用说明.md`](CYPForge_Agent安装使用说明.md)
  for the detailed Chinese usage manual (init / prep-only / resume,
  protonation decision JSON schema, troubleshooting in depth).
- **Read** [`skills/cypforge/SKILL.md`](skills/cypforge/SKILL.md) and
  [`skills/cypforge/skills_manifest.json`](skills/cypforge/skills_manifest.json)
  for the agent contract — useful if you write your own runner.
- **Cite** Shahrokh K. *et al.*, *J. Comput. Chem.* 2012, 33(2): 119–133
  ([doi:10.1002/jcc.21922](https://doi.org/10.1002/jcc.21922)) when
  publishing results that use the bundled heme parameters.
