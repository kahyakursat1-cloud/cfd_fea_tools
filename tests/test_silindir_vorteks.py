"""Silindir girdap dökülmesi çapası — zaman-çözünür yolun kanıtı.

v1.2'de URANS case yazıcısı ve frekans ölçümü eklendi ama ikisi de yalnız
SENTETİK sinyalde doğrulanmıştı. Bu çapa onları gerçek bir çözücü koşusunda
sınar ve DÖRT kusur ortaya çıkardı — hiçbirini sentetik test göremezdi:

  1. PIMPLE `pFinal` girdisi eksikti → ilk adımda FATAL IO ERROR
  2. Kaldırma yönü x-z düzleminde alınıyor; mesh x-y'deydi → Cl TAM SIFIR
  3. Simetrik kurulumda dökülme hiç başlamıyor → Cl genliği 1e-22
  4. Tek far-field yaması akımı sürdüremiyor → akış durdu, Cd negatife geçti

Testler kanıt dosyasının HÜKMÜNÜ bağlar, koşuyu tekrarlamaz (koşu ~4 dk).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "silindir_vorteks.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("silindir_vorteks.json yok (python experiments/silindir_vorteks.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_STROUHAL_deneye_yakin(kanit):
    """Williamson 1989: Re=100 için St=0,164. Bu, frekans ölçümünün BAĞIMSIZ
    doğrulamasıdır — sentetik sinyal kendi kendini doğrular, deney doğrulamaz."""
    st = kanit["olculen"]["St"]
    assert st is not None, "girdap dökülmesi ölçülemedi"
    assert abs(kanit["sapma_pct"]["St"]) < 10, f"St={st} vs 0.164"


def test_CD_literatur_mertebesinde(kanit):
    """Cd bağımsız bir çapraz kontroldür: frekans doğru ama kuvvet ölçeği
    yanlışsa kurulumda bir şey bozuktur (ilk raporda Cd 0,066 çıktı — A_ref
    ölçeği uygulanmamıştı)."""
    assert abs(kanit["sapma_pct"]["Cd"]) < 15, kanit["olculen"]


def test_AREF_olcegi_ACIKCA_yaziliyor(kanit):
    """Kanonik yazıcı Aref=lref² verir (3B bbox karesi); 2B silindirde doğru
    referans D×span'dır. Düzeltme sessiz kalırsa Cd yirmi kat yanlış olur ve
    kimse nedenini bilemez."""
    o = kanit["olculen"]
    assert o["_aref_olcegi"] == 20.0
    assert "D x span" in o["_aref_notu"]


def test_yeterli_PERIYOT_var(kanit):
    """Az periyotlu pencerede frekans istatistiği zayıftır."""
    assert kanit["salinim_olcumu"]["periyot_sayisi"] >= 10


def test_TEK_frekansli_oldugu_olculdu(kanit):
    """Re=100 dökülmesi tek frekanslıdır; saçılma büyükse medyan baskın modu
    temsil etmiyor demektir."""
    assert kanit["salinim_olcumu"]["periyot_sacilmasi_pct"] < 30


def test_kapsam_MODEL_FORM_degil_diyor(kanit):
    """Re=100 laminerdir: türbülans modeli yok. Bu vaka zaman ayrıklaştırmasını
    ölçer, model-form hatasını DEĞİL — ve model_form_bandi'ye çapa olarak
    girmemelidir."""
    k = kanit["_kapsam"]
    assert "LAMINER" in k.upper() and "MODEL-FORM" in k.upper()
    assert "GIRMEZ" in k.upper()


def test_capa_model_form_tablosuna_GIRMEDI():
    """Kapsam notu bir niyet beyanıdır; asıl kontrol tablonun kendisidir."""
    mf = KOK / "model_form_bandi.json"
    if not mf.exists():
        pytest.skip("model_form_bandi.json yok")
    d = json.loads(mf.read_text(encoding="utf-8"))
    adlar = " ".join(c.get("capa", "") for c in d.get("capalar", []))
    assert "silindir" not in adlar.lower()


def test_verdikt_SAYIYLA_gerekcelendiriliyor(kanit):
    v = kanit["verdikt"]
    assert str(kanit["olculen"]["St"])[:6] in v
    assert "Williamson" in v or "deney" in v


# ── Kurulumun kendisi: dört kusurun regresyonu ─────────────────────────────

def test_mesh_x_z_duzleminde():
    """Kaldırma yönü x-z'de alınıyor; mesh x-y'de olursa Cl TAM SIFIR çıkar."""
    import silindir_vorteks as sv
    bm = sv._blockmesh()
    satir = [s for s in bm.splitlines() if s.startswith("(") and s.count(" ") == 2]
    assert satir, "vertex bulunamadı"
    # kalinlik ekseni y: ikinci bilesen ±z/2 sabiti olmali
    ys = {abs(float(s.strip("()").split()[1])) for s in satir}
    assert len(ys) == 1, f"kalınlık ekseni y değil: {ys}"


def test_far_field_UCE_bolunmus():
    """Tek yama akımı sürdüremedi (ölçüldü: 0,074 m/s, Cd negatif)."""
    import silindir_vorteks as sv
    bm = sv._blockmesh()
    for yama in ("giris", "cikis", "ustalt"):
        assert f"  {yama}" in bm, f"{yama} yaması yok"
    assert "uzak" not in bm, "tek far-field yaması geri gelmiş"


def test_SIMETRI_KIRICI_var(tmp_path):
    """Simetrik kurulumda Kármán caddesi hiç doğmaz (ölçüldü: 50 s boyunca
    Cl genliği 1e-22)."""
    import silindir_vorteks as sv
    sv._alanlar(tmp_path)
    u = (tmp_path / "0" / "U").read_text(encoding="utf-8")
    ic = [s for s in u.splitlines() if s.startswith("internalField")][0]
    bilesen = ic.split("(")[1].split(")")[0].split()
    assert float(bilesen[2]) != 0.0, "çapraz bileşen yok — dökülme başlamaz"
