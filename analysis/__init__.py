"""Analysis pipeline: STL/STEP -> mesh -> CalculiX/OpenFOAM -> results."""

from .geometry_loader import GeometryInfo, load_geometry, BBOX_SIDES, faces_in_axis_band
from .tet_mesher import TetMesh, generate_tet_mesh, repair_mesh
from .calculix_writer import (
    FEAMaterial, FixedBC, PressureLoad, ForceLoad, FEACase,
    write_inp, surface_face_nodes,
)
from .ccx_runner import run_ccx, CCXResult
from .frd_parser import FRDResult, parse_frd
from .result_viewer import build_unstructured_grid, show_standalone
from .openfoam_runner import CFDCase, CFDResult, run_cfd, build_case, parse_force_coeffs

__all__ = [
    "GeometryInfo", "load_geometry", "BBOX_SIDES", "faces_in_axis_band",
    "TetMesh", "generate_tet_mesh", "repair_mesh",
    "FEAMaterial", "FixedBC", "PressureLoad", "ForceLoad", "FEACase",
    "write_inp", "surface_face_nodes",
    "run_ccx", "CCXResult", "FRDResult", "parse_frd",
    "build_unstructured_grid", "show_standalone",
    "CFDCase", "CFDResult", "run_cfd", "build_case", "parse_force_coeffs",
]
