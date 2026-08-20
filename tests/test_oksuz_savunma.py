"""Öksüz savunma ölçeri: yanlış pozitif üretmemeli, üretim yolunu görmeli.

Bu ölçer geliştirilirken İKİ yanlış-pozitif kaynağı ölçüldü ve ikisi de bu
depoda gerçek çağrıları gizliyordu:

  (1) TAKMA ADLI İÇE AKTARIM — `from bellek_kapisi import hukum as
      _bellek_hukmu`; çağrı `_bellek_hukmu(...)` göründüğü için `hukum` öksüz
      sanılıyordu.
  (2) TÜKETİCİ DİZİNİNİ TARAMA DIŞI BIRAKMA — `experiments/` V&V sürücüleri
      meşru tüketicidir; dışarıda bırakılınca `salinim_olc` ve `spektral_olc`
      öksüz sanıldı.

Yanlış pozitif üreten ölçer kullanılmaz hale gelir ve gerçek kusuru da gizler
(hakem dersi). Bu test o iki kaynağı BİLİNEN vakalarla sabitler.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import oksuz_savunma as os_  # noqa: E402


def _bulunan_adlar():
    return {x["fonksiyon"] for x in os_.tara() if not x["muaf"]}


def test_TAKMA_ADLI_cagri_oksuz_sayilmaz():
    # bellek_kapisi.hukum vehicle_pipeline'da `hukum as _bellek_hukmu` ile
    # cagriliyor. Takma ad cozulmezse olcer onu oksuz ilan eder.
    assert "hukum" not in _bulunan_adlar()


def test_DENEY_dizinindeki_cagri_SAYILIR():
    # experiments/silindir_urans.py `salinim_olc`, silindir_des_3b.py ise
    # `frekans_capraz_kontrol` cagiriyor (cok satirli import blogu icinde).
    ad = _bulunan_adlar()
    assert "salinim_olc" not in ad
    assert "frekans_capraz_kontrol" not in ad


def test_MUAFIYET_gerekcesiz_olamaz():
    # Gerekcesiz muafiyet olceri susturur; bu depoda "olcemedim" ile "iyi"
    # karistirilmaz.
    for anahtar, gerekce in os_.MUAF.items():
        assert len(gerekce) > 40, anahtar
        assert "KABUL" in gerekce, anahtar


def test_olcer_KENDI_sayisini_raporluyor():
    b = os_.tara()
    acik = [x for x in b if not x["muaf"]]
    # Su an acik madde YOK; artarsa bu test degil, RAPOR degisir — bu yuzden
    # sayi pinlenmez, yalnizca her kaydin gerekce tasidigi aranir.
    for x in acik:
        assert x["ad_izi"] or x["hukum_donuyor"], x["fonksiyon"]
        assert x["dosya"] and x["satir"] > 0


def test_olcerler_KAPSAMINI_beyan_ediyor():
    """KURAL: 'incelenmemiş 0' hükmü ancak KAPSAM biliniyorsa dayanaklıdır.

    Ölçüldü (2026-08-20): `revise_1001_panel.py` UTF-8 BOM ile başlıyordu;
    `encoding="utf-8"` ile okununca BOM satır 1'e düşüp ast.parse'ı düşürüyor
    ve dosya DÖRT tarayıcıda da SESSİZCE atlanıyordu. İçinde gerekçesiz bir
    sessiz yutma vardı — yani `sessiz_yutma` tabanı 87 değil 88'di ve fark
    ölçülmemiş kapsamdan geliyordu.

    Test dosya adı ya da sayı PİNLEMEZ: tarayıcının atladığını SAYDIĞINI ve
    atlanan varsa çıktısında beyan ettiğini arar.
    """
    import sessiz_yutma

    for modul in (os_, sessiz_yutma):
        assert hasattr(modul, "ATLANAN"), modul.__name__
        modul.tara()
        # Atlanan varsa liste dolar; yoksa boş kalır — ikisi de GEÇERLİ,
        # yasak olan atlamayı hiç kaydetmemek.
        assert isinstance(modul.ATLANAN, list)

    # BOM'lu kaynak artık ayrışıyor: utf-8-sig dört tarayıcıda da uygulandı.
    import ast
    from pathlib import Path as _P
    kok = _P(__file__).resolve().parent.parent
    for ad in ("sessiz_yutma.py", "kanal_ayrismasi.py", "oksuz_alan.py",
               "oksuz_savunma.py"):
        src = (kok / ad).read_text(encoding="utf-8")
        assert 'encoding="utf-8-sig"' in src, f"{ad}: BOM körlüğü geri geldi"
    # ve depoda BOM'lu bir kaynak dosya kalırsa bile taranabilmeli
    for p in kok.glob("*.py"):
        ast.parse(p.read_text(encoding="utf-8-sig", errors="replace"))
