"""Validasyon çapaları + model-belirsizlik öncülleri (ASME V&V 20 validasyon bacağı).

İki işi var:
1. ANCHORS — literatürden bilinen-doğru referans Cd'ler. validate_pipeline.py bunları
   pipeline'dan geçirip rejim-başına ÖLÇÜLEN hata bandını üretir (compute gerektirir).
2. model_uncertainty_pct — pipeline daha validate edilmeden önce kullanılan LİTERATÜR
   ÖNCÜLÜ: RANS-SST'nin rejim/duvar-çözünürlüğüne göre tipik model hatası. Ölçülen bant
   (validation_band.json) varsa O kullanılır; yoksa bu öncül + açık "validasyon beklemede"
   etiketi döner. Sahte-kesinlik verilmez.

Kaynaklar: küre subkritik Cd≈0.47 (White, Fluid Mechanics; Schlichting). NACA0012 α=0
Cd₀≈0.0081 (Ladson NASA TM-4074 / NASA TMR). Ahmed body 25° Cd≈0.285 (Ahmed 1984; Meile
2011). Rejim model-hatası mertebeleri: RANS-SST harici-aerodinamik V&V literatürü.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

ANCHORS = {
    "sphere": {
        "Cd": 0.47, "regime": "bluff", "Re": "1e3–2e5 (subkritik)",
        "aref": "frontal", "ref": "White, Fluid Mechanics; Schlichting BL Theory",
    },
    "naca0012_a0": {
        "Cd": 0.0081, "regime": "lifting", "Re": "6e6",
        "aref": "kiriş", "ref": "Ladson NASA TM-4074; NASA Turbulence Modeling Resource",
    },
    "ahmed_25": {
        "Cd": 0.285, "regime": "bluff", "Re": "~1e6",
        "aref": "frontal", "ref": "Ahmed et al. 1984; Meile et al. 2011",
    },
    "cube": {
        "Cd": 1.05, "regime": "bluff", "Re": ">1e4 (keskin-kenar, Re-duyarsız)",
        "aref": "frontal", "ref": "Hoerner, Fluid-Dynamic Drag (1965)",
    },
    "disk": {
        "Cd": 1.17, "regime": "bluff", "Re": ">1e3 (keskin-kenar, Re-duyarsız)",
        "aref": "frontal", "ref": "Hoerner, Fluid-Dynamic Drag (1965)",
    },
    "naca0012_wing_ar6": {
        "Cd": 0.020, "regime": "lifting", "Re": "3e5 (c=0.15 m, 30 m/s), α=4°",
        "aref": "planform",
        "ref": ("YARI-ANALİTİK (±%15): türbülanslı profil Cd0≈0.014 (düz-plaka Cf "
                "+ form) + lifting-line CDi=CL²/(πeAR), CL≈0.32, e≈0.9 — Anderson; "
                "deneysel tekil referans yok, band ölçümü bu belirsizlikle etiketli"),
    },
}

# Rejim × duvar-çözünürlüğü → RANS-SST tipik model belirsizliği (%, 1σ mertebesi).
# (wall_resolved=y⁺≲1+katman, wall_function=y⁺≳30). Literatür-öncül; ölçülen bant gelince
# bu DEVRE-DIŞI kalır.
_MODEL_U_PCT = {
    "lifting": {"wall_resolved": 5.0, "wall_function": 12.0},
    "bluff":   {"wall_resolved": 10.0, "wall_function": 20.0},
}
_BAND_FILE = HERE / "validation_band.json"


def regime_of(vehicle_type: str, preset: dict) -> str:
    """Araç tipini model-belirsizlik rejimine indir: lift üreten → 'lifting', küt → 'bluff'."""
    return "lifting" if preset.get("lift_relevant") else "bluff"


def model_uncertainty_pct(regime: str, wall_resolved: bool) -> dict:
    """Rejim+duvar-çözünürlüğü için model belirsizliği (%). Ölçülen validasyon bandı
    (validation_band.json) varsa onu, yoksa literatür-öncülünü döndürür (kaynak etiketli)."""
    key = "wall_resolved" if wall_resolved else "wall_function"
    if _BAND_FILE.exists():
        try:
            band = json.loads(_BAND_FILE.read_text(encoding="utf-8"))
            v = band.get(regime, {}).get(key)
            if v is not None:
                return {"u_model_pct": round(float(v), 2), "kaynak": "ölçülen (validation_band.json)"}
        except Exception:
            pass
    return {"u_model_pct": _MODEL_U_PCT.get(regime, _MODEL_U_PCT["bluff"])[key],
            "kaynak": "literatür-öncül (pipeline-validasyonu beklemede)"}


def combine_uncertainty(u_num_pct: float | None, u_model_pct: float | None) -> float | None:
    """Sayısal (GCI) + model belirsizliğini RSS ile birleştir → toplam genişletilmiş U (%)."""
    parts = [u for u in (u_num_pct, u_model_pct) if u is not None]
    if not parts:
        return None
    return round(math.sqrt(sum(u * u for u in parts)), 2)
