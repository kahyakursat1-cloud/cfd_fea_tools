"""Düz levha duvar-fonksiyonu ailesi — u_D ÖLÇÜLÜR, hücre ÜST SINIR kalır.

Bu çapanın öğrettiği şey ASME V&V 20'nin doğrudan sonucudur: model hatası
(%2,79) referansın kendi belirsizliğinden (%3,36) küçükse ayrılamaz. Hücre
ölçüm değil ÜST SINIR olarak kaydedilmelidir; aksi hâlde ölçülemeyen bir sayı
ölçülmüş gibi yayımlanır.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "experiments"))
sys.path.insert(0, str(KOK))

KANIT = KOK / "duz_levha_aile.json"


@pytest.fixture(scope="module")
def kanit() -> dict:
    if not KANIT.exists():
        pytest.skip("duz_levha_aile.json yok — python experiments/duz_levha_cf.py --aile")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_u_D_iki_korelasyonun_farkindan_OLCULUR():
    """u_D uydurulmaz. İki yerleşik korelasyonun aynı Re_x'teki farkı."""
    import duz_levha_cf as f
    re_x = f.U_INF * f.X_OLCUM / f.NU
    a, b = f.cf_referans(re_x), f.cf_schultz_grunow(re_x)
    u_d = abs(a - b) / a * 100
    assert 2.0 < u_d < 5.0, f"beklenmedik u_D=%{u_d}"


def test_ilk_hucre_merkez_duzeltmesi_iceriyor():
    """y⁺ hücre MERKEZİNDE hesaplanır → ilk hücre yüksekliği 2× olmalı.

    Çarpansız sürüm hedefin yarısını üretiyordu ve aile tampon bölgeye düşüyordu.
    """
    import duz_levha_cf as f
    cf = f.cf_referans(f.U_INF * f.X_OLCUM / f.NU)
    u_tau = (0.5 * f.U_INF ** 2 * cf) ** 0.5
    assert f._ilk_hucre(50.0) == pytest.approx(2.0 * 50.0 * f.NU / u_tau)


def test_aile_uc_seviye_tamamlandi(kanit):
    ok = [s for s in kanit["seviyeler"] if s["durum"] == "ok"]
    assert len(ok) == 3, [s["durum"] for s in kanit["seviyeler"]]


def test_ilk_hucre_seviyeler_boyunca_SABIT(kanit):
    """Yönlü aile kuralı: ilk hücre değişirse aile tek hücreyi temsil etmez."""
    assert kanit["aile"]["tasarim"].startswith("YÖNLÜ")
    ok = [s for s in kanit["seviyeler"] if s["durum"] == "ok"]
    ypler = [s["yplus"] for s in ok]
    assert max(ypler) - min(ypler) < 1.0, ypler


def test_uc_seviye_de_duvar_fonksiyonu_bandinda(kanit):
    ok = [s for s in kanit["seviyeler"] if s["durum"] == "ok"]
    assert all(30 <= s["yplus"] <= 300 for s in ok), [s["yplus"] for s in ok]
    assert kanit["duvar_islemi"] == "wall_function"


def test_model_hatasi_AYRILAMIYOR(kanit):
    """Ölçülen durum: |E| < u_val. Bu bir başarısızlık değil, hükmün kendisi."""
    ayr = kanit["ayrilabilirlik"]
    assert ayr is not None
    assert ayr["ayrilabilir_mi"] is False
    assert "ÜST SINIR" in kanit["verdikt"]


def test_hucre_model_form_tablosunda_UST_SINIR():
    mf = KOK / "model_form_bandi.json"
    if not mf.exists():
        pytest.skip("model_form_bandi.json yok")
    d = json.loads(mf.read_text(encoding="utf-8"))
    hucre = d["olculen_hucreler"]["attached_2d"]["wall_function"]
    assert hucre["_ust_sinir_mi"] is True
    assert hucre["oncul_korundu"] is True, "tek ölçümle band aşağı daraltılmış"
    assert "attached_2d.wall_function" in d["ozet"]["ust_sinir_hucreleri"]


def test_kapsam_duvar_normali_disladigini_soyluyor(kanit):
    assert "KAPSAMAZ" in kanit["_kapsam"]
