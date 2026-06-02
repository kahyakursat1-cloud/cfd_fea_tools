"""
Scanned Mesh → Aircraft Geometry Converter
STL mesh'ten otomatik olarak Aircraft parametreleri çıkarma
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict
import struct


class MeshAnalyzer:
    """STL mesh'i analiz et ve parametreleri çıkar"""

    def __init__(self, stl_file: str):
        self.stl_file = Path(stl_file)
        self.vertices = []
        self.triangles = []
        self.load_stl()

    def load_stl(self):
        """STL dosyasını yükle (ASCII ve Binary support)"""
        if not self.stl_file.exists():
            raise FileNotFoundError(f"STL file not found: {self.stl_file}")

        # Binary STL denemesi
        try:
            with open(self.stl_file, 'rb') as f:
                # Header (80 bytes)
                header = f.read(80)

                # Üçgen sayısı
                num_triangles = struct.unpack('I', f.read(4))[0]

                vertices_set = set()
                triangles = []

                for _ in range(num_triangles):
                    # Normal vector
                    nx, ny, nz = struct.unpack('fff', f.read(12))

                    # 3 Vertex
                    v1 = struct.unpack('fff', f.read(12))
                    v2 = struct.unpack('fff', f.read(12))
                    v3 = struct.unpack('fff', f.read(12))

                    # Attribute byte count
                    f.read(2)

                    # Vertices ekle
                    if v1 not in vertices_set:
                        self.vertices.append(v1)
                        vertices_set.add(v1)
                    if v2 not in vertices_set:
                        self.vertices.append(v2)
                        vertices_set.add(v2)
                    if v3 not in vertices_set:
                        self.vertices.append(v3)
                        vertices_set.add(v3)

                    # Triangle (vertex indices)
                    idx1 = self.vertices.index(v1)
                    idx2 = self.vertices.index(v2)
                    idx3 = self.vertices.index(v3)

                    triangles.append((idx1, idx2, idx3))

                self.triangles = triangles

        except (struct.error, ValueError):
            # ASCII STL fallback
            self._load_ascii_stl()

    def _load_ascii_stl(self):
        """ASCII STL yükle"""
        vertices_set = set()

        with open(self.stl_file, 'r') as f:
            for line in f:
                line = line.strip()

                if line.startswith('vertex'):
                    coords = tuple(map(float, line.split()[1:]))
                    if coords not in vertices_set:
                        self.vertices.append(coords)
                        vertices_set.add(coords)

    def get_bounding_box(self) -> Tuple[np.ndarray, np.ndarray]:
        """Mesh sınırlarını al"""
        if not self.vertices:
            return np.array([0, 0, 0]), np.array([1, 1, 1])

        vertices_array = np.array(self.vertices)
        min_point = vertices_array.min(axis=0)
        max_point = vertices_array.max(axis=0)

        return min_point, max_point

    def get_dimensions(self) -> Dict[str, float]:
        """Mesh boyutlarını al"""
        min_point, max_point = self.get_bounding_box()

        length = float(max_point[0] - min_point[0])  # X (ileri-geri)
        width = float(max_point[1] - min_point[1])   # Y (kanat genişliği)
        height = float(max_point[2] - min_point[2])  # Z (yükseklik)

        return {
            "length": length,
            "width": width,
            "height": height,
            "volume": length * width * height
        }

    def get_aspect_ratio(self) -> float:
        """En boy oranını hesapla"""
        dims = self.get_dimensions()
        if dims["height"] == 0:
            return 1.0
        return dims["width"] / dims["height"]

    def estimate_aircraft_type(self) -> str:
        """Mesh şeklinden aircraft tipini tahmin et"""
        dims = self.get_dimensions()
        length = dims["length"]
        width = dims["width"]
        height = dims["height"]

        # Length-to-width oranı
        length_width_ratio = length / width if width > 0 else 1.0

        # Aspect Ratio (kanat genişliği / yükseklik)
        aspect_ratio = self.get_aspect_ratio()

        # Sınıflandırma
        if aspect_ratio > 5 and length_width_ratio < 2:
            return "HAPS"  # Yüksek aspect ratio → uzun kanatlar
        elif length_width_ratio > 3 and height < width * 0.3:
            return "FLYING_WING"  # Deltaüçgen şekli
        elif aspect_ratio > 3 and length_width_ratio > 2:
            return "GLIDER"  # Uzun dar vücut
        elif height > width * 0.4 and length_width_ratio > 1.5:
            return "VTOL"  # Dikey şekil
        elif length_width_ratio < 1.2:
            return "HELICOPTER"  # Kare şekli
        else:
            return "FIXED_WING"  # Standart sabit kanat

    def estimate_mass(self, material_density: float = 2700) -> float:
        """Mesh hacminden kütleyi tahmin et (malzeme yoğunluğu varsayılarak)"""
        dims = self.get_dimensions()
        # Basitleştirilmiş volume hesaplaması (mesh hacmi ≈ bounding box hacmi * fill factor)
        fill_factor = 0.4  # Ortalama doluluk
        volume = dims["volume"] * fill_factor

        # Kütle = Hacim × Yoğunluk
        mass_kg = (volume * material_density) / 1e9  # mm³ → m³

        return mass_kg

    def get_mesh_statistics(self) -> Dict:
        """Mesh istatistiklerini döndür"""
        min_point, max_point = self.get_bounding_box()

        return {
            "num_vertices": len(self.vertices),
            "num_triangles": len(self.triangles),
            "bounding_box_min": min_point.tolist(),
            "bounding_box_max": max_point.tolist(),
            "dimensions": self.get_dimensions(),
            "aspect_ratio": self.get_aspect_ratio(),
            "estimated_type": self.estimate_aircraft_type(),
            "estimated_mass_kg": self.estimate_mass()
        }


# ─────────────────────────────────────────────────────────────────────────────
# MESH → AIRCRAFT CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

def convert_mesh_to_aircraft(stl_file: str, aircraft_name: str = "Scanned_Aircraft"):
    """
    STL mesh'ten Aircraft geometrisi oluştur

    Returns: Aircraft instance (aircraft_geometry.py'den)
    """
    from aircraft_geometry import Aircraft, Wing, Fuselage, Empennage, AirfoilProfile

    analyzer = MeshAnalyzer(stl_file)
    stats = analyzer.get_mesh_statistics()

    dims = stats["dimensions"]
    aspect_ratio = stats["aspect_ratio"]
    estimated_type = stats["estimated_type"]
    mass_kg = stats["estimated_mass_kg"]

    # Mesh boyutlarından aircraft parametreleri çıkar
    fuselage_length = dims["length"]
    fuselage_diameter = dims["height"]

    wing_span = dims["width"]
    wing_chord = dims["length"] * 0.3  # Tahmini ortalama chord
    wing_area = wing_span * wing_chord

    # Wing geometrisi oluştur (aircraft_geometry.py dataclass imzasına uygun)
    wing = Wing(
        airfoil=AirfoilProfile("NACA2412", chord=wing_chord, thickness_ratio=12, camber=2),
        span=wing_span,
        area=wing_area,
        aspect_ratio=wing_span**2 / wing_area if wing_area > 0 else 1.0,
        taper_ratio=0.7,
        sweep_angle=0.0,
        dihedral=2.0,
        incidence=0.0
    )

    # Fuselage oluştur
    fuselage = Fuselage(
        diameter=fuselage_diameter,
        length=fuselage_length,
        nose_type="cone",
        nose_length=fuselage_length * 0.15,
        fineness_ratio=fuselage_length / fuselage_diameter if fuselage_diameter > 0 else 10
    )

    # Empennage (tail) oluştur
    empennage = Empennage(
        horizontal_airfoil=AirfoilProfile("NACA0009", chord=wing_chord * 0.4, thickness_ratio=9, camber=0),
        vertical_airfoil=AirfoilProfile("NACA0009", chord=wing_chord * 0.4, thickness_ratio=9, camber=0),
        h_area=wing_area * 0.15,
        v_area=wing_area * 0.10,
        h_distance=fuselage_length * 0.8,
        v_distance=fuselage_diameter * 0.4
    )

    # Aircraft oluştur
    aircraft = Aircraft(
        name=aircraft_name,
        aircraft_type=estimated_type.lower(),
        wing=wing,
        fuselage=fuselage,
        empennage=empennage,
    )

    return aircraft, stats


def batch_convert_meshes(mesh_folder: str) -> list:
    """Klasördeki tüm STL dosyalarını dönüştür"""
    mesh_folder = Path(mesh_folder)
    aircraft_list = []

    for stl_file in mesh_folder.glob("*.stl"):
        try:
            aircraft, stats = convert_mesh_to_aircraft(str(stl_file), stl_file.stem)
            aircraft_list.append({
                "aircraft": aircraft,
                "statistics": stats,
                "source_file": str(stl_file)
            })
            print(f"✅ Converted: {stl_file.name} → {stats['estimated_type']}")
        except Exception as e:
            print(f"❌ Failed to convert {stl_file.name}: {str(e)}")

    return aircraft_list
