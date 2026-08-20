"""Kapanma bütçesi: "ne gerekir" sorusunun cevabı gerekçe değil SAYI olmalı.

Model-form tablosunun boş hücreleri niteliksel gerekçe taşıyordu ("referans
belirsizliği baskın", "ağ inceltmekle kapanmaz"). ASME V&V 20 ölçütü tersine
çevrilince aynı soru kapalı formda cevaplanır ve iki farklı eşik çıkar:

    u_num*  = √(E² − u_D²)          sıfır marj — |E| = u_val, hüküm kırılgan
    u_num** = √((E/1,2)² − u_D²)    kullanılabilir pay

Aradaki fark küçük değil: NACA0012 AR6 kanadında %10,04'e karşı %1,12.
"Ağ %10'a inerse kapanır" cümlesi doğru ama pratikte işe yaramaz.

Burada AYRICA bir tutarsızlık kapandı: geriye-basamak vakasının duvar-çözünür
ve duvar-fonksiyonu aileleri AYNI deneye (Driver & Seegmiller 1985) karşı
ölçülüyor, ama u_D yalnız birinde taşınıyordu. Aynı referansın iki hücreye
farklı belirsizlikle girmesi savunulamaz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from kapanma_butcesi import MARJ, butce  # noqa: E402
from model_form_bandi import _u_ref_turet  # noqa: E402


def test_referans_belirsizligi_kadar_sapmada_AG_CARE_DEGIL():
    """|E| ≤ u_D ise sayısal band sıfır olsa bile hüküm ayrılamaz."""
    b = butce(E_pct=3.0, u_num_pct=0.5, u_D_pct=3.4)
    assert b["durum"] == "AĞ ÇARE DEĞİL"
    assert b["ayrilabilir_mi"] is False
    assert b["gereken_u_num_pct"] is None, "olmayan eşik sayı olarak verilemez"


def test_marjli_esik_sifir_marjlidan_KUCUK():
    """Pay istemek eşiği daraltır; tersi olursa formül yanlış kurulmuştur."""
    b = butce(E_pct=18.05, u_num_pct=17.38, u_D_pct=15.0)
    assert b["gereken_u_num_pct"] > b["marjli_u_num_pct"] > 0
    assert b["marjli_kac_kat"] > b["kac_kat_azalmali"]


def test_sifir_marjli_esikte_ayrilabilirlik_TAM_SINIRDA():
    """u_num* tanım gereği |E| = u_val verir — yani marj sıfırdır.

    Bu testin varlık sebebi: o eşiği "hedef" diye yayımlamak yanıltıcıdır ve
    betiğin uyarısı matematiksel olarak doğrulanmalıdır.
    """
    b = butce(E_pct=18.05, u_num_pct=17.38, u_D_pct=15.0)
    import math
    u_val = math.hypot(b["gereken_u_num_pct"], 15.0)
    assert abs(u_val - 18.05) < 0.02, f"u_val={u_val} ≠ |E|"


def test_u_D_beyan_edilmemisse_SAYI_URETILMEZ():
    """Yokluk sıfır sayılmaz: u_D yoksa bütçe hesaplanmaz, uydurulmaz."""
    b = butce(E_pct=10.0, u_num_pct=2.0, u_D_pct=None)
    assert "BEYAN EDİLMEMİŞ" in b["durum"]
    assert "gereken_u_num_pct" not in b


def test_u_ref_beyandan_TURETIMDEN_once_gelir():
    """Kaynak açıkça band beyan ettiyse türetim onu EZMEMELİ."""
    assert _u_ref_turet({"u_ref_pct": 1.597, "Xr_H": 6.26,
                         "belirsizlik": 0.5}) == 1.597


def test_u_ref_mutlak_belirsizlikten_turetiliyor():
    """Xr/H = 6,26 ± 0,1 → %1,597. Kanıt dosyasında zaten vardı."""
    assert _u_ref_turet({"Xr_H": 6.26, "belirsizlik": 0.1}) == 1.597
    assert _u_ref_turet({"Xr_H": 6.26}) is None


def test_ayni_deney_iki_hucrede_AYNI_u_D_ile_giriyor():
    """Kapanan tutarsızlık: aynı referans, aynı belirsizlik.

    Duvar-çözünür aile u_D taşımıyordu ve ayrılabilirliği u_val = u_num
    varsayarak hesaplıyordu; duvar-fonksiyonu ailesi aynı deneyden %1,597
    taşıyordu. İkisi de Driver & Seegmiller 1985'e karşı ölçülüyor.
    """
    p = KOK / "model_form_bandi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    aileler = [c for c in d["capalar"]
               if "geriye-basamak" in (c.get("capa") or "") and "aile" in c["capa"]]
    if len(aileler) < 2:
        pytest.skip('kanıt/girdi yok: len(aileler) < 2')
    u_d = {c["capa"]: c.get("u_ref_pct") for c in aileler}
    assert all(v is not None for v in u_d.values()), u_d
    assert len(set(u_d.values())) == 1, (
        f"aynı deney, farklı u_D: {u_d}")


def test_kanit_dosyasi_marji_BEYAN_ediyor():
    """1,2 keyfî bir seçim; keyfî olduğu ve ne olduğu yazılı olmalı."""
    p = KOK / "kapanma_butcesi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["_marj"] == MARJ
    assert "u_num**" in d["_formul"] or "E/" in d["_formul"]
    assert d["_kisit"], "GEREK/YETER ayrımı kayıtlı olmalı"
