"""
PyVista 3D sonuç görüntüleyici.

İki kullanım modu:
1. Standalone: tek pencerede aç (debug için)
2. Embedded: PySide6 widget olarak göm (`pyvistaqt.QtInteractor`)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv

from .frd_parser import FRDResult, parse_frd
from .tet_mesher import TetMesh


def build_unstructured_grid(mesh: TetMesh, frd: FRDResult) -> pv.UnstructuredGrid:
    """TetMesh + FRDResult -> PyVista UnstructuredGrid (skalar/vektör alanlar dahil)."""
    points = mesh.points

    # Hücre tipi: VTK_QUADRATIC_TETRA = 24, VTK_TETRA = 10
    if mesh.element_type == "C3D10":
        cell_type = pv.CellType.QUADRATIC_TETRA
        n_per_cell = 10
        # CalculiX/Abaqus C3D10 vs VTK_QUADRATIC_TETRA aynı node ordering
    else:
        cell_type = pv.CellType.TETRA
        n_per_cell = 4

    n_cells = len(mesh.tets)
    cells = np.empty((n_cells, n_per_cell + 1), dtype=np.int64)
    cells[:, 0] = n_per_cell
    cells[:, 1:] = mesh.tets
    cells_flat = cells.flatten()

    cell_types = np.full(n_cells, cell_type, dtype=np.uint8)
    grid = pv.UnstructuredGrid(cells_flat, cell_types, points)

    # Sonuçları point data olarak ekle
    # frd.node_ids 1-indexed, mesh.points sıralı (0..N-1)
    # CalculiX node sıralaması bizim sıralamayla aynı (write_inp'te 1..N)
    # ama frd parse sırası farklı olabilir — yeniden indeksleyelim
    n_pts = len(points)

    if "DISP" in frd.fields:
        disp = np.zeros((n_pts, 3), dtype=np.float64)
        for nid, d in zip(frd.node_ids, frd.fields["DISP"]):
            idx = nid - 1
            if 0 <= idx < n_pts:
                disp[idx] = d
        grid.point_data["Displacement"] = disp
        grid.point_data["Displacement_Magnitude"] = np.linalg.norm(disp, axis=1)

    if "STRESS" in frd.fields:
        stress = np.zeros((n_pts, 6), dtype=np.float64)
        for nid, s in zip(frd.node_ids, frd.fields["STRESS"]):
            idx = nid - 1
            if 0 <= idx < n_pts:
                stress[idx] = s
        grid.point_data["Stress"] = stress
        sxx, syy, szz, sxy, syz, szx = (stress[:, i] for i in range(6))
        vm = np.sqrt(0.5 * (
            (sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2
            + 6.0 * (sxy ** 2 + syz ** 2 + szx ** 2)
        ))
        grid.point_data["VonMises"] = vm

    return grid


def show_standalone(mesh: TetMesh, frd: FRDResult,
                     scalar: str = "VonMises",
                     warp_factor: float = 0.0) -> None:
    """Standalone PyVista penceresinde sonucu göster.

    Args:
        scalar: 'VonMises', 'Displacement_Magnitude', vs.
        warp_factor: deplasmanı görsel olarak abart (örn 100). 0 = abartma.
    """
    grid = build_unstructured_grid(mesh, frd)

    if warp_factor > 0 and "Displacement" in grid.point_data:
        grid = grid.warp_by_vector("Displacement", factor=warp_factor)

    plotter = pv.Plotter()
    if scalar in grid.point_data:
        plotter.add_mesh(grid, scalars=scalar, cmap="jet",
                         show_edges=False, scalar_bar_args={"title": scalar})
    else:
        plotter.add_mesh(grid, show_edges=False, color="lightgray")

    plotter.add_axes()
    plotter.show_grid()
    plotter.show()


def quick_view_from_files(frd_path: Path, mesh: TetMesh,
                           scalar: str = "VonMises",
                           warp_factor: float = 0.0) -> None:
    """FRD dosyasını oku ve göster."""
    frd = parse_frd(frd_path)
    show_standalone(mesh, frd, scalar=scalar, warp_factor=warp_factor)
