"""
Advanced Material Database System
Mühendislik malzemelerine ait özellikler ve otomatik hesaplamalar
Kullanıcı tarafından manuel malzeme eklenebilir
"""
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class MaterialType(Enum):
    """Malzeme kategorileri"""
    METAL = "metal"                    # Demir/Çelik
    ALUMINUM = "aluminum"              # Alüminyum alaşımları
    COMPOSITE = "composite"            # Fiber takviyeli plastikler
    CERAMIC = "ceramic"                # Seramik malzemeler
    WOOD = "wood"                      # Ağaç ve deriveleri
    POLYMER = "polymer"                # Plastik/Reçine
    OTHER = "other"

class ApplicationField(Enum):
    """Uygulama alanları"""
    AEROSPACE = "aerospace"            # Hava/Uzay
    AUTOMOTIVE = "automotive"          # Otomotiv
    STRUCTURAL = "structural"          # İnşaat/Yapısal
    MARINE = "marine"                  # Gemi/Denizcilik
    CONSUMER = "consumer"              # Tüketici ürünleri
    OTHER = "other"

# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL PROPERTIES CLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MaterialProperties:
    """Malzeme mekanik özellikleri"""

    # ─── TEMEL ÖZELLİKLER (Girdi) ───
    name: str                                   # Malzeme adı
    material_type: MaterialType                 # Malzeme tipi
    density: float                              # Yoğunluk (kg/m³)
    youngs_modulus: float                       # Young modülü (GPa)
    poisson_ratio: float                        # Poisson oranı (0-0.5)
    yield_strength: float                       # Akma mukavemeti (MPa)
    tensile_strength: float                     # Çekme mukavemeti (MPa)
    compressive_strength: float | None = None  # Basma mukavemeti (MPa)

    # ─── TERMAL ÖZELLİKLER ───
    thermal_conductivity: float | None = None # W/(m·K)
    thermal_expansion: float | None = None    # 1/K (×10⁻⁶)
    melting_point: float | None = None        # °C

    # ─── ÇEVRESEL ÖZELLİKLER ───
    cost_per_kg: float | None = None          # USD/kg
    environmental_impact: str | None = None   # Low/Medium/High
    recyclable: bool = False                     # Geri dönüştürülebilir mi?

    # ─── APLIKASYON ───
    typical_applications: list[str] = field(default_factory=list)

    # ─── HESAPLANAN ÖZELLİKLER ───
    shear_modulus: float = field(init=False)    # G = E / (2(1+ν))
    bulk_modulus: float = field(init=False)     # K = E / (3(1-2ν))
    lame_constant: float = field(init=False)    # λ = E·ν / ((1+ν)(1-2ν))
    safety_factor: float = field(init=False)    # σ_y / σ_tensile
    strength_to_weight: float = field(init=False) # (σ_y) / ρ
    stiffness_to_weight: float = field(init=False) # E / ρ

    def __post_init__(self):
        """Kütüphaneler oluşturulduktan sonra otomatik hesaplamalar"""
        self._calculate_derived_properties()
        self._validate()

    def _calculate_derived_properties(self):
        """Türetilmiş özellikleri hesapla"""
        # Young modülü GPa → Pa'ya çevir (hesaplamalar için)
        E = self.youngs_modulus * 1e9  # Pa
        nu = self.poisson_ratio

        # Shear Modulus: G = E / (2(1+ν))
        self.shear_modulus = E / (2 * (1 + nu)) / 1e9  # GPa'ya geri çevir

        # Bulk Modulus: K = E / (3(1-2ν))
        if abs(1 - 2*nu) > 1e-10:  # Sayısal hata kontrol
            self.bulk_modulus = E / (3 * (1 - 2*nu)) / 1e9
        else:
            self.bulk_modulus = 0

        # Lamé Constant: λ = E·ν / ((1+ν)(1-2ν))
        denom = (1 + nu) * (1 - 2*nu)
        if abs(denom) > 1e-10:
            self.lame_constant = (E * nu) / denom / 1e9
        else:
            self.lame_constant = 0

        # Safety Factor: Akma/Çekme oranı
        if self.tensile_strength > 0:
            self.safety_factor = self.yield_strength / self.tensile_strength
        else:
            self.safety_factor = 1.0

        # Strength-to-Weight: σ_y / ρ (MPa / (kg/m³) = m²/s²)
        if self.density > 0:
            self.strength_to_weight = (self.yield_strength * 1e6) / self.density  # Pa / (kg/m³)
            self.stiffness_to_weight = (self.youngs_modulus * 1e9) / self.density
        else:
            self.strength_to_weight = 0
            self.stiffness_to_weight = 0

    def _validate(self):
        """Malzeme özelliklerini doğrula"""
        errors = []

        if self.youngs_modulus <= 0:
            errors.append("Young modülü > 0 olmalı")

        if not (0 <= self.poisson_ratio <= 0.5):
            errors.append("Poisson oranı 0-0.5 arasında olmalı")

        if self.yield_strength <= 0:
            errors.append("Akma mukavemeti > 0 olmalı")

        if self.tensile_strength <= 0:
            errors.append("Çekme mukavemeti > 0 olmalı")

        if self.density <= 0:
            errors.append("Yoğunluk > 0 olmalı")

        if self.compressive_strength and self.compressive_strength <= 0:
            errors.append("Basma mukavemeti > 0 olmalı")

        if errors:
            raise ValueError("Material property validation failed:\n" + "\n".join(errors))

    def to_dict(self) -> dict:
        """Dict'e çevir (JSON kaydetme için) - calculated fields exclude"""
        # Sadece init parameters'ı kaydet (calculated fields hariç)
        init_fields = [
            'name', 'material_type', 'density', 'youngs_modulus', 'poisson_ratio',
            'yield_strength', 'tensile_strength', 'compressive_strength',
            'thermal_conductivity', 'thermal_expansion', 'melting_point',
            'cost_per_kg', 'environmental_impact', 'recyclable', 'typical_applications'
        ]
        d = {field: getattr(self, field) for field in init_fields}
        d['material_type'] = self.material_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> 'MaterialProperties':
        """Dict'ten oluştur (JSON yükleme için)"""
        data = data.copy()
        data['material_type'] = MaterialType(data['material_type'])
        return MaterialProperties(**data)

    def __str__(self) -> str:
        """İnsan tarafından okunabilir format"""
        return f"""{self.name}
  Type: {self.material_type.value}

  Mekanik Özellikler:
    • E (Young Modulus): {self.youngs_modulus:.1f} GPa
    • G (Shear Modulus): {self.shear_modulus:.1f} GPa
    • K (Bulk Modulus): {self.bulk_modulus:.1f} GPa
    • ν (Poisson's Ratio): {self.poisson_ratio:.3f}
    • σ_y (Yield): {self.yield_strength:.1f} MPa
    • σ_max (Tensile): {self.tensile_strength:.1f} MPa
    • ρ (Density): {self.density:.1f} kg/m³

  Türetilmiş Özellikler:
    • Strength-to-Weight: {self.strength_to_weight/1e6:.2f} m/s²
    • Stiffness-to-Weight: {self.stiffness_to_weight/1e6:.2f} m/s²
    • Safety Factor: {self.safety_factor:.3f}
"""

# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL LIBRARY
# ─────────────────────────────────────────────────────────────────────────────

class MaterialLibrary:
    """Malzeme kütüphanesi — okuma/yazma/yönetim"""

    def __init__(self, db_file: Path | None = None):
        self.db_file = db_file or Path(__file__).parent / "materials.json"
        self.materials: dict[str, MaterialProperties] = {}
        self._load_or_create_database()

    def _load_or_create_database(self):
        """Veritabanını yükle veya oluştur"""
        if self.db_file.exists():
            self.load_from_file()
        else:
            self._create_default_materials()
            self.save_to_file()

    def _create_default_materials(self):
        """Varsayılan malzeme kütüphanesi"""
        defaults = [
            # Alüminyum alaşımları
            MaterialProperties(
                name="Aluminum 6061",
                material_type=MaterialType.ALUMINUM,
                density=2700,
                youngs_modulus=69,
                poisson_ratio=0.33,
                yield_strength=275,
                tensile_strength=310,
                thermal_conductivity=167,
                thermal_expansion=23.6e-6,
                melting_point=660,
                cost_per_kg=2.5,
                typical_applications=["Aerospace", "Automotive", "Structural"]
            ),
            MaterialProperties(
                name="Aluminum 7075",
                material_type=MaterialType.ALUMINUM,
                density=2810,
                youngs_modulus=72,
                poisson_ratio=0.33,
                yield_strength=505,
                tensile_strength=570,
                thermal_conductivity=130,
                thermal_expansion=23.4e-6,
                melting_point=477,
                cost_per_kg=4.0,
                typical_applications=["Aerospace", "High-strength"]
            ),

            # Çelik
            MaterialProperties(
                name="Steel S355",
                material_type=MaterialType.METAL,
                density=7850,
                youngs_modulus=210,
                poisson_ratio=0.30,
                yield_strength=355,
                tensile_strength=510,
                thermal_conductivity=50,
                thermal_expansion=12e-6,
                melting_point=1500,
                cost_per_kg=1.2,
                typical_applications=["Structural", "Automotive"]
            ),
            MaterialProperties(
                name="Steel Stainless 316",
                material_type=MaterialType.METAL,
                density=8000,
                youngs_modulus=193,
                poisson_ratio=0.30,
                yield_strength=310,
                tensile_strength=515,
                thermal_conductivity=16,
                thermal_expansion=16e-6,
                melting_point=1370,
                cost_per_kg=8.0,
                typical_applications=["Marine", "Corrosion-resistant"]
            ),

            # Karbon fiber
            MaterialProperties(
                name="Carbon Fiber (Epoxy)",
                material_type=MaterialType.COMPOSITE,
                density=1600,
                youngs_modulus=150,
                poisson_ratio=0.35,
                yield_strength=1200,
                tensile_strength=1300,
                thermal_conductivity=5,
                thermal_expansion=0.02e-6,
                melting_point=300,
                cost_per_kg=15.0,
                typical_applications=["Aerospace", "High-performance"]
            ),

            # Titanyum
            MaterialProperties(
                name="Titanium Grade 5 (Ti-6Al-4V)",
                material_type=MaterialType.METAL,
                density=4506,
                youngs_modulus=103,
                poisson_ratio=0.342,
                yield_strength=880,
                tensile_strength=950,
                thermal_conductivity=7.4,
                thermal_expansion=8.6e-6,
                melting_point=1660,
                cost_per_kg=12.0,
                typical_applications=["Aerospace", "Medical"]
            ),

            # Balsa
            MaterialProperties(
                name="Balsa Wood",
                material_type=MaterialType.WOOD,
                density=150,
                youngs_modulus=4.5,
                poisson_ratio=0.40,
                yield_strength=30,
                tensile_strength=35,
                thermal_conductivity=0.05,
                thermal_expansion=8e-6,
                melting_point=200,
                cost_per_kg=5.0,
                typical_applications=["Model aircraft", "Lightweight"]
            ),

            # Glass Fiber
            MaterialProperties(
                name="Glass Fiber (Epoxy)",
                material_type=MaterialType.COMPOSITE,
                density=1900,
                youngs_modulus=45,
                poisson_ratio=0.30,
                yield_strength=500,
                tensile_strength=600,
                thermal_conductivity=0.25,
                thermal_expansion=20e-6,
                melting_point=250,
                cost_per_kg=3.0,
                typical_applications=["Marine", "Automotive"]
            ),

            # Magnesium
            MaterialProperties(
                name="Magnesium AZ91D",
                material_type=MaterialType.METAL,
                density=1810,
                youngs_modulus=45,
                poisson_ratio=0.35,
                yield_strength=160,
                tensile_strength=230,
                thermal_conductivity=73,
                thermal_expansion=26e-6,
                melting_point=595,
                cost_per_kg=5.0,
                typical_applications=["Aerospace", "Lightweight"]
            ),

            # Kevlar
            MaterialProperties(
                name="Kevlar (Aramid Fiber)",
                material_type=MaterialType.COMPOSITE,
                density=1450,
                youngs_modulus=130,
                poisson_ratio=0.35,
                yield_strength=3600,
                tensile_strength=3800,
                thermal_conductivity=0.04,
                thermal_expansion=-2e-6,
                melting_point=400,
                cost_per_kg=20.0,
                typical_applications=["Ballistic", "Aerospace"]
            ),
        ]

        for mat in defaults:
            self.materials[mat.name] = mat

    def add_material(self, material: MaterialProperties):
        """Yeni malzeme ekle"""
        self.materials[material.name] = material
        print(f"[OK] Malzeme eklendi: {material.name}")

    def remove_material(self, name: str):
        """Malzeme sil"""
        if name in self.materials:
            del self.materials[name]
            print(f"[OK] Malzeme silindi: {name}")
        else:
            raise KeyError(f"Malzeme bulunamadı: {name}")

    def get_material(self, name: str) -> MaterialProperties:
        """Malzeme getir"""
        if name not in self.materials:
            raise KeyError(f"Malzeme bulunamadı: {name}")
        return self.materials[name]

    def list_materials(self) -> list[str]:
        """Tüm malzemeleri listele"""
        return sorted(self.materials.keys())

    def search_by_type(self, material_type: MaterialType) -> list[str]:
        """Türe göre ara"""
        return [name for name, mat in self.materials.items()
                if mat.material_type == material_type]

    def search_by_property(self, property_name: str, min_val: float, max_val: float) -> list[str]:
        """Özelliğe göre ara (örn: Young modülü 50-100 GPa)"""
        results = []
        for name, mat in self.materials.items():
            if hasattr(mat, property_name):
                val = getattr(mat, property_name)
                if min_val <= val <= max_val:
                    results.append(name)
        return results

    def save_to_file(self):
        """JSON dosyasına kaydet"""
        data = {name: mat.to_dict() for name, mat in self.materials.items()}
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[OK] Database saved: {self.db_file}")

    def load_from_file(self):
        """JSON dosyasından yükle"""
        with open(self.db_file, encoding='utf-8') as f:
            data = json.load(f)
        self.materials = {name: MaterialProperties.from_dict(props)
                         for name, props in data.items()}
        print(f"[OK] Database loaded: {len(self.materials)} materials")

    def export_csv(self, output_file: Path):
        """CSV'ye dışa aktar"""
        import csv
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['name', 'type', 'density', 'youngs_modulus', 'yield_strength',
                         'tensile_strength', 'poisson_ratio', 'thermal_conductivity',
                         'strength_to_weight', 'stiffness_to_weight', 'cost_per_kg']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for name, mat in self.materials.items():
                row = {
                    'name': mat.name,
                    'type': mat.material_type.value,
                    'density': mat.density,
                    'youngs_modulus': mat.youngs_modulus,
                    'yield_strength': mat.yield_strength,
                    'tensile_strength': mat.tensile_strength,
                    'poisson_ratio': mat.poisson_ratio,
                    'thermal_conductivity': mat.thermal_conductivity or '',
                    'strength_to_weight': mat.strength_to_weight,
                    'stiffness_to_weight': mat.stiffness_to_weight,
                    'cost_per_kg': mat.cost_per_kg or ''
                }
                writer.writerow(row)
        print(f"[OK] CSV disari aktarildi: {output_file}")

    def __repr__(self) -> str:
        return f"MaterialLibrary({len(self.materials)} materials)"

# ─────────────────────────────────────────────────────────────────────────────
# SINGLETON INSTANCE
# ─────────────────────────────────────────────────────────────────────────────

# Global kütüphane instance
MATERIAL_LIBRARY = MaterialLibrary()

if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    # Test
    print("=" * 70)
    print("MATERIAL LIBRARY TEST")
    print("=" * 70)

    # List all
    print("\nMalzemeler:")
    for name in MATERIAL_LIBRARY.list_materials():
        print(f"  • {name}")

    # Get one
    print("\n" + "=" * 70)
    mat = MATERIAL_LIBRARY.get_material("Aluminum 6061")
    print(mat)

    # Search
    print("=" * 70)
    print("Aramalar:")
    print("  Young modülü 100-200 GPa:")
    for name in MATERIAL_LIBRARY.search_by_property("youngs_modulus", 100, 200):
        print(f"    • {name}")

    # Export
    print("\n" + "=" * 70)
    MATERIAL_LIBRARY.export_csv(Path(__file__).parent / "materials.csv")
