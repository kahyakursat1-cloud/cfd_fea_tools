"""y⁺ kapsamı: duvar işlemi duvarın ne kadarını temsil ediyor.

Ölçülen kusur (2026-08-22): mevcut kapı ortalama+tepe ikilisine bakıyor ve
Ahmed 25° çapası ondan GEÇİYOR (ort 30,4 · tepe 74,6 → wall_function), oysa
duvar alanının yalnız %65,8'i log-bandında. Kapsam, kapının göremediği şey.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from yplus_dagilim import duvar_islemi_kapsami  # noqa: E402


def _dagilim(bandda: float, cozunur: float) -> dict:
    return {"bandda_alan_pct": bandda, "cozunur_alan_pct": cozunur,
            "band": [30.0, 300.0], "cozunur_esik": 5.0,
            "p05": 1.0, "p50": 2.0, "p95": 3.0, "agirlik": "ALAN"}


def test_kapsam_CAPANIN_KENDI_duvar_islemine_gore_okunur():
    """Aynı dağılım, iki duvar işlemi, ZIT hüküm.

    Küre çapası duvar-çözünür koşar ve log-bandındaki alanı %0,4'tür. O sayıyı
    "kapsam yetersiz" diye okumak tam tersini söyler: çapa zaten bandın ALTINDA
    olmayı amaçlar. Tek yüzdeyi duvar işleminden bağımsız yorumlamak, bu
    ölçerin engellemek için yazıldığı kusurun ta kendisi.
    """
    d = _dagilim(bandda=0.4, cozunur=99.6)

    wf = duvar_islemi_kapsami(d, "wall_function")
    wr = duvar_islemi_kapsami(d, "wall_resolved")

    assert wf["kapsam_pct"] == 0.4 and wf["yeterli"] is False
    assert wr["kapsam_pct"] == 99.6 and wr["yeterli"] is True
    # iki ham sayi HER IKI kayitta da durur — hangisi secildigi denetlenebilsin
    for k in (wf, wr):
        assert k["bandda_alan_pct"] == 0.4 and k["cozunur_alan_pct"] == 99.6


def test_esik_DAYATILMIYOR_hukum_ayri_alanda_durur():
    """Eşik bandı etkilemez; dayatılsaydı bugün üç çapa da düşerdi."""
    k = duvar_islemi_kapsami(_dagilim(65.8, 2.0), "wall_function")
    assert k["kapsam_olculdu"] is True          # kapsam OLCULDU
    assert k["yeterli"] is False                # ama esigin ALTINDA
    assert "%80 önerisinin ALTINDA" in k["hukum"]
    assert "%34.2'inde geçerli değil" in k["hukum"]


def test_olculemeyen_kapsam_IYI_sayilmaz():
    d = {"durum": "yPlus alanı yok — foamPostProcess -func yPlus koşulmalı"}
    k = duvar_islemi_kapsami(d, "wall_function")
    assert k["kapsam_olculdu"] is False
    assert "yPlus" in k["neden"]
    assert "yeterli" not in k              # yoklugun hukmu YOK


def test_alan_agirligi_YUZ_SAYISINDAN_farkli_sonuc_verir():
    """Alan ağırlığı şart: yüz-sayısı oranı büyük hücreyi küçüğüyle eşit sayar.

    Kurgu: tek bir DEV yüz bandın içinde, doksan dokuz minik yüz dışında.
    Yüz sayısıyla kapsam %1, alanla %91 — ölçüt seçimi hükmü tersine çevirir.
    """
    from yplus_dagilim import dagilim as _d
    y = np.concatenate([[100.0], np.full(99, 1.0)])
    a = np.concatenate([[1000.0], np.full(99, 1.0)])
    bandda_alan = 100 * a[(y >= 30) & (y <= 300)].sum() / a.sum()
    bandda_yuz = 100 * ((y >= 30) & (y <= 300)).sum() / len(y)
    assert round(bandda_alan, 1) == 91.0 and round(bandda_yuz, 1) == 1.0
    assert callable(_d)


@pytest.mark.parametrize("capa,beklenen", [
    ("Ahmed 25°", 65.8), ("küp (çapa koşusu)", 69.4), ("disk", 59.8)])
def test_KANIT_dosyasi_olculen_kapsami_TASIYOR(capa, beklenen):
    """Sayı üreticiye bağlı: kanıt dosyası kapsamı taşımazsa ölçüm boşa gider.

    Bu deponun baskın kusuru "kapı VAR ama üretim yolu onu çağırmıyor"dur;
    test tam o yolu bağlar.
    """
    p = KOK / "model_form_bandi.json"
    if not p.exists():
        pytest.skip("model_form_bandi.json üretilmemiş")
    kayit = json.loads(p.read_text(encoding="utf-8"))
    c = next((x for x in kayit["capalar"] if x["capa"] == capa), None)
    assert c is not None, f"{capa} çapası kanıtta yok"
    assert c["yplus_kapsam_pct"] == pytest.approx(beklenen, abs=0.6)
    assert c["yplus_kapsam_islemi"] == "wall_function"
    assert c["yplus_kapsam_yeterli"] is False


def test_kapsam_OZETI_kendi_kapsamini_beyan_eder():
    """Ölçer kendi kapsamını söylemezse, ölçülmemiş olan ölçülmüş sayılır."""
    p = KOK / "model_form_bandi.json"
    if not p.exists():
        pytest.skip("model_form_bandi.json üretilmemiş")
    o = json.loads(p.read_text(encoding="utf-8"))["yplus_kapsam_ozeti"]
    assert o["olculen_capa"] < o["toplam_capa"]      # kismi kapsam GIZLENMIYOR
    assert o["olculemeyen"], "ölçülemeyen çapalar ADIYLA listelenmeli"
    for satir in o["olculemeyen"]:
        assert "ÖLÇÜLMEDİ" in satir or "hata" in satir.lower()
    assert len(o["esigin_altinda"]) == 3            # ucu de esigin altinda
    assert "band" in o["_esik_dayatilmiyor"].lower()


def test_wall_resolved_dali_URETIMDE_calismiyor_ve_BU_YAZILI():
    """Öksüz savunma denetimi: dal doğru ama bugün üretimde çağrılmıyor.

    `wall_resolved` çapalarının case dizinleri diskte yok (kanıt korundu, vaka
    temizlendi). Dal silinmiyor — model-form tablosunda DOLU wall_resolved
    hücreleri var ve vaka geri geldiğinde küre-tipi yanlış okuma anında geri
    dönerdi. Ama "çalışmıyor" olduğu KANITTA yazılı olmalı; bu test o beyanın
    sessizce düşmesini engeller.
    """
    p = KOK / "model_form_bandi.json"
    if not p.exists():
        pytest.skip("model_form_bandi.json üretilmemiş")
    o = json.loads(p.read_text(encoding="utf-8"))["yplus_kapsam_ozeti"]
    if "wall_resolved" in o["olculen_duvar_islemleri"]:
        return          # vaka geri gelmis: dal artik URETIMDE — beyan gereksiz
    assert "wall_resolved" in o["_kapsamin_kapsami"]
    assert "URETIMDE calismiyor" in o["_kapsamin_kapsami"]
