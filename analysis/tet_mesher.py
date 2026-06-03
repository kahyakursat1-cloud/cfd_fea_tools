"""
Tetrahedral hacim mesh üretimi (gmsh Python API).

Strateji:
  1. STL'i (gerekirse) onar (trimesh fill_holes + fix_normals)
  2. Geçici STL'i diske yaz
  3. gmsh.merge -> classifySurfaces -> createGeometry -> addSurfaceLoop -> addVolume
  4. mesh.generate(3) ile tet üret
  5. .msh 2.2 olarak yaz, meshio ile geri oku
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import gmsh
import meshio
import numpy as np
import trimesh


@dataclass
class TetMesh:
    """Hacim mesh sonucu."""
    points: np.ndarray   # (N, 3) düğüm koordinatları (m)
    tets: np.ndarray     # (M, 4 veya 10) tet bağlantıları (0-indexed)
    surface_tris: np.ndarray  # (K, 3 veya 6) yüzey üçgenleri
    msh_path: Path       # geçici .msh dosyası
    element_type: str = "C3D4"  # CalculiX element tipi: C3D4 (4-node) veya C3D10 (10-node)

    @property
    def num_nodes(self) -> int:
        return len(self.points)

    @property
    def num_tets(self) -> int:
        return len(self.tets)

    def summary(self) -> str:
        return (f"Tet mesh: {self.num_nodes:,} düğüm, "
                f"{self.num_tets:,} tetrahedron, "
                f"{len(self.surface_tris):,} yüzey üçgeni")


def repair_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Watertight olmayan mesh için temel onarım."""
    repaired = mesh.copy()
    # Normal düzelt
    repaired.fix_normals()
    # Yinelenen vertexleri birleştir
    repaired.merge_vertices()
    # Dejenere üçgenleri at
    repaired.update_faces(repaired.nondegenerate_faces())
    repaired.remove_unreferenced_vertices()
    # Küçük delikleri doldur
    try:
        trimesh.repair.fill_holes(repaired)
    except Exception:
        pass
    return repaired


def generate_tet_mesh(
    surface_mesh: trimesh.Trimesh,
    target_size: float = 0.01,
    output_dir: Path | None = None,
    progress_callback=None,
    second_order: bool = True,
) -> TetMesh:
    """STL yüzey mesh'inden tetrahedral hacim mesh üret (gmsh Python API).

    Args:
        surface_mesh: trimesh.Trimesh (kapalı yüzey önerilir; değilse onarılır)
        target_size: Hedef element boyutu (metre). Varsayılan 0.01 = 1 cm.
        output_dir: .msh dosyasının yazılacağı dizin. None ise temp.
        progress_callback: callable(percent: int, message: str)

    Returns:
        TetMesh

    Raises:
        RuntimeError: gmsh hata verirse veya hacim üretilemezse
    """
    def _progress(p, m):
        if progress_callback:
            progress_callback(p, m)

    _progress(5, "Mesh onarımı...")
    repaired = repair_mesh(surface_mesh)

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="bilsem_tetmesh_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    stl_path = output_dir / "input.stl"
    msh_path = output_dir / "volume.msh"

    _progress(10, "STL diske yazılıyor...")
    repaired.export(str(stl_path))

    _progress(20, "Gmsh hacim mesh üretiyor...")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", target_size * 0.5)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", target_size)
        gmsh.option.setNumber("Mesh.Algorithm", 6)    # Frontal-Delaunay 2D
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay 3D
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        if second_order:
            gmsh.option.setNumber("Mesh.ElementOrder", 2)
            gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)

        # STL'i yükle (yüzey ağı olarak)
        gmsh.merge(str(stl_path))

        # STL üçgenlerini geometri olarak sınıflandır
        # angle: yüzeyleri bölmek için dihedral açı (radyan). 40° iyi bir varsayılan.
        angle_rad = 40.0 * math.pi / 180.0
        gmsh.model.mesh.classifySurfaces(angle_rad, True, True, math.pi)
        gmsh.model.mesh.createGeometry()

        # Tüm yüzeylerden tek surface loop ve volume oluştur
        surfaces = gmsh.model.getEntities(2)
        if not surfaces:
            raise RuntimeError("Gmsh STL'den yüzey çıkartamadı")

        surface_tags = [s[1] for s in surfaces]
        loop_tag = gmsh.model.geo.addSurfaceLoop(surface_tags)
        gmsh.model.geo.addVolume([loop_tag])
        gmsh.model.geo.synchronize()

        _progress(40, f"Hacim oluşturuldu ({len(surface_tags)} yüzey), 3D mesh...")
        gmsh.model.mesh.generate(3)

        _progress(80, "MSH yazılıyor...")
        gmsh.write(str(msh_path))
    except Exception as e:
        gmsh.finalize()
        raise RuntimeError(f"Gmsh tet mesh üretimi başarısız: {e}") from e
    finally:
        try:
            gmsh.finalize()
        except Exception:
            pass

    if not msh_path.exists():
        raise RuntimeError(f"Gmsh çıktı dosyası üretmedi: {msh_path}")

    _progress(90, "Mesh dosyası okunuyor...")
    m = meshio.read(str(msh_path))

    # tetrahedron ve üçgen bloklarını al (linear: tetra/triangle, quadratic: tetra10/triangle6)
    tet_type_priority = ("tetra10", "tetra")
    tri_type_priority = ("triangle6", "triangle")

    tet_block = None
    tri_block = None
    for cell_block in m.cells:
        if cell_block.type in tet_type_priority and tet_block is None:
            tet_block = cell_block
        elif cell_block.type in tet_type_priority:  # noqa: SIM102 — deprecated, mantik korunuyor
            # 2. ordan tet1 varsa 2. order tercih
            if cell_block.type == "tetra10":
                tet_block = cell_block
        if cell_block.type in tri_type_priority and tri_block is None or cell_block.type == "triangle6":
            tri_block = cell_block

    if tet_block is None or len(tet_block.data) == 0:
        raise RuntimeError(
            "Gmsh hacim mesh üretemedi (tetrahedron bulunamadı). "
            "Yüzey mesh kapalı (watertight) değil olabilir."
        )

    points = m.points.astype(np.float64)
    tets = tet_block.data.astype(np.int64)
    tris = tri_block.data.astype(np.int64) if tri_block is not None else np.zeros((0, 3), dtype=np.int64)

    element_type = "C3D10" if tet_block.type == "tetra10" else "C3D4"

    _progress(95, "Tamamlandı")
    return TetMesh(
        points=points,
        tets=tets,
        surface_tris=tris,
        msh_path=msh_path,
        element_type=element_type,
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Kullanım: python tet_mesher.py <stl> [target_size_m]")
        sys.exit(1)
    target = float(sys.argv[2]) if len(sys.argv) > 2 else 0.01
    surf = trimesh.load(sys.argv[1], force="mesh")
    print(f"Yüzey: {len(surf.faces)} üçgen, watertight={surf.is_watertight}")
    tm = generate_tet_mesh(surf, target_size=target,
                            progress_callback=lambda p, m: print(f"[{p}%] {m}"))
    print(tm.summary())
    print(f"MSH: {tm.msh_path}")
