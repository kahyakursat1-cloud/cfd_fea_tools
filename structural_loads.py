"""
Structural Load Envelope — FAR/CS-23
=====================================
Manevra zarfi (V-n) + gust zarfi (FAR 23.333/335/341).
Kritik yuk durumlarini otomatik uretir; FEA'ya beslenir.

Referans:
  FAR 23.333  Flight envelope
  FAR 23.335  Design airspeeds (Va, Vc, Vd)
  FAR 23.337  Limit maneuvering load factors
  FAR 23.341  Gust load factors
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


# Kategori basina limit yuk faktorleri (FAR 23.337)
CATEGORY_LIMITS = {
    "normal":    {"n_max":  3.8, "n_min": -1.52},  # n_min = -0.4*n_max
    "utility":   {"n_max":  4.4, "n_min": -1.76},
    "aerobatic": {"n_max":  6.0, "n_min": -3.0},
}

# Gust hizlari — FAR 23.333(c) (m/s, EAS)
GUST_VELOCITIES = {
    "Vb": 20.12,   # 66 fps — rough air (kaba hava)
    "Vc": 15.24,   # 50 fps — cruise
    "Vd":  7.62,   # 25 fps — dive
}

RHO0 = 1.225  # deniz seviyesi yogunluk (kg/m3)
G    = 9.81


@dataclass
class FlightEnvelope:
    """Bir ucak icin V-n manevra + gust zarfi."""

    mass_kg:        float          # MTOW
    wing_area_m2:   float          # S
    wing_span_m:    float          # b
    mac_m:          float          # ortalama aerodinamik kord (MAC)
    cl_max:         float          # maksimum kaldirma katsayisi (pozitif)
    cl_min:         float          # minimum (negatif stall, ~ -0.8*cl_max)
    cl_alpha:       float          # kaldirma egri egimi (1/rad)
    v_cruise_ms:    float          # Vc tasarim seyir hizi
    category:       str = "normal"
    rho:            float = RHO0

    # Hesaplanan alanlar
    def __post_init__(self):
        lim = CATEGORY_LIMITS.get(self.category, CATEGORY_LIMITS["normal"])
        self.n_max = lim["n_max"]
        self.n_min = lim["n_min"]
        self.W = self.mass_kg * G                       # agirlik (N)
        self.WS = self.W / self.wing_area_m2            # kanat yuklemesi (Pa)
        self.q_cruise = 0.5 * self.rho * self.v_cruise_ms ** 2

    # ── Hizlar ──────────────────────────────────────────────────────────────
    def v_stall(self, n: float = 1.0, positive: bool = True) -> float:
        """Belirli yuk faktorunde stall hizi (m/s).
        V_s = sqrt( 2*n*W / (rho*S*CL_max) )
        """
        cl = self.cl_max if positive else abs(self.cl_min)
        return math.sqrt(2 * abs(n) * self.W / (self.rho * self.wing_area_m2 * cl))

    @property
    def Vs1(self) -> float:
        """1g stall hizi."""
        return self.v_stall(1.0, positive=True)

    @property
    def Va(self) -> float:
        """Manevra hizi (corner speed): Va = Vs1 * sqrt(n_max)."""
        return self.Vs1 * math.sqrt(self.n_max)

    @property
    def Vc(self) -> float:
        return self.v_cruise_ms

    @property
    def Vd(self) -> float:
        """Dalis hizi (FAR 23.335): Vd >= 1.25*Vc (kucuk ucak icin tipik)."""
        return 1.40 * self.v_cruise_ms

    # ── Manevra zarfi ───────────────────────────────────────────────────────
    def maneuver_envelope(self, n_pts: int = 40) -> dict:
        """Manevra V-n zarfini hesaplar.
        Alt-ust egriler: CLmax stall sinirlari + sabit n_max/n_min plato.
        """
        Vd = self.Vd
        # Pozitif stall egrisi: n = 0.5*rho*V^2*S*CLmax / W
        v_pos = [i * Vd / n_pts for i in range(1, n_pts + 1)]
        upper = []
        for V in v_pos:
            n_stall = 0.5 * self.rho * V ** 2 * self.wing_area_m2 * self.cl_max / self.W
            upper.append((V, min(n_stall, self.n_max)))

        lower = []
        for V in v_pos:
            n_stall_neg = -0.5 * self.rho * V ** 2 * self.wing_area_m2 * abs(self.cl_min) / self.W
            lower.append((V, max(n_stall_neg, self.n_min)))

        return {
            "Vs1":   round(self.Vs1, 2),
            "Va":    round(self.Va, 2),
            "Vc":    round(self.Vc, 2),
            "Vd":    round(Vd, 2),
            "n_max": self.n_max,
            "n_min": self.n_min,
            "upper_curve": upper,
            "lower_curve": lower,
        }

    # ── Gust zarfi (FAR 23.341) ─────────────────────────────────────────────
    def _gust_alleviation(self) -> float:
        """Gust alleviation faktoru K_g.
        mu_g = 2*(W/S) / (rho*MAC*a*g);  K_g = 0.88*mu_g/(5.3+mu_g)
        """
        mu_g = 2 * self.WS / (self.rho * self.mac_m * self.cl_alpha * G)
        return 0.88 * mu_g / (5.3 + mu_g), mu_g

    def gust_load_factor(self, V_ms: float, U_de_ms: float) -> float:
        """Gust yuk faktoru (FAR 23.341):
        n = 1 + (K_g * U_de * V * a * rho) / (2 * W/S)
        """
        K_g, _ = self._gust_alleviation()
        dn = (K_g * U_de_ms * V_ms * self.cl_alpha * self.rho) / (2 * self.WS)
        return dn

    def gust_envelope(self) -> dict:
        """Vc ve Vd'de gust hatlari (yukari + asagi gust)."""
        K_g, mu_g = self._gust_alleviation()
        lines = {}
        for speed_key, V in [("Vc", self.Vc), ("Vd", self.Vd)]:
            U = GUST_VELOCITIES[speed_key]
            dn = self.gust_load_factor(V, U)
            lines[speed_key] = {
                "V":      round(V, 2),
                "U_de":   U,
                "n_up":   round(1 + dn, 3),
                "n_down": round(1 - dn, 3),
            }
        return {"K_g": round(K_g, 4), "mu_g": round(mu_g, 2), "lines": lines}

    # ── Kritik yuk durumlari ────────────────────────────────────────────────
    def critical_load_cases(self) -> List[dict]:
        """FEA'ya beslenecek kritik yuk durumlarini dondurur.
        Manevra ve gust zarflarinin en kotu kosesini secer.
        """
        man = self.maneuver_envelope()
        gust = self.gust_envelope()

        cases = []
        # Manevra koseleri
        cases.append({"name": "A_maneuver_pos", "V": man["Va"], "n": self.n_max,
                      "desc": "Pozitif manevra koprusu (Va, n_max)"})
        cases.append({"name": "D_dive_pos", "V": man["Vd"], "n": self.n_max,
                      "desc": "Dalista pozitif (Vd, n_max)"})
        cases.append({"name": "E_dive_neg", "V": man["Vd"], "n": self.n_min,
                      "desc": "Dalista negatif (Vd, n_min)"})
        cases.append({"name": "G_maneuver_neg", "V": self.v_stall(abs(self.n_min), False),
                      "n": self.n_min, "desc": "Negatif manevra (n_min stall)"})

        # Gust koseleri — manevra n_max'i asabilir
        gc = gust["lines"]["Vc"]
        gd = gust["lines"]["Vd"]
        cases.append({"name": "Vc_gust_up", "V": gc["V"], "n": gc["n_up"],
                      "desc": f"Vc yukari gust (U={gc['U_de']} m/s)"})
        cases.append({"name": "Vc_gust_down", "V": gc["V"], "n": gc["n_down"],
                      "desc": f"Vc asagi gust"})
        cases.append({"name": "Vd_gust_up", "V": gd["V"], "n": gd["n_up"],
                      "desc": f"Vd yukari gust (U={gd['U_de']} m/s)"})

        # Her durum icin tasarim yuku (N) ve dinamik basinc
        for c in cases:
            c["V"] = round(c["V"], 2)
            c["n"] = round(c["n"], 3)
            c["limit_load_N"]    = round(abs(c["n"]) * self.W, 1)
            c["ultimate_load_N"] = round(abs(c["n"]) * self.W * 1.5, 1)
            c["q_Pa"]            = round(0.5 * self.rho * c["V"] ** 2, 1)

        # En kritik (max |n|) durumu isaretle
        crit = max(cases, key=lambda c: abs(c["n"]))
        crit["is_design_critical"] = True
        return cases

    def summary(self) -> dict:
        return {
            "category":        self.category,
            "mass_kg":         self.mass_kg,
            "wing_loading_Pa": round(self.WS, 1),
            "n_max":           self.n_max,
            "n_min":           self.n_min,
            "speeds_ms":       self.maneuver_envelope(),
            "gust":            self.gust_envelope(),
            "critical_cases":  self.critical_load_cases(),
        }


def envelope_from_aircraft(aircraft, mass_kg: float, cl_max: float = 1.3,
                            v_cruise_ms: float = 18.0, category: str = "normal",
                            cl_alpha: float = None) -> FlightEnvelope:
    """AircraftLibrary Aircraft nesnesinden FlightEnvelope kurar."""
    AR = aircraft.wing.aspect_ratio
    # 3D lift egri egimi: a = a0 / (1 + a0/(pi*e*AR)), a0=2*pi
    if cl_alpha is None:
        a0 = 2 * math.pi
        e = 0.85
        cl_alpha = a0 / (1 + a0 / (math.pi * e * AR))

    mac = aircraft.wing.root_chord() * (2/3) * (
        (1 + aircraft.wing.taper_ratio + aircraft.wing.taper_ratio**2) /
        (1 + aircraft.wing.taper_ratio)
    )

    return FlightEnvelope(
        mass_kg=mass_kg,
        wing_area_m2=aircraft.wing.area,
        wing_span_m=aircraft.wing.span,
        mac_m=mac,
        cl_max=cl_max,
        cl_min=-0.8 * cl_max,
        cl_alpha=cl_alpha,
        v_cruise_ms=v_cruise_ms,
        category=category,
    )


if __name__ == "__main__":
    import json
    # MiniHawk benzeri kucuk IHA
    env = FlightEnvelope(
        mass_kg=1.8, wing_area_m2=0.45, wing_span_m=1.5, mac_m=0.30,
        cl_max=1.3, cl_min=-1.04, cl_alpha=5.0, v_cruise_ms=18.0,
        category="normal",
    )
    print(json.dumps(env.summary(), indent=2, default=str))
