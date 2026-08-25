"""CFD→FEA yük aktarımı hükme bağlanıyor mu?

Hakem incelemesi (2026-08-24) bunu P0 olarak işaretledi ve haklıydı:
`aktarim_hatasi` 20 vakada %0,07--%56,30 arası ölçülüyordu ama hiçbir kapı
okumuyordu. Kuvvet korunumu 1e-18 olduğu için %56'lık bir koşu ``korunumlu''
görünüyordu --- oysa o metrik FEA yüzü→düğüm dağıtımını ölçer ve eşit-üçtebir
şemasında YAPI GEREĞİ kesindir.

Bu testler kapıyı HEM yanlış-pozitif HEM yanlış-negatif için sınar; kapının
ilk sürümü ölçütünden geniş çıkmıştı ve bu burada kayda geçiyor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from fsi_aktarim_kapisi import (  # noqa: E402
    ALAN_KIMLIK_ESIGI_PCT,
    MUTLAK_RED_PCT,
    aktarim_hukmu,
)


def test_buyuk_aktarim_hatasi_REDDEDILIYOR():
    h = aktarim_hukmu(56.30, 49.83)
    assert h["kullanilabilir"] is False
    assert h["kod"] == "AKTARIM_HATASI_BUYUK"
    assert "tasarım kararında kullanılamaz" in h["neden"]
    # ESLEME KUSURU BANDA GOMULMEZ — bu ayrim hukumde yazili olmali
    assert "belirsizlik değildir" in h["neden"]


def test_ALAN_FARKI_TEK_BASINA_reddetmiyor():
    """Kapının ilk sürümü bunu yapıyordu ve ölçümle geri çekildi.

    `MiniHawk_UAV`: alan farkı %7,46 (eşiğin üstünde) AMA aktarım hatası
    %0,90. Yük doğru taşınmış. Alan farkıyla reddetmek çalışan bir vakayı
    öldürürdü.
    """
    h = aktarim_hukmu(0.90, 7.46)
    assert h["kullanilabilir"] is True, "alan farkı tek başına reddediyor"
    assert "TEŞHİS" in h["neden"], "risk göstergesi hükümde görünmüyor"


def test_banda_baskin_hata_REDDEDILIYOR():
    """Hata koşunun kendi bandından büyükse band anlamını yitirir."""
    h = aktarim_hukmu(20.25, 9.48, u_toplam_pct=12.0)
    assert h["kullanilabilir"] is False
    assert h["kod"] == "AKTARIM_BANDA_BASKIN"
    h2 = aktarim_hukmu(3.88, 0.0, u_toplam_pct=12.0)
    assert h2["kullanilabilir"] is True and h2["kod"] == "BAND_ICINDE"


def test_band_verilmezse_SESSIZ_gecmiyor():
    """Banda-göreli dal çalışmadıysa bu SÖYLENMELİ; sessiz geçiş,
    denetlenmemiş bir koşuyu denetlenmiş gibi gösterir."""
    h = aktarim_hukmu(3.88, 0.0)
    assert h["kod"] == "BAND_YOK"
    assert "SORULMAMIŞTIR" in h["neden"]


def test_OLCULEMEDI_guvenilir_sayilmiyor():
    h = aktarim_hukmu(None)
    assert h["kullanilabilir"] is None
    assert "DOĞRULANMAMIŞTIR" in h["neden"]


def test_esikler_OLCULEN_dagilimla_tutarli():
    """Eşikler uydurulmadı, dağılımdaki boşluğa kondu. Dağılım değişirse
    bu test eşiğin hâlâ o boşlukta olup olmadığını sorar."""
    p = KOK / "fsi_korunum.json"
    if not p.exists():
        import pytest
        pytest.skip("fsi_korunum.json üretilmemiş")
    v = sorted(k["aktarim_hatasi_pct"]
               for k in json.loads(p.read_text(encoding="utf-8"))["vakalar"]
               if k.get("aktarim_hatasi_pct") is not None)
    # MUTLAK_RED sicramanin ustunu kesmeli: altinda cok vaka, ustunde AZ
    alt = [x for x in v if x <= MUTLAK_RED_PCT]
    ust = [x for x in v if x > MUTLAK_RED_PCT]
    assert len(alt) >= 15 and len(ust) <= 2, (
        f"eşik dağılımdaki boşlukta değil: {len(alt)} altında, {len(ust)} üstünde")
    assert 0 < ALAN_KIMLIK_ESIGI_PCT < 100


def test_URETIM_YOLU_kapiyi_cagiriyor():
    """Kapı VAR ama sürücü çağırmıyorsa kapı yoktur — bu deponun kusuru."""
    src = (KOK / "fsi_surucu.py").read_text(encoding="utf-8")
    assert "_aktarim_hukmu_ozeti" in src
    assert "yuk_aktarimi_kullanilabilir" in src
    # TESHIS ALANI TUR KAYDINA GIRIYOR MU
    assert '"alan_farki_pct": yukler.get("alan_farki_pct")' in src


def test_gecmis_YOKSA_gecerli_sayilmiyor():
    import fsi_surucu as f
    r = f._aktarim_hukmu_ozeti([])
    assert r["yuk_aktarimi_kullanilabilir"] is None
