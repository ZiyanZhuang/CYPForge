# cypforge.core3_finalize_protonation

## Purpose

Apply explicit, audited residue rename decisions to the ligand-aware final complex. This module must not infer or auto-correct protonation states.

## Inputs

```text
ligand_mapping_manifest_json
original_prepared_complex_pdb
protonation_decision_json
run_root
project_root
```

## Required Files

```text
<PROJECT_ROOT>/scripts/complex_protonation_finalize.py
<LIGAND_MAPPING_MANIFEST_JSON>
<ORIGINAL_PREPARED_COMPLEX_PDB>
<PROTONATION_DECISION_JSON>
```

## Canonical Mode11 Decision

```text
GLU419 -> GLH419
HIE55 -> HID55
HIE299 -> HID299
HIE386 -> HID386
GLU275 remains GLU as watchlist
ASP residues remain ASP, with ASP237 and ASP335 as watchlist
CYM410 remains CYM
```

The decision JSON must record both current and original residue numbering for high-risk residues.

## Command

```powershell
cd "<PROJECT_ROOT>"
$env:PYTHONPATH="<PROJECT_ROOT>\src"

python scripts\complex_protonation_finalize.py `
  --ligand-mapping-manifest-json "<LIGAND_MAPPING_MANIFEST_JSON>" `
  --original-prepared-pdb "<ORIGINAL_PREPARED_COMPLEX_PDB>" `
  --protonation-decision-json "<PROTONATION_DECISION_JSON>" `
  --output-dir "<RUN_ROOT>\14_complex_protonation_finalize"
```

## Outputs

```text
<RUN_ROOT>/14_complex_protonation_finalize/finalized_complex.pdb
<RUN_ROOT>/14_complex_protonation_finalize/protonation_finalize_manifest.json
<RUN_ROOT>/14_complex_protonation_finalize/residue_rename_audit.*
<RUN_ROOT>/14_complex_protonation_finalize/charge_prediction_audit.*
<RUN_ROOT>/14_complex_protonation_finalize/core3_protonation_decision_report.md
```

## Hard Gates

`FAIL` if:

```text
finalized complex PDB missing
protonation manifest missing
residue 419 is not GLH when GLH419 is requested
residues 55, 299, or 386 are not HID when HID is requested
residue 410 is not CYM
current/original numbering for renamed residues is absent
GLH419 lacks a chemically plausible carboxylic proton
HID residues do not have intended ND1-H / NE2 tautomer state
GLH419 creates severe H clash
HID rename creates donor-donor clash or severe H clash
dry complex charge does not increase by +1 after GLU419 -> GLH419
mode11 main model dry charge is not approximately +6
```

## Warning Gates

`WARN` if:

```text
GLH419 proton is not clearly hydrogen-bonded but has no clash
HID tautomer has no clear local hydrogen-bond benefit but no clash
GLU275/ASP237/ASP335 watchlist lacks pKa-tool evidence
all HIS states were inherited from defaults without network evidence
```

## Failure Behavior

Stop. Do not solvate, ionize, or run tLeap on a model whose residue renames or charge sanity fail.

## Audit Artifacts

Decision report must include:

```text
protonation decision JSON path
current/original residue map
renamed residue table
GLH419 proton atom and oxygen assignment
HID ND1/NE2 hydrogen state table
watchlist residues
old dry charge
new expected dry charge
observed dry charge if available
PASS/WARN/FAIL
```

## Scientific Interpretation

Residue renaming is a mechanistic decision. This module confirms that the chosen decision was applied. It does not prove that the chosen protonation state is globally correct without pKa and local environment evidence.
