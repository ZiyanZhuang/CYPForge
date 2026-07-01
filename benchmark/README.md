# CYPForge Agent Benchmark

This directory holds the reproducible agent-driven benchmark for CYPForge. It
contains three crystal-structure inputs (4EJJ, 1Z10, 1Z11), three ablation
prompt templates (full, no-outer-shell, no-CYPForge), and a small render
script that converts a template + per-machine config into a ready-to-send
prompt under `benchmark/build/`.

The committed benchmark structures, SDF files, reviewed 4EJJ MOL2/frcmod, and
checksum file are public reproducibility assets for the GitHub source release.
Machine-local files are not release assets: `benchmark/config.json` and
`benchmark/build/` are gitignored and excluded from source distributions.

The benchmark itself is path-agnostic. Every machine-specific path (project
root, run root, WSL user, Amber/Multiwfn binaries) lives in
`benchmark/config.json`, which is gitignored. Templates only contain
placeholders like `{{project_root}}` and `{{case.pdb_path}}`; placeholders are
resolved by `render_prompt.py`.

## Layout

```
benchmark/
  4EJJ/                          # structure, SDF, reviewed MOL2/frcmod, checksums
  1Z10/                          # crystal-structure input (CYP + coumarin, IC6)
  1Z11/                          # crystal-structure input (CYP + 8-methoxypsoralen, IC6)
  prompts/
    full_test.md.tmpl            # full CYPForge ablation template
    no_outer_shell_test.md.tmpl  # no-outer-shell ablation template
    no_cypforge_test.md.tmpl     # no-CYPForge (AmberTools-only) ablation template
  config.example.json            # commit this; copy to config.json locally
  config.json                    # local-only (gitignored)
  render_prompt.py               # render a template + config into a prompt
  build/                         # rendered prompts (gitignored)
  README.md
  .gitignore
```

## One-time setup

```powershell
cd <PROJECT_ROOT>\benchmark
copy config.example.json config.json
# Edit config.json: replace every "<set to ...>" with your local path/value.
```

`config.json` must define:

| Key | Meaning |
| --- | --- |
| `project_root` | Absolute path to the local CYPForge repo root |
| `benchmark_input_root` | Absolute path to this `benchmark/` directory |
| `run_root_base` | Where rendered runs will write their RUN_ROOT (e.g. `C:/cypforge_agent_runs`) |
| `wsl_user` | Your WSL username (Windows hosts only) |
| `amber_sh` | WSL path to `amber.sh`, e.g. `/home/<user>/amber25/amber.sh` |
| `multiwfn_bin` | WSL path to `Multiwfn_noGUI` |
| `cases.<name>.*` | Per-case scientific facts (kept in config so templates stay generic) |

The default `cases` block ships the verified residue/atom/chain/charge facts
for 4EJJ, 1Z10, and 1Z11. Update only if you replace the input PDB/SDF.

## Rendering a benchmark prompt

```powershell
cd <PROJECT_ROOT>
python benchmark\render_prompt.py --case 4EJJ --variant full
python benchmark\render_prompt.py --case 1Z10 --variant no_outer_shell
python benchmark\render_prompt.py --case 1Z11 --variant no_cypforge
```

Each invocation writes `benchmark/build/<variant>_<case>.md` and prints the
output path on stdout. Override the run identifier with `--run-id`, and the
output path with `--out`. The script aborts if the config still contains an
unfilled `<set to ...>` value or if a template uses a placeholder name that
the script did not register.

## Variants

| Variant | Purpose |
| --- | --- |
| `full` | Full CYPForge route (skills, outer shell, all module scripts) up to but not including `core3_run_pre_md`. |
| `no_outer_shell` | Module-script-only execution. Outer shell, orchestrator, skills, and prior runs are forbidden. The agent must reconstruct the workflow from low-level scripts. |
| `no_cypforge` | AmberTools-only. No CYPForge code/scripts/skills/outputs are allowed. A correct hard-stop is an acceptable outcome. |

## Cases

| Case | Heme state | PDB chains | Ligand | Axial Cys (in PDB) | Why this case |
| --- | --- | --- | --- | --- | --- |
| `4EJJ` | CPDI (Fe=O) | blank | nicotine (NCT) | `CYM 410`, Fe-SG = 2.55 Angstrom | Compound I + ATOM-record HEM + blank chains stress test. |
| `1Z10` | IC6 (resting Fe) | A | coumarin (COU) | `CYP A 439`, Fe-SG = 2.37 Angstrom | Standard IC6 with chain A, HETATM HEM. |
| `1Z11` | IC6 (resting Fe) | A | 8-methoxypsoralen (8MO) | `CYP A 439`, Fe-SG = 2.37 Angstrom | Second IC6 benchmark with a different ligand chemistry. |

### PDB preprocessing status

The bundled PDB files are **not raw RCSB X-ray entries** - they are CYPForge-prepared
intermediates committed into the benchmark so all three ablation variants start
from the same input. Two consequences matter for the `no_cypforge` variant in
particular:

- The proximal (axial) Cys has already been renamed away from `CYS`. 4EJJ stores
  it as `CYM` (anionic thiolate); 1Z10 / 1Z11 store it as `CYP` (CYPForge's
  internal name from `cypforge.heme.prepare.standardize_proximal_cyp`). An
  AmberTools-only agent should treat this residue name as a fact of the input
  file, not assume the raw RCSB `CYS` naming.
- Each PDB *also* contains an unrelated non-axial `CYS` residue (4EJJ: `CYS 53`,
  1Z10 / 1Z11: `CYS A 82`) that sits ~21 Angstrom from the iron. **Do not** identify
  the axial Cys by residue name alone - verify by Fe-SG distance (~2.3-2.6 Angstrom).

Each case's `pdb_preprocessing_note` field in `config.example.json` records this
explicitly. The prompt templates render the axial residue as
`{{case.axial_cys_resname}}{{case.axial_cys_resid}}` so the agent sees the
actual residue name in the PDB, not a hardcoded `CYM`.

## Reproducibility notes

- `config.json` and `build/` are gitignored. Commit only `config.example.json`
  and templates. Anyone re-running the benchmark must regenerate prompts
  from their own machine-local config.
- The per-case scientific facts in `config.example.json` were verified by
  direct inspection of the bundled PDB/SDF files. Treat them as the canonical
  expected-state declarations the agent must match during intake.
- `4EJJ/NCT_multiwfn_resp.mol2` and `4EJJ/NCT.frcmod` are the reviewed ligand
  parameters used by the quick no-QM route. `4EJJ/SHA256SUMS.txt` records their
  file checksums. CYPForge still verifies composition, charge, atom names, and
  coordinates against the supplied SDF and confirmed complex before use.
- Rendered prompts (`benchmark/build/<run_id>.md`) are themselves
  reproducible artifacts. To re-run the same benchmark on another machine,
  ship only `config.json` (or share the rendered prompt directly).
- No template references hardcoded `C:\...` paths; the run root is derived
  from `run_root_base + run_id`. Linux/macOS runs work the same way once
  `run_root_base` is set to a host-native path.
