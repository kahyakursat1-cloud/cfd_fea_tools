"""Analysis pipeline: STL/STEP -> mesh -> CalculiX/OpenFOAM -> results.

GENEL (geometriden-bağımsız) sıfırdan CFD/FEA motoru. Herhangi bir STL'i alır,
domain + mesh üretir (snappyHexMesh / gmsh tet), çözer ve sonuç çıkarır.

`pipeline.py` (uçağa-özel V&V iş akışı) ile TAMAMLAYICIDIR, eskimiş değildir:
- pipeline.py → belirli uçak konfigi, V-n zarfı, sertifikasyon zinciri
- analysis/   → keyfi geometri için sıfırdan mesh→çözüm

2026-06-03 uçtan uca doğrulandı (küre: CFD Cd=0.135, FEA .frd). Bkz.
docs/adr/0001-kanonik-mimari.md. Tüketici: check_cfd_pipeline / check_fea_pipeline.
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
from .tet_mesher import TetMesh, generate_tet_mesh, repair_mesh

# GÖRÜNTÜLEYİCİ İSTEĞE BAĞLI. `result_viewer` `pyvista` ithal ediyor ve bu satır
# eskiden koşulsuzdu: `analysis` paketini ithal eden HERKES bir masaüstü 3B
# görüntüleyiciye bağımlı oluyordu. Başsız konteyner tam burada düştü
# (2026-08-15) — çekirdek hesap katmanı sunum katmanına bağımlı olmamalı.
#
# Ad KORUNUR: `from analysis import show_standalone` çalışmaya devam eder;
# pyvista yoksa çağrıldığında ANLAŞILIR bir hata verir, ithalde değil.
try:
    from .result_viewer import build_unstructured_grid, show_standalone
except ImportError as _e:                                      # pragma: no cover
    _viewer_hata = _e

    def _viewer_yok(*_a, **_k):
        raise ImportError(
            "3B görüntüleyici için `pyvista` gerekli (isteğe bağlı bağımlılık): "
            f"pip install 'cfdfea-tools[viz]'  —  özgün hata: {_viewer_hata}")

    build_unstructured_grid = show_standalone = _viewer_yok

__all__ = [
    "GeometryInfo", "load_geometry", "BBOX_SIDES", "faces_in_axis_band",
    "TetMesh", "generate_tet_mesh", "repair_mesh",
    "FEAMaterial", "FixedBC", "PressureLoad", "ForceLoad", "FEACase",
    "write_inp", "surface_face_nodes",
    "run_ccx", "CCXResult", "FRDResult", "parse_frd",
    "build_unstructured_grid", "show_standalone",
    "CFDCase", "CFDResult", "run_cfd", "build_case", "parse_force_coeffs",
]
