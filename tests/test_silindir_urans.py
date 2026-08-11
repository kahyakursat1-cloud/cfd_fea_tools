"""Türbülanslı URANS çapası — hüküm İKİYE ayrılmış olmalı.

Bu çapada mekanizma geçti (kOmegaSST zaman-çözünür çevrimde koştu, salınım ve
y⁺ ölçüldü) ama fizik kalmadı (St deneysel platonun %37 üstünde). İkisini tek
cümlede birleştirmek her iki yönde de yanıltır; bu dosya ayrımı kilitler.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "experiments"))
sys.path.insert(0, str(KOK))

KANIT = KOK / "silindir_urans.json"


@pytest.fixture(scope="module")
def kanit() -> dict:
    if not KANIT.exists():
        pytest.skip("silindir_urans.json yok — python experiments/silindir_urans.py")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_verdikt_mekanizma_ve_fizigi_AYIRIR(kanit):
    v = kanit["verdikt"]
    assert "MEKANİZMA" in v and "FİZİK" in v


def test_mekanizma_gecti_fizik_kaldi(kanit):
    v = kanit["verdikt"]
    assert "✅ MEKANİZMA" in v, "türbülans modeli zaman-çözünür çevrimde koştu"
    assert "❌ FİZİK" in v, "St deneysel platonun dışında"


def test_yplus_duvar_fonksiyonu_bandinda(kanit):
    """Duvar işlemi İDDİA değil ÖLÇÜM olmalı."""
    yp = kanit["olculen"]["yplus"]
    assert yp is not None, "y⁺ ölçülmedi — duvar işlemi iddiası doğrulanmamış"
    assert 30.0 <= yp["ort"] <= 300.0, yp


def test_iki_sapmanin_yonu_tutarli(kanit):
    """2B kurulumun imzası: iz daralır → Cd DÜŞER, St YÜKSELİR.

    Yönler ters çıkarsa açıklama (span-yönü korelasyon kaybı) tutmaz ve
    rapordaki gerekçe kanıtla çelişir.
    """
    assert kanit["sapma_pct"]["St"] > 0
    assert kanit["sapma_pct"]["Cd"] < 0


def test_cd_capa_olarak_beyan_edilmiyor(kanit):
    tip = kanit["referans"]["Cd_tipi"]
    assert "EĞİLİM" in tip.upper()


def test_model_form_tablosuna_GIRMEZ():
    """Zaman-çözünür 2B vaka model-form hücresi doldurmamalı."""
    mf = KOK / "model_form_bandi.json"
    if not mf.exists():
        pytest.skip("model_form_bandi.json yok")
    # HAM METINDE ARAMA YANLIS POZITIF VERIR: dosya artik "kalan hucre neden
    # kapanmadi" gerekcelerini de tasiyor ve orada silindir bir KARSI ORNEK
    # olarak geciyor ("laminer bir vaka bu hucreyi dolduramaz"). Aranan sey
    # capa LISTESINDE bir giris olup olmadigidir.
    d = json.loads(mf.read_text(encoding="utf-8"))
    adlar = [c["ad"].lower()
             for h in d["olculen_hucreler"].values()
             for islem in h.values()
             for c in islem.get("capalar", [])]
    adlar += [x["capa"].lower() for x in (d.get("atanamayan") or [])]
    assert not any("silindir" in a for a in adlar), adlar


def test_mesh_laminer_capadan_yeniden_kullaniliyor():
    """İskele tekrarı yok: aynı blockMesh iki çapayı da besler."""
    import silindir_urans
    import silindir_vorteks
    assert silindir_urans._blockmesh is silindir_vorteks._blockmesh
    assert silindir_urans._coeffs is silindir_vorteks._coeffs
