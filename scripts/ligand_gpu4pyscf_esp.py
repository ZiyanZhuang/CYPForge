#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cypforge_core.ligand_gpu4pyscf_esp import (
    extract_ligand_from_complex_pdb,
    prepare_complex_sdf_ligand_resp_inputs,
    prepare_gpu4pyscf_esp_job,
    prepare_gpu4pyscf_molden_job,
    run_complex_ligand_multiwfn_resp_parameterization,
    run_complex_sdf_ligand_multiwfn_resp_parameterization,
    run_gpu4pyscf_esp_parameterization,
    run_gpu4pyscf_multiwfn_resp_parameterization,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="CYPForge second core: exact-pose GPU4PySCF/PySCF + Multiwfn RESP ligand parameterization.")
    parser.add_argument("--ligand-pose", help="Hydrogen-complete ligand pose MOL2/PDB. MOL2 is required for direct charge injection/frcmod.")
    parser.add_argument("--complex-pdb", help="User-confirmed protein+heme+ligand complex PDB. This is the main second-core input.")
    parser.add_argument("--ligand-template-sdf", help="Ligand SDF chemistry source for bond graph/bond order/GAFF2 typing; coordinates still come from --complex-pdb.")
    parser.add_argument("--ligand-resname", default="LIG")
    parser.add_argument("--ligand-chain", default="")
    parser.add_argument("--blank-ligand-chain", action="store_true", help="Select a ligand whose PDB chain ID is blank.")
    parser.add_argument("--formal-charge", type=int, required=True)
    parser.add_argument("--spin", type=int, default=1)
    parser.add_argument("--basis", default="6-31g*")
    parser.add_argument("--points-per-atom", type=int, default=24)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fit-method", choices=["multiwfn-resp", "esp-lsq"], default="multiwfn-resp")
    parser.add_argument("--multiwfn-bin", default=None, help="Default: MULTIWFN_BIN, then bundled fallback path.")
    parser.add_argument("--amber-sh", default=None, help="Path to amber.sh. Default: $AMBER_SH, then $AMBERHOME/amber.sh. Required if env vars are not set.")
    parser.add_argument("--prepare-only", action="store_true", help="Write QM inputs and runner without executing SCF.")
    parser.add_argument("--cpu-only", action="store_true", help="Do not call mf.to_gpu().")
    parser.add_argument("--require-gpu", action="store_true", help="Fail if GPU4PySCF cannot be used.")
    parser.add_argument("--no-parmchk2", action="store_true")
    parser.add_argument("--resp-geometry-cleanup", choices=["h-only", "none"], default="none")
    parser.add_argument(
        "--pre-resp-relax",
        choices=["pbe-h-only", "none"],
        default="pbe-h-only",
        help="Pre-RESP geometry cleanup: pbe-h-only = H-only PBE relaxation (default, GPU); none = skip.",
    )
    args = parser.parse_args()
    if args.blank_ligand_chain:
        args.ligand_chain = ""

    out = Path(args.output_dir)
    ligand_pose = args.ligand_pose
    if not ligand_pose and not args.complex_pdb:
        parser.error("Provide --ligand-pose or --complex-pdb.")

    try:
        if args.complex_pdb and args.ligand_template_sdf and not args.prepare_only and args.fit_method == "multiwfn-resp":
            result = run_complex_sdf_ligand_multiwfn_resp_parameterization(
                complex_pdb=args.complex_pdb,
                ligand_template_sdf=args.ligand_template_sdf,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                formal_charge=args.formal_charge,
                output_dir=out,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                multiwfn_bin=args.multiwfn_bin,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
                resp_geometry_cleanup=args.resp_geometry_cleanup,
                pre_resp_relax=args.pre_resp_relax,
            )
        elif args.complex_pdb and not args.prepare_only and args.fit_method == "multiwfn-resp":
            result = run_complex_ligand_multiwfn_resp_parameterization(
                complex_pdb=args.complex_pdb,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                formal_charge=args.formal_charge,
                output_dir=out,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                multiwfn_bin=args.multiwfn_bin,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
                resp_geometry_cleanup=args.resp_geometry_cleanup,
            )
        elif args.complex_pdb and args.ligand_template_sdf and args.prepare_only:
            result = prepare_complex_sdf_ligand_resp_inputs(
                complex_pdb=args.complex_pdb,
                ligand_template_sdf=args.ligand_template_sdf,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                formal_charge=args.formal_charge,
                output_dir=out,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
            )
        elif args.complex_pdb and args.prepare_only:
            ligand_pose = str(out / f"{args.ligand_resname}_from_confirmed_complex.pdb")
            extract_ligand_from_complex_pdb(
                complex_pdb=args.complex_pdb,
                ligand_resname=args.ligand_resname,
                ligand_chain=args.ligand_chain,
                output_pdb=ligand_pose,
            )
            result = prepare_gpu4pyscf_molden_job(
                ligand_pose=ligand_pose,
                formal_charge=args.formal_charge,
                output_dir=out,
                resname=args.ligand_resname,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
            )
        elif args.prepare_only:
            if args.fit_method == "multiwfn-resp":
                result = prepare_gpu4pyscf_molden_job(
                    ligand_pose=ligand_pose,
                    formal_charge=args.formal_charge,
                    output_dir=out,
                    resname=args.ligand_resname,
                    spin_multiplicity=args.spin,
                    basis=args.basis,
                    use_gpu=not args.cpu_only,
                    require_gpu=args.require_gpu,
                )
            else:
                result = prepare_gpu4pyscf_esp_job(
                    ligand_pose=ligand_pose,
                    formal_charge=args.formal_charge,
                    output_dir=out,
                    resname=args.ligand_resname,
                    spin_multiplicity=args.spin,
                    basis=args.basis,
                    points_per_atom=args.points_per_atom,
                    use_gpu=not args.cpu_only,
                    require_gpu=args.require_gpu,
                )
        elif args.fit_method == "multiwfn-resp":
            result = run_gpu4pyscf_multiwfn_resp_parameterization(
                ligand_pose=ligand_pose,
                formal_charge=args.formal_charge,
                output_dir=out,
                resname=args.ligand_resname,
                spin_multiplicity=args.spin,
                basis=args.basis,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                multiwfn_bin=args.multiwfn_bin,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
                resp_geometry_cleanup=args.resp_geometry_cleanup,
            )
        else:
            result = run_gpu4pyscf_esp_parameterization(
                ligand_pose=ligand_pose,
                formal_charge=args.formal_charge,
                output_dir=out,
                resname=args.ligand_resname,
                spin_multiplicity=args.spin,
                basis=args.basis,
                points_per_atom=args.points_per_atom,
                use_gpu=not args.cpu_only,
                require_gpu=args.require_gpu,
                amber_sh=args.amber_sh,
                run_parmchk2=not args.no_parmchk2,
            )
    except Exception as exc:
        result = {
            "schema": "cypforge.gpu4pyscf_esp_cli_result.v1",
            "status": "failed",
            "error": str(exc),
            "input_ligand_pose": ligand_pose,
            "formal_charge": args.formal_charge,
        }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"prepared", "success"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
