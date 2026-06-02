"""Analysis pipeline: STL/STEP -> mesh -> CalculiX/OpenFOAM -> results.

.. deprecated::
    Bu paket eski kuşak #3 (bkz. docs/adr/0001-kanonik-mimari.md). Kanonik
    CFD/FEA path: ``simulation_runner`` / ``fea_runner`` (pipeline.py üzerinden).
    Yalnızca küre doğrulama smoke testleri (test_cfd_pipeline / test_fea_pipeline)
    tüketir. Yeni kod buraya bağımlılık eklememeli.
"""

from .calculix_writer import (
    FEACase,
    FEAMaterial,
    FixedBC,
    ForceLoad,
    PressureLoad,
    surface_face_nodes,
    write_inp,
)
from .ccx_runner import CCXResult, run_ccx
from .frd_parser import FRDResult, parse_frd
from .geometry_loader import BBOX_SIDES, GeometryInfo, faces_in_axis_band, load_geometry
from .openfoam_runner import CFDCase, CFDResult, build_case, parse_force_coeffs, run_cfd
from .result_viewer import build_unstructured_grid, show_standalone
from .tet_mesher import TetMesh, generate_tet_mesh, repair_mesh

__all__ = [
    "GeometryInfo", "load_geometry", "BBOX_SIDES", "faces_in_axis_band",
    "TetMesh", "generate_tet_mesh", "repair_mesh",
    "FEAMaterial", "FixedBC", "PressureLoad", "ForceLoad", "FEACase",
    "write_inp", "surface_face_nodes",
    "run_ccx", "CCXResult", "FRDResult", "parse_frd",
    "build_unstructured_grid", "show_standalone",
    "CFDCase", "CFDResult", "run_cfd", "build_case", "parse_force_coeffs",
]
