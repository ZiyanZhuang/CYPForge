# cypforge.core3_finalize_protonation

## Purpose

Generate an advisory protonation review list and apply only explicit, audited residue-state decisions to the ligand-aware final complex. Recommendations must not be applied automatically.

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
<PROJECT_ROOT>/src/cypforge_core/cli.py
<LIGAND_MAPPING_MANIFEST_JSON>
<ORIGINAL_PREPARED_COMPLEX_PDB>
<PROTONATION_DECISION_JSON>
```

## Example Reviewed Decision

```text
<CHAIN>:GLU<ORIGINAL_RESID> -> GLH
<CHAIN>:HIE<ORIGINAL_RESID> -> HID
watchlist residues remain unchanged unless explicitly confirmed
manifest-declared proximal CYM remains CYM
```

This is an example from one reviewed CYP benchmark, not a default policy.
The decision JSON must record both current and original residue numbering for
any high-risk residue selected by the user.

## Command

Generate the review list first:

```text
cypforge protonation recommend <RUN_NAME> --ph 7.4
```

Apply user-confirmed selectors or a reviewed decision JSON:

```text
cypforge protonation apply <RUN_NAME> --set A:GLU419=GLH
```

Selectors and recommendation output use the chain and residue number from the
original prepared PDB. The decision JSON also records the corresponding
assembled LEaP residue index.

The low-level module command is:

```powershell
cypforge module protonation finalize `
  --ligand-mapping-manifest-json "<LIGAND_MAPPING_MANIFEST_JSON>" `
  --original-prepared-pdb "<ORIGINAL_PREPARED_COMPLEX_PDB>" `
  --protonation-decision-json "<PROTONATION_DECISION_JSON>" `
  --output-dir "<RUN_ROOT>\14_complex_protonation_finalize"
```

## Outputs

```text
<RUN_ROOT>/14_complex_protonation_finalize/complex_ligand_protonation_final.pdb
<RUN_ROOT>/14_complex_protonation_finalize/complex_protonation_final_leap.in
<RUN_ROOT>/14_complex_protonation_finalize/protonation_finalize_manifest.json
```

## Hard Gates

`FAIL` if:

```text
finalized complex PDB missing
protonation manifest missing
requested GLH residue was not renamed to GLH
requested HID residue was not renamed to HID
manifest-declared proximal CYM is not retained as CYM
current/original numbering for renamed residues is absent
GLH419 lacks a chemically plausible carboxylic proton
HID residues do not have intended ND1-H / NE2 tautomer state
GLH419 creates severe H clash
HID rename creates donor-donor clash or severe H clash
expected dry complex charge change is inconsistent with the decision JSON
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

A selector that does not match the chain, current residue name, and original residue number is a hard failure. Generic titratable residue names without site-specific evidence remain in manual-review state.

Stop. Do not solvate, ionize, or run tLeap on a model whose residue renames or charge sanity fail.

## Audit Artifacts

Decision report must include:

```text
protonation decision JSON path
current/original residue map
renamed residue table
proton atom and oxygen assignment for any requested GLH/ASH residue
HID ND1/NE2 hydrogen state table
watchlist residues
old dry charge
new expected dry charge
observed dry charge if available
PASS/WARN/FAIL
```

## Scientific Interpretation

Residue renaming is a mechanistic decision. This module confirms that the chosen decision was applied. It does not prove that the chosen protonation state is globally correct without pKa and local environment evidence.
