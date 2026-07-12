"""least_squares_gci (Eça-Hoekstra LSR, basitleştirilmiş) — 3-nokta Richardson'ın
çözemediği non-asimptotik/salınımlı dizilerde savunulabilir belirsizlik bandı."""
import json
import math
from pathlib import Path

import pytest

from report_generator import least_squares_gci

ROOT = Path(__file__).resolve().parent.parent


def _h(n=5, r=1.3):
    return [0.001 * r ** i for i in range(n)]


def test_ideal_second_order_reduces_to_gci():
    h = _h()
    f = [0.01 + 0.05 * x ** 2 for x in h]
    g = least_squares_gci(h, f)
    assert g["guvenilir"] and g["convergence"] == "monotonic"
    assert g["p"] == pytest.approx(2.0, abs=0.02)
    assert g["f_exact"] == pytest.approx(0.01, rel=1e-3)
    assert g["u_pct"] < 0.5


def test_noisy_second_order_still_recovers():
    h = _h(6)
    noise = [1e-5, -8e-6, 6e-6, -1e-5, 9e-6, -7e-6]
    f = [0.01 + 0.05 * x ** 2 + e for x, e in zip(h, noise)]
    g = least_squares_gci(h, f)
    assert g["f_exact"] == pytest.approx(0.01, abs=5e-4)
    assert g["u_abs"] >= g["sigma_abs"]            # fit gürültüsü banda dahil


def test_oscillatory_no_extrapolation():
    h = _h()
    f = [0.0102, 0.0098, 0.0101, 0.0099, 0.01005]  # ince→kaba salınım
    g = least_squares_gci(h, f)
    assert g["convergence"] == "oscillatory" and not g["guvenilir"]
    assert g["f_exact"] == f[0]                    # ekstrapolasyon YOK
    dm = max(f) - min(f)
    assert g["u_abs"] == pytest.approx(3 * dm, rel=1e-6)


def test_subasymptotic_never_extrapolates():
    # p→0'da fit dejenere (h^p ~sabit) → f_exact patlıyordu (Ahmed: -7.8, U %7670).
    # Asimptotik-altı dal artık ekstrapole ETMEZ: f_exact=f_ince, U=3·Δ_M+σ (sonlu).
    h = _h(5)
    f = [0.3 + 0.5 * x ** 0.1 for x in h]
    g = least_squares_gci(h, f)
    assert g["convergence"] == "monotonic" and g["p"] < 0.5
    assert g["f_exact"] == pytest.approx(f[0], rel=1e-6)     # ince-mesh değeri, ekstrapolasyon yok
    dm = max(f) - min(f)
    assert g["u_abs"] < 5 * dm                               # veri-aralığı ölçeğinde, patlama yok
    assert "ekstrapolasyon yok" in g["kural"] and not g["guvenilir"]


def test_requires_four_grids():
    assert least_squares_gci([1e-3, 2e-3, 3e-3], [0.1, 0.11, 0.12]) is None
    assert least_squares_gci(_h(4), [0.01] * 4) is None   # dejenere (özdeş)


def test_real_airfoil_cd_honest_wide_band():
    # Kronik vaka (gci_airfoil.json, 5-seviye O-grid): 3-nokta Richardson asimptotik
    # aralık dışıydı. LSR dürüst-geniş band verir ve band deneysel referansı KAPSAR.
    d = json.loads((ROOT / "gci_airfoil.json").read_text(encoding="utf-8"))
    h = [1 / math.sqrt(lv["cells"]) for lv in d["levels"]]
    cd = [lv["Cd"] for lv in d["levels"]]
    g = least_squares_gci(h, cd)
    assert g["convergence"] == "monotonic" and g["n"] == 5
    assert g["u_pct"] > 30                          # dar-band yanılsaması yok
    lo, hi = g["f_exact"] - g["u_abs"], g["f_exact"] + g["u_abs"]
    assert lo < d["reference"]["Cd_turb"] < hi      # Ladson türbülanslı Cd bandın içinde


def test_real_airfoil_cl_mixed_flagged():
    d = json.loads((ROOT / "gci_airfoil.json").read_text(encoding="utf-8"))
    h = [1 / math.sqrt(lv["cells"]) for lv in d["levels"]]
    cl = [lv["Cl"] for lv in d["levels"]]
    g = least_squares_gci(h, cl)
    assert g["convergence"] in ("oscillatory", "mixed") and not g["guvenilir"]
    lo, hi = g["f_exact"] - g["u_abs"], g["f_exact"] + g["u_abs"]
    assert lo < d["reference"]["Cl"] < hi           # Ladson Cl bandın içinde
