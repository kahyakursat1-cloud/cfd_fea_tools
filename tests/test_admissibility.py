"""Fiziksel kabul-edilebilirlik kapısı — sayısal yakınsama fiziği kurtarmaz.

Somut vaka: gci_airfoil.json coarse seviyesi Cd=-0.0036 iken drift=2.1e-05 olduğu için
raporda "✅ ok" görünüyordu; negatif sürükleme hükmü elle yazılan dipnottaydı.
"""
import json
from pathlib import Path

import pytest

from report_generator import CD_MAX_PLAUSIBLE, CD_MAX_STREAMLINED, force_admissibility

ROOT = Path(__file__).resolve().parent.parent


def test_negatif_cd_kabul_edilemez():
    r = force_admissibility(-0.003593, Cl=0.4478, alpha=4)
    assert r["verdict"] == "inadmissible"
    assert "negatif" in r["reasons"][0]


def test_makul_cd_kabul():
    assert force_admissibility(0.0092, Cl=0.44, alpha=4)["verdict"] == "ok"


def test_asiri_cd_mertebesi_kabul_edilemez():
    assert force_admissibility(CD_MAX_PLAUSIBLE + 0.1)["verdict"] == "inadmissible"


def test_kunt_cisim_haksiz_reddedilmez():
    """GERÇEK ÇÖZÜCÜ DERSİ (2026-07-26): küp regresyonu Cd=1.079 ölçtü ve o zamanki
    tek eşik (0.5) bunu 'fizik-dışı' saydı. Künt cisim (küp≈1.05, levha≈1.98,
    paraşüt≈1.4) geçerli fizik; yanlış alarm kapıya olan güveni yok eder."""
    for cd in (1.079, 1.05, 1.4, 1.98):
        assert force_admissibility(cd)["verdict"] == "ok", f"künt cisim Cd={cd} reddedildi"


def test_akis_yonlu_dar_esik_cagirana_ait():
    """Profil/kanat bilindiğinde çağıran dar eşiği geçirir — o zaman 1.0 şüphelidir."""
    assert force_admissibility(1.0, cd_max=CD_MAX_STREAMLINED)["verdict"] == "inadmissible"
    assert force_admissibility(0.0092, cd_max=CD_MAX_STREAMLINED)["verdict"] == "ok"
    assert CD_MAX_STREAMLINED < CD_MAX_PLAUSIBLE


def test_ters_isaretli_lift_supheli():
    r = force_admissibility(0.01, Cl=-0.4, alpha=4)
    assert r["verdict"] == "suspect"
    # kucuk aci: kamburluk isareti cevirebilir, hukum verme
    assert force_admissibility(0.01, Cl=-0.05, alpha=1)["verdict"] == "ok"


def test_eksik_veri_hukumsuz():
    assert force_admissibility(None)["verdict"] == "ok"


def test_gercek_kanit_dosyasinda_negatif_seviyeler_yakalanir():
    """Regresyon çapası: mevcut O-grid ailesinde tam olarak 2 seviye fizik-dışı."""
    d = json.loads((ROOT / "gci_airfoil.json").read_text(encoding="utf-8"))
    kotu = [lv["name"] for lv in d["levels"]
            if force_admissibility(lv.get("Cd"), lv.get("Cl"),
                                   d.get("alpha"))["verdict"] == "inadmissible"]
    assert kotu == ["coarse", "medium"]
    # ...ve bu seviyeler iterasyon olcutune gore 'ok' idi — kapinin varlik sebebi
    assert all(lv["status"] == "ok" for lv in d["levels"] if lv["name"] in kotu)


# ── NaN sızıntısı (sistematik taramada bulundu) ──────────────────────────────

def test_nan_katsayi_kapidan_gecemez():
    """NaN ile yapılan HER karşılaştırma False döner; `Cd <= 0` ve `abs(Cd) > cd_max`
    kontrolleri NaN'ı ıskalıyor ve kapı "ok" diyordu. Inf yakalanıyordu (mertebe
    kontrolü), NaN geçiyordu — forceCoeffs başlığı değişince parser NaN üretebiliyor."""
    import math
    assert force_admissibility(math.nan)["verdict"] == "inadmissible"
    assert force_admissibility(0.03, math.nan, 4.0)["verdict"] == "inadmissible"
    assert force_admissibility(math.inf)["verdict"] == "inadmissible"
    r = force_admissibility(math.nan)
    assert "sonlu değil" in r["reasons"][0]


def test_saglam_katsayi_nan_kontrolunden_etkilenmez():
    assert force_admissibility(0.032, 0.44, 4.0)["verdict"] == "ok"


def test_forcecoeffs_basliksizsa_sahte_sayi_uretmez():
    """Başlıkta Cd/Cl sütunu yoksa parser her satırda NaN üretip history'yi
    dolduruyordu → çağıran "Cd = nan" alıyordu. Okunamadıysa dürüst cevap None."""
    from analysis.openfoam_runner import parse_force_coeffs_text

    cd, cl, cm, hist = parse_force_coeffs_text("# Time totals\n100 0.5 0.1 0.2\n")
    assert (cd, cl, cm) == (None, None, None) and hist == []

    cd, cl, _, hist = parse_force_coeffs_text("# Time Cd Cs Cl\n100 0.031 0.0 0.44\n")
    assert cd == pytest.approx(0.031) and cl == pytest.approx(0.44) and len(hist) == 1
