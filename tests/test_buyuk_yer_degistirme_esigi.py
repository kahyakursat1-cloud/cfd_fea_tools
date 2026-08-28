"""Lineer statigin geometrik gecerlilik esigi --- OLCUMLE kuruldu.

Bu testler iki ayri seyi baglar:

  1. ESIGIN KENDISI bir kanit dosyasindan gelir, kaynakta sabit sayi
     olarak durmaz. `vehicle_fea.LINEER_GECERLI_DELTA_L_PCT` ile
     `buyuk_yer_degistirme_esigi.json` ayrisirsa test duser.
  2. YASA UYDURMASININ olcutu HEM tutan HEM tutmayan veriyle sinanir.
     Ilk surumde artik olcutu %5'ti ve yasa "tutmuyor" hukmu aldi ---
     ama olculen sey fizik degil, sapmanin 3 ondaliga yuvarlanmasiydi
     (en kucuk nokta -0,002, yani IKI kuantum). Olcut kendi cikti
     cozunurlugunu olcuyordu.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "buyuk_yer_degistirme_esigi.json"


def _kanit() -> dict:
    if not KANIT.exists():
        pytest.skip(f"{KANIT.name} yok — experiments/ betigi kosulmali")
    return json.loads(KANIT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- yasa fiti
# SENTETIK: kanit dosyasindan BAGIMSIZ calisir, atlanamaz. (Bu depoda yedi
# test bir kanit dosyasi silindigi icin sessizce atlanmisti.)

def _fit(noktalar):
    from buyuk_yer_degistirme_esigi import _uy_yasasi
    return _uy_yasasi(noktalar)


def _nokta(dl, sapma):
    return {"kosdu": True, "delta_L_pct": dl, "uy_sapma_pct": sapma}


def test_YASA_TAM_KARE_VERIDE_TUTUYOR():
    """Yanlis-negatif tarafi: kusursuz kare veride olcut TUTMALI ve usu
    2'yi bulmali."""
    n = [_nokta(d, -0.008 * d ** 2) for d in (0.5, 1, 2.5, 5, 10, 19)]
    r = _fit(n)
    assert r["olculdu"] and r["tutuyor"], r
    assert abs(r["us"] - 2.0) < 1e-6, r["us"]
    assert abs(r["katsayi"] - 0.008) < 1e-6, r["katsayi"]


def test_YASA_GUC_YASASI_OLMAYAN_VERIDE_TUTMUYOR():
    """Yanlis-pozitif tarafi: olcut her seye 'tutuyor' demiyor. Ussel
    buyuyen bir sinyal log-log'da dogru DEGILDIR."""
    import math
    n = [_nokta(d, -math.exp(d / 3.0)) for d in (0.5, 1, 2.5, 5, 10, 19)]
    r = _fit(n)
    assert r["olculdu"] and not r["tutuyor"], r


def test_YASA_ESIGI_TAVANDAN_COZUYOR():
    """Turetilen esik, uydurulan yasanin kendi tersidir --- ayri bir
    sabit degil."""
    n = [_nokta(d, -0.008 * d ** 2) for d in (0.5, 1, 2.5, 5, 10, 19)]
    r = _fit(n)
    assert abs(r["delta_L_esik_1pct"] - (1.0 / 0.008) ** 0.5) < 1e-3


def test_YASA_TUTMAYINCA_ESIK_URETMIYOR():
    """Tutmayan bir fitten esik turetmek sahte kesinlik olurdu."""
    import math
    n = [_nokta(d, -math.exp(d / 3.0)) for d in (0.5, 1, 2.5, 5, 10, 19)]
    r = _fit(n)
    assert "delta_L_esik_1pct" not in r


def test_AZ_NOKTADA_FIT_YAPILMIYOR():
    assert _fit([_nokta(1, -0.008), _nokta(2, -0.032)])["olculdu"] is False


# ------------------------------------------------------------ kanit baglari

def test_ESIK_KAYNAKTA_SABIT_DEGIL_KANITTAN():
    """`vehicle_fea`'daki esik kanit dosyasiyla AYNI olmali. Ayrisirsa
    kanit yenilendiginde uretim yolu eski sayiyla hukum verirdi."""
    import vehicle_fea
    k = _kanit()
    if not k["uy_yasasi"].get("tutuyor"):
        pytest.fail("kanitta yasa tutmuyor — esik turetilemez")
    beklenen = k["uy_yasasi"]["delta_L_esik_1pct"]
    assert abs(vehicle_fea.LINEER_GECERLI_DELTA_L_PCT - beklenen) < 0.1, (
        f"vehicle_fea {vehicle_fea.LINEER_GECERLI_DELTA_L_PCT} diyor, kanit "
        f"{beklenen}")


def test_EKSENEL_SAPMA_ESIKTEN_BAGIMSIZ():
    """Kapinin metnindeki 'ux butun bantta ~%100 yanlis' iddiasi kanitta
    OLCULMUS olmali --- kapi bir iddiayi tasiyorsa o iddia olculmus
    olmalidir."""
    e = _kanit()["eksenel_hukum"]
    assert e["olculdu"] and e["esikten_bagimsiz"], e
    assert e["ux_sapma_min_pct"] > 90.0, e


def test_MEKANIZMA_KAPISI_NLGEOM_ESIGINDEN_ONCE_BAGLIYOR():
    """KAPININ GEREKCESI. `_lineer_gecerlilik` 'gecerli pencerenin tamami
    lineerin icinde' diyor; bu ancak mekanizma tavani olculen esikten
    KUCUKSE dogrudur. Mekanizma tavani gevsetilirse bu test duser ve
    gerekce yeniden olculmelidir."""
    import inspect

    import vehicle_fea
    src = inspect.getsource(vehicle_fea._mechanism_check)
    assert "0.05 * lmax_m" in src, (
        "mekanizma tavani degismis — `_lineer_gecerlilik`'in gerekcesi "
        "bu tavanin %11,1'in altinda olmasina dayaniyor")
    assert vehicle_fea.LINEER_GECERLI_DELTA_L_PCT > 5.0


# ------------------------------------------------------------ uretim yolu

def test_URETIM_YOLU_KAPIYI_CAGIRIYOR():
    """Bu deponun BASKIN KUSURU: kapi var ama uretim yolu onu cagirmiyor.
    Olcut metne degil AGACA baglanir: `run_structural_check` govdesinde
    `_lineer_gecerlilik` cagrisi bulunmali."""
    import ast
    agac = ast.parse((KOK / "vehicle_fea.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef)
              and n.name == "run_structural_check")
    cagrilar = [getattr(c.func, "id", getattr(c.func, "attr", ""))
                for c in ast.walk(fn) if isinstance(c, ast.Call)]
    assert "_lineer_gecerlilik" in cagrilar, (
        "kapi tanimli ama uretim yolu cagirmiyor")
    # OLCUT SAYIYA DEGIL MEKANIZMAYA BAGLI: sehim hukmu veren HER yol
    # (dolu-kati ve kabuk) kapiyi da cagirmali. Ucuncu bir statik yol
    # eklenirse bu test onu yakalar; sabit bir "2 olsun" yakalamazdi.
    assert (cagrilar.count("_lineer_gecerlilik")
            == cagrilar.count("_mechanism_check")), (
        f"_mechanism_check {cagrilar.count('_mechanism_check')} yerde, "
        f"_lineer_gecerlilik {cagrilar.count('_lineer_gecerlilik')} yerde — "
        "sehme hukum veren her yol kapiyi da cagirmali")


def test_PRESETLER_TEK_YUZ_TUTUYOR():
    """KAPININ IKINCI GEREKCESI. `_lineer_gecerlilik` eksenel yolun besleme
    yapmadigini soylerken bunu mesnet presetlerinin TEK YUZ tutmasina
    dayandiriyor: uc eksenel serbest → kisalma engellenmiyor → zar
    sertlesmesi yok. Iki yuzu tutan bir preset eklenirse o gerekce coker
    ve lineer cozum olculen banttan cok once bozulur.

    Olcut yapiya baglanir: her preset (aciklama, eksen, taraf) uclusudur
    ve TEK eksen/TEK taraf tasir --- yani tanimi geregi tek duzlem.
    """
    from vehicle_fea import CONSTRAINT_PRESETS
    assert CONSTRAINT_PRESETS, "preset ailesi bos"
    for ad, v in CONSTRAINT_PRESETS.items():
        assert len(v) == 3, (
            f"{ad}: preset ucluden ciktı — tek duzlem varsayimi artik "
            "gecerli olmayabilir")
        _, eksen, taraf = v
        assert eksen in (0, 1, 2), f"{ad}: eksen {eksen}"
        assert taraf in ("min", "max"), f"{ad}: taraf {taraf}"


def test_KAPI_ALTINDA_YETERLI_USTUNDE_DEGIL():
    """Olcutun iki tarafi. lmax = 1 m; esik %11,1 → 111 mm."""
    from vehicle_fea import _lineer_gecerlilik
    assert _lineer_gecerlilik(50.0, 1.0)["yeterli"] is True
    assert _lineer_gecerlilik(150.0, 1.0)["yeterli"] is False
    assert _lineer_gecerlilik(None, 1.0) is None
    assert _lineer_gecerlilik(50.0, 0.0) is None
