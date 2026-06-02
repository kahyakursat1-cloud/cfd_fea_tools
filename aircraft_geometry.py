"""
Aircraft/Rocket Geometry Generator
Parametrik kanat, gövde, kuyruk tasarımı
STEP export + mesh yönetimi
"""

import json
from dataclasses import dataclass

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# AIRCRAFT GEOMETRY CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AirfoilProfile:
    """Kanat profili (NACA vb.)"""
    name: str                    # "NACA2412", "Clark Y", etc.
    chord: float                 # Kord uzunluğu (m)
    thickness_ratio: float       # Kalınlık oranı (%)
    camber: float               # Eğrilik (%)

    def generate_coordinates(self, num_points: int = 100) -> np.ndarray:
        """NACA profil koordinatları oluştur"""
        x = np.linspace(0, 1, num_points)

        # NACA4 series (basitleştirilmiş)
        m = self.camber / 100
        p = 0.3  # NACA parametresi
        t = self.thickness_ratio / 100

        # Kalınlık dağılımı
        y_t = (t / 0.2) * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 +
                            0.2843 * x**3 - 0.1015 * x**4)

        # Eğrilik çizgisi
        y_c = np.where(
            x < p,
            (m / p**2) * (2*p*x - x**2),
            (m / (1-p)**2) * ((1 - 2*p) + 2*p*x - x**2)
        )

        # Alt ve üst yüzey
        y_upper = y_c + y_t
        y_lower = y_c - y_t

        return np.column_stack([x * self.chord, y_upper * self.chord])

@dataclass
class Wing:
    """Kanat (sabit kanat)"""
    airfoil: AirfoilProfile
    span: float                  # Kanat açıklığı (m)
    area: float                 # Kanat alanı (m²)
    aspect_ratio: float         # Aspect Ratio (span²/area)
    taper_ratio: float          # Taper ratio (uç/kök)
    sweep_angle: float          # Kanat tarama açısı (derece)
    dihedral: float             # Dihedral açısı (derece)
    incidence: float            # Kanat hücum açısı (derece)

    def root_chord(self) -> float:
        return 2 * self.area / (self.span * (1 + self.taper_ratio))

    def tip_chord(self) -> float:
        return self.root_chord() * self.taper_ratio

@dataclass
class Fuselage:
    """Gövde (silindir + konik başlık)"""
    diameter: float             # Gövde çapı (m)
    length: float              # Gövde uzunluğu (m)
    nose_type: str             # "cone" | "ogive" | "power" | "parabolic"
    nose_length: float         # Başlık uzunluğu (m)
    fineness_ratio: float      # Uzunluk/çap oranı

@dataclass
class Empennage:
    """Kuyruk sistemi (dikey + yatay)"""
    horizontal_airfoil: AirfoilProfile
    vertical_airfoil: AirfoilProfile
    h_area: float              # Yatay kuyruk alanı (m²)
    v_area: float              # Dikey kuyruk alanı (m²)
    h_distance: float          # Yatay konum (gövde sonundan)
    v_distance: float          # Dikey konum (gövde sonundan)

@dataclass
class Aircraft:
    """Tam uçak modeli"""
    name: str
    aircraft_type: str         # "fixed_wing" | "rocket" | "quadrotor" | "vtol"
    wing: Wing
    fuselage: Fuselage
    empennage: Empennage = None
    landing_gear: bool = False
    control_surfaces: dict = None

    def mass_properties(self) -> dict:
        """Kütle özellikleri tahmin et"""
        # Çok basit tahmin (gerçekte CFD/FEA gerekli)
        fuselage_vol = np.pi * (self.fuselage.diameter/2)**2 * self.fuselage.length
        wing_vol = self.wing.area * 0.02  # 2cm ortalama kalınlık

        # Malzeme yoğunluğu (kg/m³)
        fuselage_mass = fuselage_vol * 50  # Composite
        wing_mass = wing_vol * 60
        empennage_mass = (self.empennage.h_area + self.empennage.v_area) * 0.1 if self.empennage else 0
        systems_mass = (fuselage_mass + wing_mass) * 0.2  # Motor, elektronik vb.

        total_mass = fuselage_mass + wing_mass + empennage_mass + systems_mass

        # Merkez kütle (yaklaşık)
        cg_x = self.fuselage.length * 0.35  # 35% gövde uzunluğundan

        return {
            "total_mass": total_mass,
            "fuselage_mass": fuselage_mass,
            "wing_mass": wing_mass,
            "empennage_mass": empennage_mass,
            "systems_mass": systems_mass,
            "cg_x": cg_x,
            "wing_area": self.wing.area,
            "ar": self.wing.aspect_ratio,
        }

    def to_dict(self) -> dict:
        """JSON serileştirme"""
        return {
            "name": self.name,
            "type": self.aircraft_type,
            "wing": {
                "span": self.wing.span,
                "area": self.wing.area,
                "aspect_ratio": self.wing.aspect_ratio,
                "taper": self.wing.taper_ratio,
                "sweep": self.wing.sweep_angle,
            },
            "fuselage": {
                "diameter": self.fuselage.diameter,
                "length": self.fuselage.length,
                "nose_type": self.fuselage.nose_type,
            },
            "mass_properties": self.mass_properties(),
        }

# ─────────────────────────────────────────────────────────────────────────────
# PREDEFINED AIRCRAFT TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

class AircraftLibrary:
    """Hazır uçak tasarımları"""

    @staticmethod
    def minihawk_uav() -> Aircraft:
        """MiniHawk — Küçük İHA"""
        wing = Wing(
            airfoil=AirfoilProfile("NACA2412", chord=0.25, thickness_ratio=12, camber=2),
            span=1.5,
            area=0.45,
            aspect_ratio=5.0,
            taper_ratio=0.7,
            sweep_angle=2,
            dihedral=5,
            incidence=2
        )
        fuselage = Fuselage(
            diameter=0.08,
            length=0.8,
            nose_type="cone",
            nose_length=0.15,
            fineness_ratio=10
        )
        empennage = Empennage(
            horizontal_airfoil=AirfoilProfile("NACA0009", chord=0.12, thickness_ratio=9, camber=0),
            vertical_airfoil=AirfoilProfile("NACA0009", chord=0.12, thickness_ratio=9, camber=0),
            h_area=0.08,
            v_area=0.06,
            h_distance=0.6,
            v_distance=0.05
        )
        return Aircraft(
            name="MiniHawk UAV",
            aircraft_type="fixed_wing",
            wing=wing,
            fuselage=fuselage,
            empennage=empennage,
            landing_gear=False
        )

    @staticmethod
    def model_rocket() -> Aircraft:
        """Model Roket — F-serisi"""
        wing = Wing(
            airfoil=AirfoilProfile("Rocket", chord=0.08, thickness_ratio=6, camber=0),
            span=0.15,
            area=0.012,
            aspect_ratio=1.9,
            taper_ratio=0.6,
            sweep_angle=30,
            dihedral=0,
            incidence=0
        )
        fuselage = Fuselage(
            diameter=0.05,
            length=0.6,
            nose_type="ogive",
            nose_length=0.12,
            fineness_ratio=12
        )
        return Aircraft(
            name="Model Roket F25",
            aircraft_type="rocket",
            wing=wing,
            fuselage=fuselage,
            empennage=None
        )

    @staticmethod
    def fixed_wing_racer() -> Aircraft:
        """Sabit Kanat Yarış Dronu"""
        wing = Wing(
            airfoil=AirfoilProfile("NACA3312", chord=0.35, thickness_ratio=12, camber=3),
            span=2.0,
            area=0.8,
            aspect_ratio=5.0,
            taper_ratio=0.6,
            sweep_angle=8,
            dihedral=3,
            incidence=1
        )
        fuselage = Fuselage(
            diameter=0.12,
            length=1.2,
            nose_type="cone",
            nose_length=0.25,
            fineness_ratio=10
        )
        empennage = Empennage(
            horizontal_airfoil=AirfoilProfile("NACA0012", chord=0.2, thickness_ratio=12, camber=0),
            vertical_airfoil=AirfoilProfile("NACA0012", chord=0.2, thickness_ratio=12, camber=0),
            h_area=0.16,
            v_area=0.12,
            h_distance=1.0,
            v_distance=0.1
        )
        return Aircraft(
            name="Fixed-Wing Racer",
            aircraft_type="fixed_wing",
            wing=wing,
            fuselage=fuselage,
            empennage=empennage,
            landing_gear=True
        )

    @staticmethod
    def vtol_drone() -> Aircraft:
        """VTOL Drone (Hover + Forward Flight)"""
        wing = Wing(
            airfoil=AirfoilProfile("NACA2412", chord=0.3, thickness_ratio=12, camber=2),
            span=1.8,
            area=0.6,
            aspect_ratio=5.4,
            taper_ratio=0.8,
            sweep_angle=5,
            dihedral=8,
            incidence=0
        )
        fuselage = Fuselage(
            diameter=0.15,
            length=1.0,
            nose_type="cone",
            nose_length=0.2,
            fineness_ratio=6.7
        )
        return Aircraft(
            name="VTOL Drone",
            aircraft_type="vtol",
            wing=wing,
            fuselage=fuselage,
            landing_gear=False
        )

    @staticmethod
    def high_altitude_platform() -> Aircraft:
        """Yüksek İrtifa Platformu (HAPS)"""
        wing = Wing(
            airfoil=AirfoilProfile("SD7003", chord=0.5, thickness_ratio=8.5, camber=2),
            span=4.0,
            area=2.5,
            aspect_ratio=6.4,
            taper_ratio=0.5,
            sweep_angle=0,
            dihedral=12,
            incidence=3
        )
        fuselage = Fuselage(
            diameter=0.08,
            length=1.2,
            nose_type="parabolic",
            nose_length=0.3,
            fineness_ratio=15
        )
        return Aircraft(
            name="High Altitude Platform",
            aircraft_type="fixed_wing",
            wing=wing,
            fuselage=fuselage,
            landing_gear=False
        )


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETRIC ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

class ParametricStudy:
    """Parametrik çalışma (Varyasyon analizi)"""

    def __init__(self, base_aircraft: Aircraft):
        self.base = base_aircraft
        self.variations = []

    def add_variation(self, param_name: str, values: list[float]) -> None:
        """Parametreye birden fazla değer ata"""
        self.variations.append({
            "parameter": param_name,
            "values": values
        })

    def generate_cases(self) -> list[Aircraft]:
        """Tüm kombinasyonları oluştur"""
        import itertools

        cases = []
        param_names = [v["parameter"] for v in self.variations]
        param_values = [v["values"] for v in self.variations]

        for combo in itertools.product(*param_values):
            aircraft = self._create_variant(dict(zip(param_names, combo)))
            cases.append(aircraft)

        return cases

    def _create_variant(self, params: dict) -> Aircraft:
        """Parametreye göre varyant oluştur"""
        import copy
        variant = copy.deepcopy(self.base)

        for param, value in params.items():
            if "span" in param:
                variant.wing.span = value
            elif "area" in param:
                variant.wing.area = value
            elif "aspect_ratio" in param:
                variant.wing.aspect_ratio = value
            elif "taper" in param:
                variant.wing.taper_ratio = value
            elif "sweep" in param:
                variant.wing.sweep_angle = value
            elif "fuselage_length" in param:
                variant.fuselage.length = value
            elif "nose_length" in param:
                variant.fuselage.nose_length = value

        return variant


# ─────────────────────────────────────────────────────────────────────────────
# EXAMPLE USAGE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Sabit kanat roket oluştur
    roket = AircraftLibrary.model_rocket()
    print(f"Aircraft: {roket.name}")
    print(f"Type: {roket.aircraft_type}")
    print(json.dumps(roket.to_dict(), indent=2))

    # Parametrik çalışma
    study = ParametricStudy(roket)
    study.add_variation("span", [0.12, 0.15, 0.18])
    study.add_variation("sweep", [20, 30, 40])

    cases = study.generate_cases()
    print(f"\nGenerated {len(cases)} cases for parametric study")

    for i, case in enumerate(cases):
        print(f"Case {i+1}: Span={case.wing.span}m, Sweep={case.wing.sweep_angle}°")
