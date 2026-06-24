#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _parse_pdb_atoms(path: Path) -> list[dict]:
    atoms = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        atoms.append(
            {
                "line": line,
                "name": line[12:16].strip(),
                "resname": line[17:20].strip(),
                "chain": line[21].strip(),
                "resid": line[22:26].strip(),
                "x": float(line[30:38]),
                "y": float(line[38:46]),
                "z": float(line[46:54]),
                "element": (line[76:78].strip() or line[12:16].strip()[0]).upper(),
            }
        )
    return atoms


def _parse_mol2_bonds(path: Path) -> list[tuple[str, str]]:
    atoms: dict[int, str] = {}
    bonds: list[tuple[str, str]] = []
    section = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("@<TRIPOS>ATOM"):
            section = "atom"
            continue
        if line.startswith("@<TRIPOS>BOND"):
            section = "bond"
            continue
        if line.startswith("@<TRIPOS>"):
            section = None
            continue
        parts = line.split()
        if section == "atom" and len(parts) >= 2:
            atoms[int(parts[0])] = parts[1]
        elif section == "bond" and len(parts) >= 4:
            a = atoms[int(parts[1])]
            b = atoms[int(parts[2])]
            bonds.append((a, b))
    return bonds


def _parse_mol2_atoms(path: Path) -> list[dict]:
    atoms = []
    section = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("@<TRIPOS>ATOM"):
            section = "atom"
            continue
        if line.startswith("@<TRIPOS>"):
            section = None
            continue
        if section != "atom":
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        atom_type = parts[5]
        element = "".join(ch for ch in atom_type.split(".")[0] if ch.isalpha()).upper()
        if len(element) > 1:
            element = element[0] + element[1:].lower()
        atoms.append(
            {
                "name": parts[1],
                "x": float(parts[2]),
                "y": float(parts[3]),
                "z": float(parts[4]),
                "element": element.upper(),
            }
        )
    return atoms


def _distance(a: dict, b: dict) -> float:
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)


def _format_xyz(line: str, x: float, y: float, z: float) -> str:
    if len(line) < 80:
        line = line.ljust(80)
    return f"{line[:30]}{x:8.3f}{y:8.3f}{z:8.3f}{line[54:]}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a mode-11 hydrogen-complete complex by grafting mode-11 heavy atom coordinates onto an existing complete NCT complex."
    )
    parser.add_argument("--template-complex", required=True)
    parser.add_argument("--mode11-pdb", required=True)
    parser.add_argument("--mode11-hcomplete-mol2")
    parser.add_argument("--template-ligand-mol2", required=True)
    parser.add_argument("--ligand-resname", default="NCT")
    parser.add_argument("--ligand-chain", default="C")
    parser.add_argument("--output-pdb", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    template_complex = Path(args.template_complex)
    mode11_pdb = Path(args.mode11_pdb)
    template_ligand_mol2 = Path(args.template_ligand_mol2)
    output_pdb = Path(args.output_pdb)
    manifest_path = Path(args.manifest)
    output_pdb.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    template_atoms = _parse_pdb_atoms(template_complex)
    mode11_atoms = _parse_pdb_atoms(mode11_pdb)
    mode11_hcomplete_atoms = _parse_mol2_atoms(Path(args.mode11_hcomplete_mol2)) if args.mode11_hcomplete_mol2 else []
    ligand_atoms = [
        atom
        for atom in template_atoms
        if atom["resname"] == args.ligand_resname and atom["chain"] == args.ligand_chain
    ]
    if not ligand_atoms:
        raise SystemExit(f"No {args.ligand_resname} atoms found on chain {args.ligand_chain} in {template_complex}")

    mode11_by_name = {atom["name"]: atom for atom in mode11_atoms if atom["element"] != "H"}
    ligand_by_name = {atom["name"]: atom for atom in ligand_atoms}
    heavy_template = [atom for atom in ligand_atoms if atom["element"] != "H"]
    missing = sorted(atom["name"] for atom in heavy_template if atom["name"] not in mode11_by_name)
    extra = sorted(name for name in mode11_by_name if name not in ligand_by_name)
    if missing or extra:
        raise SystemExit(f"Mode-11/template heavy atom name mismatch: missing={missing}; extra={extra}")

    bonds = _parse_mol2_bonds(template_ligand_mol2)
    hydrogen_parent: dict[str, str] = {}
    for a, b in bonds:
        a_is_h = a.startswith("H")
        b_is_h = b.startswith("H")
        if a_is_h and not b_is_h:
            hydrogen_parent[a] = b
        elif b_is_h and not a_is_h:
            hydrogen_parent[b] = a

    new_coords: dict[str, tuple[float, float, float]] = {}
    new_names: dict[str, str] = {}
    if mode11_hcomplete_atoms:
        if len(mode11_hcomplete_atoms) != len(ligand_atoms):
            raise SystemExit(
                f"Hydrogen-complete mode-11 MOL2 atom count {len(mode11_hcomplete_atoms)} "
                f"does not match template ligand atom count {len(ligand_atoms)}"
            )
        hydrogen_names = [atom["name"] for atom in ligand_atoms if atom["element"] == "H"]
        h_idx = 0
        for template_atom, source_atom in zip(ligand_atoms, mode11_hcomplete_atoms):
            if template_atom["element"] != source_atom["element"]:
                raise SystemExit(
                    f"Element mismatch while writing h-complete mode-11 ligand: "
                    f"template {template_atom['name']}={template_atom['element']} source {source_atom['name']}={source_atom['element']}"
                )
            new_coords[template_atom["name"]] = (source_atom["x"], source_atom["y"], source_atom["z"])
            if source_atom["element"] == "H":
                new_names[template_atom["name"]] = hydrogen_names[h_idx]
                h_idx += 1
            else:
                new_names[template_atom["name"]] = source_atom["name"]
    else:
        for atom in heavy_template:
            pose_atom = mode11_by_name[atom["name"]]
            new_coords[atom["name"]] = (pose_atom["x"], pose_atom["y"], pose_atom["z"])
            new_names[atom["name"]] = atom["name"]
        for atom in ligand_atoms:
            if atom["element"] != "H":
                continue
            parent_name = hydrogen_parent.get(atom["name"])
            if parent_name is None:
                raise SystemExit(f"No heavy-atom parent found in MOL2 bonds for hydrogen {atom['name']}")
            old_parent = ligand_by_name[parent_name]
            new_parent = new_coords[parent_name]
            new_coords[atom["name"]] = (
                new_parent[0] + atom["x"] - old_parent["x"],
                new_parent[1] + atom["y"] - old_parent["y"],
                new_parent[2] + atom["z"] - old_parent["z"],
            )
            new_names[atom["name"]] = atom["name"]

    out_lines = []
    ligand_count = 0
    for line in template_complex.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(("ATOM", "HETATM")) and line[17:20].strip() == args.ligand_resname and line[21].strip() == args.ligand_chain:
            name = line[12:16].strip()
            x, y, z = new_coords[name]
            renamed = f"{line[:12]}{new_names[name]:>4}{line[16:]}"
            out_lines.append(_format_xyz(renamed, x, y, z))
            ligand_count += 1
        else:
            out_lines.append(line)
    output_pdb.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    rebuilt_ligand = [
        {"name": atom["name"], "element": atom["element"], "x": new_coords[atom["name"]][0], "y": new_coords[atom["name"]][1], "z": new_coords[atom["name"]][2]}
        for atom in ligand_atoms
    ]
    h_parent_distances = []
    rebuilt_by_name = {atom["name"]: atom for atom in rebuilt_ligand}
    for h_name, parent_name in sorted(hydrogen_parent.items()):
        if h_name in rebuilt_by_name and parent_name in rebuilt_by_name:
            h_parent_distances.append(_distance(rebuilt_by_name[h_name], rebuilt_by_name[parent_name]))

    manifest = {
        "schema": "cypforge.mode11_hcomplete_complex_graft.v1",
        "template_complex": str(template_complex),
        "mode11_heavy_pose": str(mode11_pdb),
        "mode11_hcomplete_mol2": str(Path(args.mode11_hcomplete_mol2)) if args.mode11_hcomplete_mol2 else None,
        "template_ligand_mol2": str(template_ligand_mol2),
        "output_pdb": str(output_pdb),
        "ligand_resname": args.ligand_resname,
        "ligand_chain": args.ligand_chain,
        "ligand_atom_count": ligand_count,
        "mode11_heavy_atom_count": len(mode11_by_name),
        "hydrogen_count": sum(1 for atom in ligand_atoms if atom["element"] == "H"),
        "hydrogen_coordinate_policy": "Hydrogen coordinates are taken from the h-complete mode-11 MOL2 when provided; otherwise they are translated with their bonded heavy atom from the complete template. Downstream RESP h-only cleanup may regularize bond lengths.",
        "heavy_coordinate_policy": "All ligand heavy atom coordinates are taken from the mode-11 Vina pose by atom name.",
        "hydrogen_parent_distance_min_a": round(min(h_parent_distances), 6),
        "hydrogen_parent_distance_max_a": round(max(h_parent_distances), 6),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
