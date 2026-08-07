"""Ayrılabilirlik ölçütü — REFERANS belirsizliği de hesaba girer mi?

ASME V&V 20'de karşılaştırma belirsizliği u_val = √(u_num² + u_input² + u_D²).
Bu depoda u_D (referans belirsizliği) hesaba HİÇ girmiyordu ve ölçüt sistematik
olarak GEVŞEKTİ.

ÖLÇÜLEN VAKA: yarı-analitik kanat çapası (NACA0012 AR6). Referansı ±%15 ile
etiketli ve bu, çapanın kendi metninde YAZILI — ama sayı olarak taşınmadığı
için görünmüyordu. Ham sapma %18,05, sayısal band %17,38: eski ölçüt
"ayrılabilir" diyordu. u_D=%15 katılınca u_val=%22,96 ve fark ayırt EDİLEMEZ.

Bunun pratik sonucu, bir gecelik CFD koşusunun iptalidir: sayısal bandı
iyileştirmek o çapayı kurtaramaz, çünkü u_val hiçbir zaman %15'in altına
inemez — referansın kendisi o kadar belirsiz.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from model_form_bandi import ayrilabilir  # noqa: E402

from validation_anchors import ANCHORS  # noqa: E402


def test_referans_belirsizligi_u_vale_GIRIYOR():
    r = ayrilabilir(18.05, 17.38, 15.0)
    assert r["u_val_pct"] == round(math.hypot(17.38, 15.0), 2)
    assert r["ayrilabilir_mi"] is False, "u_D yok sayılıyor — ölçüt gevşek"


def test_ayni_veri_u_ref_YOKSA_gevsek_kaliyor():
    """Karşılaştırma: u_D beyan edilmezse eski (gevşek) hüküm çıkar. Bu bir
    kusur değil, BİLGİ EKSİKLİĞİDİR ve öyle etiketlenmeli."""
    r = ayrilabilir(18.05, 17.38, None)
    assert r["ayrilabilir_mi"] is True
    assert "BEYAN EDİLMEMİŞ" in r["gerekce"]
    assert "BÜYÜKTÜR" in r["gerekce"], "yokluk sıfır sayılıyormuş gibi okunmamalı"


def test_sayisal_band_yoksa_DEGERLENDIRILMEDI():
    """'Değerlendirilmedi' ile 'ayrılamaz' aynı şey değil — ikincisi hücreye
    üst-sınır damgası vurur, birincisi vurmamalı."""
    r = ayrilabilir(18.05, None, 15.0)
    assert r["ayrilabilir_mi"] is None
    assert "DEĞERLENDİRİLMEDİ" in r["gerekce"]


def test_buyuk_sapma_kucuk_bantla_AYRILABILIR():
    r = ayrilabilir(10.46, 2.39, None)
    assert r["ayrilabilir_mi"] is True


def test_u_val_bilesenlerin_HER_BIRINDEN_buyuk():
    """RSS toplamı: u_val ne u_num'dan ne u_D'den küçük olabilir."""
    for un, ud in ((5.0, 3.0), (17.38, 15.0), (1.0, 40.0)):
        u = ayrilabilir(999.0, un, ud)["u_val_pct"]
        assert u >= un - 1e-9 and u >= ud - 1e-9


def test_kanat_capasinin_belirsizligi_SAYI_olarak_tasiniyor():
    """Metinde '±%15' yazması yetmez; karar veren yere sayı olarak ulaşmalı."""
    spec = ANCHORS["naca0012_wing_ar6"]
    assert spec.get("u_ref_pct") == 15.0
    assert "%15" in spec["ref"], "metin ile sayı ayrışmamalı"


def test_alpha0_capasi_LIFTING_degil():
    """α=0'da taşıma sıfırdır; vaka bağlı 2B akıştır. Etiket 'lifting' iken
    model_form_bandi onu attached_2d hücresine yazıyordu — iki kaynak
    çelişiyordu."""
    assert ANCHORS["naca0012_a0"]["regime"] == "attached_2d"


def test_her_capa_u_ref_alanini_TASIYOR():
    """Alanın yokluğu ile None farklı: yokluk 'hiç düşünülmedi' demektir ve
    sessizce sıfır sayılır."""
    eksik = [a for a, s in ANCHORS.items() if "u_ref_pct" not in s]
    assert not eksik, f"u_ref_pct alanı yok: {eksik}"
