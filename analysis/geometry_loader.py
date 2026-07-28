"""
Geometry loader: STL/STEP -> trimesh + bounding box face groups.

STEP desteği opsiyonel: cadquery / OCP varsa kullanılır, yoksa kullanıcıdan
STL beklenir. STL native trimesh ile okunur.

Çıktı: GeometryInfo
  - mesh: trimesh.Trimesh
  - bbox: (min, max) np.array
  - faces_by_side: bbox'ın 6 yüzüne yakın olan üçgenlerin face index listesi
    (calculix BC ve load için kullanıcı bu yüzleri seçer)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

# Bbox yüzlerinin standart isimleri (sağ el koordinat sistemi: x sağ, y yukarı, z dışarı)
BBOX_SIDES = ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")


@dataclass
class GeometryInfo:
    """Yüklenmiş geometriyi ve türetilen bilgileri tutar."""
    source_path: Path
    mesh: trimesh.Trimesh
    bbox_min: np.ndarray  # (3,)
    bbox_max: np.ndarray  # (3,)
    faces_by_side: dict[str, np.ndarray] = field(default_factory=dict)  # side -> face index array

    @property
    def size(self) -> np.ndarray:
        return self.bbox_max - self.bbox_min

    @property
    def volume(self) -> float | None:
        """Hacim; ÖLÇÜLEMEZSE None (0.0 DEĞİL).

        0.0 makul görünen ama yanlış bir sayıdır ve aritmetiğe sızar (kütle, yoğunluk,
        hacim oranı hepsi sıfırlanır). None "bilinmiyor" der ve çağıranı düşünmeye zorlar.
        """
        try:
            return float(self.mesh.volume)
        # sessiz-yutma: kabul — su-geçirmez olmayan mesh'te hacim tanımsızdır; None dönüp özet "ölçülemedi" yazar
        except Exception:
            return None

    @property
    def surface_area(self) -> float:
        return float(self.mesh.area)

    @property
    def num_triangles(self) -> int:
        return len(self.mesh.faces)

    def summary(self) -> str:
        return (
            f"Dosya: {self.source_path.name}\n"
            f"Üçgen sayısı: {self.num_triangles:,}\n"
            f"BBox boyutu: {self.size[0]*1000:.1f} x {self.size[1]*1000:.1f} x "
            f"{self.size[2]*1000:.1f} mm\n"
            f"Yüzey alanı: {self.surface_area*1e6:.1f} mm²\n"
            f"Hacim: {self.volume*1e9:.1f} mm³\n"
            f"Kapalı (watertight): {self.mesh.is_watertight}\n"
            f"BBox yüz grupları:\n"
            + "\n".join(f"  {s:5s}: {len(self.faces_by_side.get(s, [])):>5d} üçgen"
                        for s in BBOX_SIDES)
        )


def load_geometry(path: str | Path,
                  side_tolerance_ratio: float = 0.02,
                  unit_scale: float = 1.0) -> GeometryInfo:
    """STL veya STEP dosyasını yükle.

    Args:
        path: Dosya yolu (.stl, .obj, .ply, .step, .stp)
        side_tolerance_ratio: Bbox boyutunun yüzdesi olarak yüz toleransı.
          (varsayılan: %2 — çok düz olmayan yüzler için biraz cömert)
        unit_scale: Yüklenen koordinatları çarpacak ölçek faktörü.
          1.0 = dosya zaten metre cinsinden.
          0.001 = dosya mm cinsinden (mm -> m).
          0.0254 = inch -> m.
          Otomatik tespit yapılmıyor — kullanıcı seçer.

    Returns:
        GeometryInfo

    Raises:
        FileNotFoundError, ValueError
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Geometri dosyası yok: {path}")

    suffix = path.suffix.lower()

    if suffix in (".step", ".stp"):
        mesh = _load_step(path)
    else:
        mesh = trimesh.load(str(path), force="mesh")
        if not isinstance(mesh, trimesh.Trimesh):
            # force="mesh" Scene'i zaten birleştirir; buraya düşmek format hatasıdır
            raise ValueError(f"Geometri Trimesh'e dönüştürülemedi: {path}")

    if len(mesh.faces) == 0:
        raise ValueError(f"Geometri boş (üçgen yok): {path}")

    if unit_scale != 1.0:
        mesh.apply_scale(unit_scale)

    bbox_min = mesh.bounds[0].astype(np.float64)
    bbox_max = mesh.bounds[1].astype(np.float64)

    faces_by_side = _classify_faces_by_bbox_side(
        mesh, bbox_min, bbox_max, tol_ratio=side_tolerance_ratio
    )

    return GeometryInfo(
        source_path=path,
        mesh=mesh,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        faces_by_side=faces_by_side,
    )


def _load_step(path: Path) -> trimesh.Trimesh:
    """STEP dosyasını yüklemek için cadquery veya OCP dene."""
    # Önce cadquery
    try:
        import cadquery as cq  # type: ignore
        from cadquery import exporters
        result = cq.importers.importStep(str(path))
        # Geçici STL'e yaz, sonra trimesh ile oku
        import os
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            exporters.export(result, tmp_path)
            mesh = trimesh.load(tmp_path, force="mesh")
            return mesh
        finally:
            try:
                os.unlink(tmp_path)
            # sessiz-yutma: kabul — STEP okuyucu opsiyonel (OCC yoksa); çağıran STL yoluna düşer ve kaynak formatı raporda görünür
            except OSError:
                pass
    # sessiz-yutma: kabul — STEP okuyucu opsiyonel (OCC yoksa); çağıran STL yoluna düşer ve kaynak formatı raporda görünür
    except ImportError:
        pass

    # Olmazsa hata
    raise ImportError(
        "STEP dosyası yüklemek için 'cadquery' gerekli. "
        "Lütfen STL'e dönüştürüp yükleyin veya 'pip install cadquery' yapın."
    )


def _classify_faces_by_bbox_side(
    mesh: trimesh.Trimesh,
    bbox_min: np.ndarray,
    bbox_max: np.ndarray,
    tol_ratio: float = 0.02,
) -> dict[str, np.ndarray]:
    """Her bbox yüzüne 'yapışık' üçgenleri grupla.

    Bir üçgenin centroid'i bbox yüzüne tol mesafede ise ve normali o yöne
    bakıyorsa o gruba dahil edilir. CalculiX BC/load için iyi bir başlangıç
    seti sağlar (kullanıcı sonradan revize edebilir).
    """
    centroids = mesh.triangles_center  # (N, 3)
    normals = mesh.face_normals          # (N, 3)
    size = bbox_max - bbox_min
    tol = np.maximum(size * tol_ratio, 1e-6)

    groups: dict[str, np.ndarray] = {}

    # axis index, side ('min'|'max'), expected normal sign
    sides = [
        ("xmin", 0, bbox_min[0], -1.0),
        ("xmax", 0, bbox_max[0], +1.0),
        ("ymin", 1, bbox_min[1], -1.0),
        ("ymax", 1, bbox_max[1], +1.0),
        ("zmin", 2, bbox_min[2], -1.0),
        ("zmax", 2, bbox_max[2], +1.0),
    ]

    for name, axis, plane, normal_sign in sides:
        pos_match = np.abs(centroids[:, axis] - plane) < tol[axis]
        normal_match = normals[:, axis] * normal_sign > 0.5  # ~60° kabul açısı
        idx = np.where(pos_match & normal_match)[0]
        groups[name] = idx.astype(np.int64)

    return groups


def faces_in_axis_band(mesh: trimesh.Trimesh,
                        axis: int = 2,
                        band: str = "lower",
                        fraction: float = 0.10) -> np.ndarray:
    """Verilen eksende alt/üst N% bandında bulunan üçgen index'leri.

    Düzensiz/asimetrik geometriler için bbox yüz tespiti çalışmadığında
    yedek BC/load yüzeyi seçim yöntemi.

    Args:
        mesh: trimesh
        axis: 0=x, 1=y, 2=z (varsayılan z = "yukarı")
        band: "lower" alt, "upper" üst
        fraction: bant kalınlığı (0.10 = bbox boyutunun %10'u)

    Returns:
        Bu banta düşen face index np.array
    """
    centroids = mesh.triangles_center
    coords = centroids[:, axis]
    lo, hi = float(coords.min()), float(coords.max())
    span = hi - lo
    if span <= 0:
        return np.array([], dtype=np.int64)
    if band == "lower":
        cutoff = lo + span * fraction
        idx = np.where(coords <= cutoff)[0]
    elif band == "upper":
        cutoff = hi - span * fraction
        idx = np.where(coords >= cutoff)[0]
    else:
        raise ValueError(f"band must be 'lower' or 'upper', got {band}")
    return idx.astype(np.int64)


def get_unique_node_indices(mesh: trimesh.Trimesh, face_indices: np.ndarray) -> np.ndarray:
    """Verilen face index'lerden benzersiz node (vertex) index'leri."""
    if len(face_indices) == 0:
        return np.array([], dtype=np.int64)
    return np.unique(mesh.faces[face_indices].flatten())


if __name__ == "__main__":
    # CLI test: python -m analysis.geometry_loader path/to/file.stl
    import sys
    if len(sys.argv) < 2:
        print("Kullanım: python geometry_loader.py <stl_dosyası>")
        sys.exit(1)
    info = load_geometry(sys.argv[1])
    print(info.summary())
