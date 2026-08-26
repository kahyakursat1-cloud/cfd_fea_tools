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


def test_KIMLIK_olan_sayiyla_kapi_kurulamaz():
    """DIŞ HAKEM P1 (2026-08-26): moment artığı için üretim kabul ölçütü.

    Denetlerken kapının kendisinin ATIL olduğu çıktı. Korunumlu şemaya
    geçince `aktarim_hatasi_pct` KİMLİK gereği sıfır oldu (24/24 vakada tam
    0,0000) ve kapı ona bakıyordu --- yani her koşuyu geçiriyordu. Savunma
    duruyordu, üretim yolu ona boş bir sayı besliyordu.
    """
    r = aktarim_hukmu(0.0)
    assert r["kod"] == "OLCUT_ATIL" and r["kullanilabilir"] is None
    assert "KİMLİKTİR" in r["neden"]


def test_HAKIM_ARTIK_ucunun_EN_BUYUGU():
    """En küçüğü almak kapıyı yine susturur; muhafazakâr yön en büyüğüdür."""
    r = aktarim_hukmu(0.0, moment_artigi_pct=13.54, is_artigi_pct=102.64,
                      u_toplam_pct=5.0)
    assert r["hakim_metrik"] == "arayuz_isi"
    assert r["kullanilabilir"] is False
    assert set(r["bilesenler"]) == {"kuvvet", "moment", "arayuz_isi"}


def test_ESKI_SEMA_hukmu_DEGISMEDI():
    """Yanlış-pozitif kapısı: `sema="tutarli"` koşularında kuvvet artığı
    hâlâ anlamlıdır ve hüküm eskisi gibi verilmeli."""
    r = aktarim_hukmu(20.0, u_toplam_pct=5.0)
    assert r["kod"] == "AKTARIM_BANDA_BASKIN" and r["hakim_metrik"] == "kuvvet"


def test_KUCUK_artiklar_GECER():
    """Kapı katı olmamalı: bandın içindeki artık koşuyu düşürmez."""
    r = aktarim_hukmu(0.0, moment_artigi_pct=0.3, is_artigi_pct=0.5,
                      u_toplam_pct=5.0)
    assert r["kullanilabilir"] is True and r["kod"] == "BAND_ICINDE"


def test_URETIM_YOLU_kapiyi_UC_ARTIKLA_besliyor():
    """Kapı ile çağıran ayrışmasın: sürücü moment ve işi TAŞIMALI.

    Kaynak-metni aramak yetmez --- alan adları kayıtta da geçebilir. AST ile
    çağrının ANAHTAR ARGÜMANLARI denetlenir.
    """
    import ast

    src = (KOK / "fsi_surucu.py").read_text(encoding="utf-8")
    cagri = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "aktarim_hukmu"]
    assert cagri, "üretim yolu kapıyı hiç çağırmıyor"
    for c in cagri:
        adlar = {k.arg for k in c.keywords}
        assert {"moment_artigi_pct", "is_artigi_pct"} <= adlar, (
            "sürücü kapıya moment/iş artığını vermiyor — kapı kimlik olan "
            f"kuvvet artığına bakar ve ATIL kalır (verilen: {sorted(adlar)})")
