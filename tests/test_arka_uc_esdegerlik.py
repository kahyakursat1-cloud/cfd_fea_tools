"""Arka-uç taşıması: engel dosyalarda değil KATMANDA eksikti.

İki dosya "taşıma davranışı değiştirebilir, önce eşdeğerlik ölçülmeli"
gerekçesiyle bekliyordu. Ölçüldüğünde engel netleşti: `linux_argv` login kabuğu,
`linux_run` stdin beslemesini desteklemiyordu. İkisi eklendi, eşdeğerlik ölçüldü
(birebir), taşıma yapıldı. Bu dosya hem katman yeteneklerini hem ölçüm sırasında
yakalanan `_keskin_firar` kusurunu kilitler.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))


def test_linux_argv_login_kabugu_kurabiliyor():
    from analysis.backend import linux_argv
    assert "-c" in linux_argv("echo x")
    assert "-lc" in linux_argv("echo x", login=True)
    assert "-lc" not in linux_argv("echo x")


def test_linux_run_stdin_besleyebiliyor():
    from analysis.backend import linux_run
    r = linux_run("cat", 60, girdi="merhaba\n")
    assert r.stdout.strip() == "merhaba"


def test_login_kabugu_varsayilani_DEGISTIRMEDI():
    """Yeni seçenek eklemek eski çağrıları etkilememeli."""
    from analysis.backend import linux_argv
    assert linux_argv("echo x") == linux_argv("echo x", login=False)


# ── ölçüm sırasında yakalanan kusur: koşulsuz 'y' cevabı ────────────────────

def test_keskin_firar_kenari_KOORDINATTAN_olculuyor():
    from construct2d_bridge import _keskin_firar
    ornek = KOK / "Construct2D" / "sample_airfoils"
    if not ornek.exists():
        pytest.skip("örnek profiller yok")
    kunt = ornek / "naca0012.dat"
    keskin = ornek / "naca0012_sharp.dat"
    if not (kunt.exists() and keskin.exists()):
        pytest.skip("karşılaştırma profilleri yok")
    assert _keskin_firar(keskin) is True
    assert _keskin_firar(kunt) is False


def test_okunamayan_profil_ESKI_davranisa_duser():
    """Belirsizlikte 'keskin' varsayılır — değişiklik bilinen vakalarda etkisiz."""
    from construct2d_bridge import _keskin_firar
    assert _keskin_firar(KOK / "yok_boyle_bir_dosya.dat") is True


# ── kanıt ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def kanit() -> dict:
    p = KOK / "arka_uc_esdegerlik.json"
    if not p.exists():
        pytest.skip("arka_uc_esdegerlik.json yok")
    return json.loads(p.read_text(encoding="utf-8"))


def test_esdegerlik_TASIMADAN_ONCE_olculdu(kanit):
    assert kanit["tasinabilir_mi"] is True, kanit.get("verdikt")
    assert kanit["xfoil"]["durum"] == "AYNI"
    assert kanit["xfoil"]["en_buyuk_bagil_fark"] <= kanit["xfoil"]["esik"]


def test_construct2d_uretilen_ag_BIREBIR_ayni(kanit):
    c = kanit["construct2d"]
    if c.get("durum") == "atlandi":
        pytest.skip(c.get("neden", "atlandı"))
    assert c["durum"] == "AYNI"
    assert c["eski"] == c["yeni"], (c["eski"], c["yeni"])
    assert c["surec_gorunurlugu"]["ayni"] is True


def test_sayac_dustu_ve_kalan_MESRU():
    """Kalan satırlar yalnız karşılaştırma tabanı olmalı."""
    import arka_uc_sayaci as a
    dosyalar = set(a.ozet()["dosyalar"])
    assert "construct2d_bridge.py" not in dosyalar, "taşınmıştı, geri mi geldi?"
    assert "xfoil_kesit.py" not in dosyalar
    # Kalan her dosya BEKLEYEN'de gerekcesiyle kayitli olmali.
    assert dosyalar <= set(a.BEKLEYEN), dosyalar - set(a.BEKLEYEN)
