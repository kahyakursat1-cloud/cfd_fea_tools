"""Model-form tablosu daha çok değişkene koşullanabilir mi — güç hesabı.

Hakem (#13) türbülans modeli / Re / ağ kalitesi gibi değişkenlere de
koşullanmasını istedi. İstek makul ama koşullamak hücreleri BÖLMEK demek ve
bugün altı hücrenin beşinde TEK çapa var.

ÖLÇÜLDÜ 2026-08-23:
  σ_iç  = %3,96 (yalnız bluff.wall_function'da ölçülebiliyor, n=3)
  σ_dış = %7,27
  10 puanlık farkı ayırt etmek için hücre başına ~3 çapa (tabloda ~18);
  5 puan için ~10 (~60). Bir değişken daha eklemek bunları İKİYE KATLAR.
  Elde 8 çapa var.

AYRICA — asıl bulgu: altı 'ölçülen' hücrenin ÜÇÜ tam olarak literatür
öncülünü taşıyor. Çapa ölçüldü ama sapma öncülden küçük çıktı ve muhafazakâr
davranılıp öncül korundu. Tablonun veri-güdümlü kısmı 3/6.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from model_form_kosullama import gereken_n  # noqa: E402


def test_DELTA_SIFIR_sifir_capa_DEGIL_ayrilamaz():
    """İki hücre aynı değeri taşıyorsa 'sıfır çapa yeter' değil 'hiçbir zaman
    ayrılamaz' demektir.

    İlk sürüm 0 döndürüyordu ve bütçe tam TERSİNE okunuyordu.
    """
    assert gereken_n(3.96, 0.0) is None
    assert gereken_n(3.96, -1.0) is None
    assert gereken_n(0.0, 5.0) is None


def test_n_farkin_KARESIYLE_ters_orantili():
    """Δ yarıya inince gereken çapa DÖRDE KATLANIR — bütçenin sertliği burada."""
    n5, n25 = gereken_n(3.96, 5.0), gereken_n(3.96, 2.5)
    assert n25 / n5 == pytest.approx(4.0, rel=0.15)


def test_BUTCE_tek_sayi_degil_FARKIN_fonksiyonu():
    """Tek sayı vermek yanıltıcıydı: en yakın çift 5,23 ve 5,41 (Δ=0,18) ve
    ondan hesaplanan bütçe 7602 çıkıyordu --- doğru ama 'koşullama imkânsız'
    diye yanlış okunur. Soru 'hangi farkı görmek istiyorsun' sorusudur.
    """
    p = KOK / "model_form_kosullama.json"
    if not p.exists():
        pytest.skip("model_form_kosullama.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    t = d["butce"]["fark_basina"]
    assert len(t) >= 3, "bütçe tek noktadan veriliyor"
    farklar = [x["ayirt_edilecek_fark_puan"] for x in t]
    assert farklar == sorted(farklar)
    # Buyuk fark DAHA UCUZ olmali
    n = [x["hucre_basina_capa"] for x in t]
    assert n == sorted(n, reverse=True), "bütçe farkla azalmıyor"


def test_BIR_DEGISKEN_DAHA_butceyi_IKIYE_katliyor():
    p = KOK / "model_form_kosullama.json"
    if not p.exists():
        pytest.skip("model_form_kosullama.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    for x in d["butce"]["fark_basina"]:
        assert x["toplam_BIR_DEGISKEN_DAHA"] == 2 * x["toplam_MEVCUT_TABLO"]


def test_ONCULU_KORUYAN_hucreler_veri_gudumlu_SAYILMIYOR():
    """Değeri öncüle eşit olan hücre 'ölçülen' listesinde durur ama TAŞIDIĞI
    SAYI literatürden gelir. Bu ayrım yazılmazsa tablonun veri-güdümlülüğü
    olduğundan çok görünür.
    """
    p = KOK / "model_form_kosullama.json"
    if not p.exists():
        pytest.skip("model_form_kosullama.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    onculu = d["degeri_onculden_gelen_hucreler"]
    assert d["veri_gudumlu_hucre"] + len(onculu) == d["mevcut_hucre"]
    for h in d["hucreler"]:
        if h["hucre"] in onculu:
            assert h["u_pct"] == pytest.approx(h["oncul_pct"]), h["hucre"]
        elif h["oncul_pct"] is not None:
            assert h["u_pct"] != pytest.approx(h["oncul_pct"]), h["hucre"]


def test_OZDES_degerli_cift_ADIYLA_raporlaniyor():
    """Tablo iki hücreyi ayırıyor ama veri ayırmıyorsa bu görünmeli."""
    p = KOK / "model_form_kosullama.json"
    if not p.exists():
        pytest.skip("model_form_kosullama.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    if not d["butce"].get("ozdes_degerli_cift"):
        pytest.skip("özdeş değerli hücre çifti yok")
    assert "ÖZDEŞ" in d["verdikt"]
    assert "veri ayırmıyor" in d["verdikt"]


def test_SIGMA_IC_ust_sinir_oldugu_YAZILI():
    """σ_iç çapaların kendi sayısal bandıyla aynı mertebede; ne kadarı model
    ne kadarı ağ bu veriden çıkmaz. Üst sınır kullanmak bütçeyi BÜYÜK tarafta
    tutar --- muhafazakâr yön, ve bu yazılı olmalı."""
    p = KOK / "model_form_kosullama.json"
    if not p.exists():
        pytest.skip("model_form_kosullama.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "UST SINIRDIR" in d["_kisit"]
    assert "KARESEL" in d["_kisit"], "bütçenin σ'ya karesel bağlılığı yazılmamış"
