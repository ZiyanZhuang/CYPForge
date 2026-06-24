# cypforge.core1_prepare_heme_cym

## Purpose

Prepare CYP450 protein + HEME/CYM coordinates and generate heme/CYM LEaP mapping without changing ligand chemistry or performing solvation.

## Inputs

```text
raw_protein_heme_pdb
heme_state: IC6 | DIOXY | CPDI
heme_resname
heme_chain
protein_chain
axial_cys_current_resid
run_root
project_root
```

## Required Files

```text
<PROJECT_ROOT>/scripts/heme_only.py
<PROJECT_ROOT>/scripts/heme_mapping_leapin.py
<RAW_PROTEIN_HEME_PDB>
```

## Commands

```powershell
cd "<PROJECT_ROOT>"
$env:PYTHONPATH="<PROJECT_ROOT>\src"

python scripts\heme_only.py `
  --heme-state <IC6|DIOXY|CPDI> `
  --output-dir "<RUN_ROOT>\01_heme_only" `
  --heme-resname <HEME_RESNAME> `
  --heme-chain <HEME_CHAIN> `
  --protein-chain <PROTEIN_CHAIN> `
  --axial-cys-resid <AXIAL_CYS_CURRENT_RESID> `
  "<RAW_PROTEIN_HEME_PDB>"

python scripts\heme_mapping_leapin.py `
  --prepared-pdb "<RUN_ROOT>\01_heme_only\prepared.pdb" `
  --prepare-report-json "<RUN_ROOT>\01_heme_only\prepare_report.json" `
  --output-dir "<RUN_ROOT>\02_heme_mapping_leapin" `
  --heme-resname <HEME_RESNAME>
```

Dangerous optional transmembrane helix trimming before Core 1:

```powershell
python scripts\heme_only.py `
  --heme-state <IC6|DIOXY|CPDI> `
  --output-dir "<RUN_ROOT>\01_heme_only" `
  --heme-resname <HEME_RESNAME> `
  --heme-chain <HEME_CHAIN> `
  --protein-chain <PROTEIN_CHAIN> `
  --axial-cys-resid <AXIAL_CYS_CURRENT_RESID> `
  --trim-transmembrane-range A:1-35 `
  --confirm-transmembrane-trim `
  "<RAW_PROTEIN_HEME_PDB>"
```

This option is disabled unless both conditions are true:

```text
the human user supplied exact chain:residue ranges, e.g. A:1-35
the command includes --confirm-transmembrane-trim
```

`--trim-transmembrane-range` may be repeated or comma-separated. It removes only explicit ATOM residue ranges before heme/CYP detection and writes `transmembrane_trimmed_input.pdb` plus an `optional_transmembrane_trim` audit block in `prepare_report.json`.

Strict rules:

```text
Never auto-predict transmembrane helices for deletion.
Never infer a trim range from screenshots, vague wording, hydrophobicity, or sequence position alone.
Never add --trim-transmembrane-range unless the user explicitly gave exact chain:residue ranges.
Never add --confirm-transmembrane-trim unless the user explicitly confirmed the deletion intent.
Never trim the proximal Cys, selected HEM, catalytic residues needed for the question, unresolved loop anchors, or residues required to preserve the intended structural model.
If the user asks "can we remove TM helices?" without exact ranges, stop and ask for exact ranges plus confirmation.
```

## Outputs

```text
<RUN_ROOT>/01_heme_only/prepared.pdb
<RUN_ROOT>/01_heme_only/prepare_report.json
<RUN_ROOT>/01_heme_only/transmembrane_trimmed_input.pdb  # optional, only when trimming is enabled
<RUN_ROOT>/02_heme_mapping_leapin/heme_mapping_leapin.in
<RUN_ROOT>/02_heme_mapping_leapin/heme_mapping_manifest.json
<RUN_ROOT>/02_heme_mapping_leapin/core1_decision_report.md
```

## Hard Gates

`FAIL` if:

```text
prepared.pdb missing
prepare_report.json missing
heme_mapping_leapin.in missing
proximal cysteine is not CYM in prepared coordinates
CYM SG has HG
HEM Fe atom missing
heme state in output does not match requested IC6/DIOXY/CPDI
IC6 contains DIOXY/CPDI oxygen atoms or DIOXY/CPDI lacks required oxygen atoms
Fe-SG distance outside chemically plausible range
any Fe-Nporphyrin distance outside chemically plausible range
HEM/CYM parameter source cannot be traced
HEME/CYM parameter package does not match requested heme state
transmembrane trimming was requested without exact human-provided chain:residue ranges
transmembrane trimming was requested without --confirm-transmembrane-trim
optional_transmembrane_trim removed zero residues
optional_transmembrane_trim removed the proximal Cys or selected HEM context
```

Use these geometric ranges as audit defaults, not as claims about every CYP state:

```text
Fe-SG plausible range: 1.8-3.0 A; expected CYP range roughly 2.2-2.5 A
Fe-Nporphyrin plausible range: 1.7-2.5 A; expected range roughly 1.9-2.2 A
```

## Warning Gates

`WARN` if:

```text
Fe-SG or Fe-N distances pass broad hard range but are outside expected CYP range
heme face orientation has not been algebraically audited
current/original residue numbering is missing
proximal residue identity was inferred without explicit user confirmation
```

## Failure Behavior

Stop. Do not proceed to Core 2 ligand preparation or Core 3 solvation.

## Audit Artifacts

The decision report must include:

```text
requested heme state
heme residue name and chain
protein chain
axial CYM current residue ID
Fe atom name
SG atom record
Fe-SG distance
Fe-Nporphyrin distances
CYM HG absence check
heme state atom-count check
parameter source record
PASS/WARN/FAIL
```

## Scientific Interpretation

Core 1 proves that the protein-heme-CYM assembly is traceable and geometrically plausible. It does not prove ligand pose, ligand charges, protonation correctness outside CYM, or MD stability.
