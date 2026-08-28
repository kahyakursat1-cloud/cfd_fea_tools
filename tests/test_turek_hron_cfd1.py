"""CFD1: akış çözüldü ve yayımlanmış bir referansa %1 içinde oturdu.

BİRİM TUZAĞI ÖLÇÜMÜN İÇİNDEN ÇIKTI ve sessizdi. İlk koşu sürüklemeyi
0,1428 N verdi, referans 14,29 --- %-99,0 sapma. ``Fizik yanlış'' gibi
görünüyordu; oysa oran TAM OLARAK 100 idi, yani $1/0{,}01$: 2B ağın z
kalınlığı. Çözücü o dilime ait kuvveti verir, Turek--Hron ise BİRİM DERİNLİK
başına yayımlar. Normalize edilince sapma %-0,05'e indi.

Bu tuzağın sinsi yanı, yanlış sonucun da ``makul'' görünmesidir: 0,1428 N
bir kuvvettir, negatif değildir, yakınsamıştır. Yalnız referansla
karşılaştırma açığa çıkardı --- ve karşılaştırma olmasaydı sayı
yayımlanabilirdi.

BU TESTLER SONUCU DEĞİL KURALI BAĞLAR: referans değişirse ya da ağ
inceltilirse düşmezler; düşmeleri için ya birim normalizasyonu kalkmalı ya
da kayıt kendi içinde çelişmeli.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_cfd1.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_cfd1.json yok "
                    "(python experiments/turek_hron_cfd1.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_REYNOLDS_benchmark_kosuluyla_ayni(kanit):
    """Re yanlışsa referansla karşılaştırma anlamsızdır."""
    k = kanit["kosul"]
    assert abs(k["Re"] - 20.0) < 1e-9, f"Re={k['Re']}, CFD1 20 ister"
    assert k["model"] == "laminer", "Re=20'de türbülans modeli yanlıştır"
    assert k["giris"] == "parabolik"


def test_BIRIM_NORMALIZASYONU_var_ve_OLCEK_dogru(kanit):
    """z kalınlığı KEYFİDİR; normalize edilmezse sapma tam olarak kalınlık
    çarpanı kadar çıkar (ölçüldü: 100 kat)."""
    kv = kanit["kuvvet"]
    if not kv.get("okundu"):
        pytest.skip("kuvvet okunamadı")
    assert kv["birim_derinlik_olcegi"] == pytest.approx(1.0 / kv["z_kalinlik_m"])
    assert kv["surukleme_N"] == pytest.approx(
        kv["ham_surukleme_N"] / kv["z_kalinlik_m"], rel=1e-12)
    assert "birim derinlik" in kv["_birim"]


def test_NORMALIZE_EDILMEMIS_deger_ile_ARADAKI_fark_KALINLIK_carpani(kanit):
    """Tuzağın imzası: ham/normalize oranı tam olarak 1/kalınlık. Bu
    ilişki bozulursa normalizasyon başka bir şey yapıyordur."""
    kv = kanit["kuvvet"]
    if not kv.get("okundu") or kv["ham_surukleme_N"] == 0:
        pytest.skip("kuvvet okunamadı")
    oran = kv["surukleme_N"] / kv["ham_surukleme_N"]
    assert oran == pytest.approx(1.0 / kv["z_kalinlik_m"], rel=1e-9)


def test_KOSU_YAKINSADI(kanit):
    r = kanit["rezidueller"]
    if not r.get("okundu"):
        pytest.skip("rezidüel okunamadı")
    assert r["yakinsadi"] is True, f"rezidüeller {r['son']}"


def test_REFERANSIN_DOGRULANMADIGI_KAYITTA(kanit):
    """En tehlikeli okuma: '%0,05 sapma' = 'doğrulandı'.

    CFD1'in referansı (sürükleme 14,29 / taşıma 1,119) bu depoda birincil
    kaynaktan TEYİT EDİLMEDİ --- FSI1/CSM referansları edildi, bu edilmedi
    ve ikisi karıştırılmamalı. Kısıt bunu söylemeli.

    ÖLÇÜT BİR KEZ BAYATLADI: eski hâli hükümde 'çapa değil' arıyordu ve
    ağ-bağımsızlığı ayrıca sınanınca o cümle kanıttan türetilir oldu.
    Test artık HÜKÜM METNİNE değil KISIT BEYANINA bağlanıyor --- proza
    değişebilir, beyan değişemez.
    """
    assert kanit["referans"]["_dogrulandi"] is False
    assert "BIRINCIL KAYNAKTAN DOGRULANMADI" in kanit["_kisit"]
    assert "CAPA DEGIL" in kanit["_kisit"]


def test_AG_BAGIMSIZLIGI_DURUMU_KANITTAN_TURETILIYOR(kanit):
    """Bu cümle bir turdur 'sınanmadı' diye SABİT yazılıydı ve aile onu
    kapatınca bayatladı; kıyaslama yöneticisi kaydı bayat işaretleyince
    ortaya çıktı. Artık kanıttan türetiliyor ve test iki ucu bağlar."""
    import json as _j
    aile = KOK / "turek_hron_ag_bagimsizligi.json"
    if not aile.exists():
        assert "SINANMADI" in kanit["verdikt"], (
            "aile koşulmamışken hüküm sınandığını ima ediyor")
        return
    d = _j.loads(aile.read_text(encoding="utf-8"))
    for deger in (d["surukleme"]["yayilim_pct"], d["tasima"]["yayilim_pct"]):
        assert str(deger) in kanit["verdikt"], (
            f"aile koşuldu ama {deger} hükme ulaşmıyor")


def test_CFD1_KUPLAJI_SINAMADIGINI_soyluyor(kanit):
    """CFD1 rijit bayrakla koşar; kuplaj hakkında hiçbir şey söylemez."""
    assert "kuplaji SINAMAZ" in kanit["_kisit"] or "kuplaji sinamaz" in kanit["_kisit"]


def test_SAPMA_kayitla_TUTARLI(kanit):
    """Sapma alanı elle yazılmış olsaydı ölçümle ayrışabilirdi."""
    kv, ref, s = kanit["kuvvet"], kanit["referans"], kanit["sapma"]
    if not kv.get("okundu"):
        pytest.skip("kuvvet okunamadı")
    beklenen = 100 * (kv["surukleme_N"] - ref["surukleme_N"]) / ref["surukleme_N"]
    assert s["surukleme_pct"] == pytest.approx(beklenen, abs=0.01)


def test_KUYRUK_BANDI_da_raporlaniyor(kanit):
    """Son satırı tek başına almak, yakınsamamış bir koşuda salınımın
    neresinde durulduğuna bağlıdır --- bu depo o dersi ödedi."""
    kv = kanit["kuvvet"]
    if not kv.get("okundu"):
        pytest.skip("kuvvet okunamadı")
    assert "surukleme_band_N" in kv and kv["kuyruk_ornek"] >= 3


def test_RAPOR_kanittan_sapmiyor(kanit):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "CFD1" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    kv, sp = kanit["kuvvet"], kanit["sapma"]
    for deger in (round(kv["surukleme_N"], 4), round(kv["tasima_N"], 4),
                  sp["surukleme_pct"], sp["tasima_pct"]):
        s = f"{deger}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"
    # BIRIM TUZAGI DERSI rapordan sessizce dusmemeli
    assert "birim derinlik" in t
    # "CAPA DEGIL" kaydi da durmali
    assert "çapa değil" in t or "bir eğilimdir" in t
