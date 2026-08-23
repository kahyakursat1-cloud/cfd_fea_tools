"""Girdi-UQ taraması ne ölçtü — null-değişken yöntemi ve hipotez elemesi.

LHS taraması Cd için %0,95 (2σ) band verdi; ikinci bağımsız tarama %0,89.
Sayı yinelenebilir --- ama bandın GİRDİLERDEN geldiği gösterilemedi ve
"u_girdi = %0,95" diye yayımlamak yanlış olurdu.

NULL DEĞİŞKEN YÖNTEMİ: taramaya, etkisi olamayacağı önceden bilinen iki girdi
kondu (küre için α, sabit-ν kabulüyle ρ) ve çalışma kendi kontrolüne döndü.
İkisi de gerçek değişkenle AYNI mertebede korelasyon gösterdi → ölçülen şey
girdi yanıtı değil.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from girdi_uq_teshis import kritik_r  # noqa: E402


def test_KRITIK_r_ORNEKLEM_BUYUKLUGUNE_bagli():
    """İlk sürüm n=30'un eşiğini (0,361) n=12'lik taramaya da uyguladı ve
    r=−0,55'i "anlamlı" saydı; n=12 için eşik 0,576'dır ve o korelasyon da
    anlamlı DEĞİLDİR. Eşik n'den bağımsız yazılırsa sınav sessizce yanlış
    hüküm verir.
    """
    assert kritik_r(30) == pytest.approx(0.361, abs=0.01)
    assert kritik_r(12) == pytest.approx(0.576, abs=0.02)
    assert kritik_r(12) > kritik_r(30), "küçük örneklem DAHA BÜYÜK eşik ister"


def test_KRITIK_r_cok_kucuk_orneklemde_hukum_vermiyor():
    assert kritik_r(3) >= 0.99


def test_HICBIR_korelasyon_ANLAMLI_degil():
    p = KOK / "girdi_uq_teshis.json"
    if not p.exists():
        pytest.skip("girdi_uq_teshis.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    t = d["null_degisken_yontemi"]["taramalar"]
    assert len(t) >= 2, "iki tarama da kayıtta olmalı"
    for x in t:
        assert x["anlamli_olan"] == [], (
            f"{x['tarama']}: {x['anlamli_olan']} anlamlı çıktı — bu doğruysa "
            f"teşhis yeniden yazılmalı")


def test_NULL_degiskenler_GERCEK_degiskenle_ayni_mertebede():
    """Yöntemin bütün gücü burada: null bir değişken gerçek değişkenle aynı
    korelasyonu gösteriyorsa, ölçülen şey girdi yanıtı DEĞİLDİR."""
    p = KOK / "girdi_uq_teshis.json"
    if not p.exists():
        pytest.skip("girdi_uq_teshis.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    nulls = set(d["null_degisken_yontemi"]["degiskenler"])
    assert nulls == {"rho", "alpha_deg"}
    for x in d["null_degisken_yontemi"]["taramalar"]:
        r = x["duyarlilik_pearson"]
        en_buyuk_null = max(abs(r[a]) for a in nulls if r.get(a) is not None)
        gercek = abs(r.get("velocity") or 0)
        assert en_buyuk_null >= 0.5 * gercek, (
            f"{x['tarama']}: null değişkenler gerçekten küçük çıkmış — "
            f"o zaman band girdi yanıtı OLABİLİR ve teşhis yenilenmeli")


def test_DORT_hipotezden_UCU_curudu():
    p = KOK / "girdi_uq_teshis.json"
    if not p.exists():
        pytest.skip("girdi_uq_teshis.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    h = d["hipotezler"]
    curuk = [x for x in h if x["sonuc"] == "ÇÜRÜDÜ"]
    destek = [x for x in h if x["sonuc"] == "DESTEKLENDİ"]
    assert len(curuk) >= 4, "eleme kaydı eksik"
    assert len(destek) == 1, "birden çok açıklama destekleniyorsa hüküm belirsiz"
    for x in h:
        assert x["sinav"] and x["olcum"], f"gerekçesiz hipotez: {x['hipotez']}"


def test_VERDIKT_UST_SINIR_diyor_girdi_duyarliligi_DEMIYOR():
    p = KOK / "girdi_uq_teshis.json"
    if not p.exists():
        pytest.skip("girdi_uq_teshis.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "ÜST SINIRDIR" in d["verdikt"]
    assert "ÖLÇÜLEMEDİ" in d["verdikt"]
    assert d["ne_gerekir"], "ne gerektiği yazılmamış"


def test_DESTEKLENEN_aciklama_KANITLANMIS_sayilmiyor():
    """"Yakınsamadan durma" desteklendi ama kanıtlanmadı: kesin sınav, tavanı
    yükseltip bandın çökmesini göstermektir ve o koşulmadı."""
    p = KOK / "girdi_uq_teshis.json"
    if not p.exists():
        pytest.skip("girdi_uq_teshis.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "KANITLANMADI" in d["_kisit"]


def test_TARAMA_CIKTISI_toleransi_adinda_TASIYOR():
    """İki çalışma birbirini ezdi (gevşek taramanın ham verisi kayboldu)."""
    import ast
    src = (KOK / "experiments" / "girdi_uq_kos.py").read_text(encoding="utf-8")
    assert "_cikti" in src
    agac = ast.parse(src)
    fon = [f for f in ast.walk(agac)
           if isinstance(f, ast.FunctionDef) and f.name == "_cikti"]
    assert fon, "çıktı adı toleranstan türetilmiyor"
    assert "cd_tol" in ast.dump(fon[0])
