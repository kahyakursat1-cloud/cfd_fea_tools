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
