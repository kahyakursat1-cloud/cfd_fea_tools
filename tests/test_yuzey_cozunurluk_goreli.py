"""Yüzey çözünürlük ölçütü GEOMETRİYE GÖRELİ — sabit yüz sayısı kaba bir ölçüttü.

500 yüzlük tek eşik, aynı sayıyı 4 m'lik kanada da 4 cm'lik fine de uygular:
büyük gövdede fazlasıyla gevşek, küçük özellikte anlamsızdır. Ölçüt artık tipik
yüzey hücresini (h=√(A/N)) en küçük geometrik özellikle karşılaştırır.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from analysis.openfoam_runner import (  # noqa: E402
    OZELLIK_BASINA_HUCRE,
    YUZEY_YUZ_ESIGI,
    yuzey_cozunurluk_hukmu,
)


def test_mutlak_taban_korundu():
    assert yuzey_cozunurluk_hukmu("temiz", 216)["cozuldu"] is False
    assert yuzey_cozunurluk_hukmu("temiz", 1704)["cozuldu"] is True


def test_taban_ustunde_ama_ozelligi_cozemeyen_mesh_ISARETLENIR():
    """Eski kapının GÖRMEDİĞİ sınıf: 2000 yüz > 500 ama 2 mm'lik firar kenarı
    yanında yüzey hücresi 22 mm — özellik geometrik olarak YOK. Ölçüm yapılır
    ve hüküm yazılır; koşu REDDEDİLMEZ (bkz. test_ince_ozellik_engelleyici_degil)."""
    h = yuzey_cozunurluk_hukmu("temiz", 2000, en_kucuk_boyut_m=0.002,
                               yuzey_alani_m2=1.0)
    gr = h["geometri_goreli"]
    assert gr["uygulandi"] is True
    assert gr["ozellik_cozuldu"] is False
    assert gr["ozellik_basina_hucre"] < OZELLIK_BASINA_HUCRE
    assert "COZULMEDI" in gr["hukum"]


def test_ince_ozellik_engelleyici_degil():
    """1 mm firar kenarına 4 hücre = 0.7 m kanatta ~13M yüz. Engelleyici yapmak
    her ince-kesitli koşuyu reddeder ve kapı bilgi TAŞIMAZ hale gelirdi."""
    h = yuzey_cozunurluk_hukmu("temiz", 24_477, en_kucuk_boyut_m=0.001188,
                               yuzey_alani_m2=1.1377)
    assert h["cozuldu"] is True                      # engellemiyor
    assert h["geometri_goreli"]["ozellik_cozuldu"] is False   # ama saklamiyor


def test_ozelligi_cozen_mesh_gecer():
    alan, ozellik = 1.0, 0.05
    h_gereken = ozellik / OZELLIK_BASINA_HUCRE
    n = int(math.ceil(alan / h_gereken ** 2)) + 10
    h = yuzey_cozunurluk_hukmu("temiz", n, en_kucuk_boyut_m=ozellik,
                               yuzey_alani_m2=alan)
    assert h["cozuldu"] is True
    assert h["geometri_goreli"]["ozellik_cozuldu"] is True
    assert h["geometri_goreli"]["gereken_yuz"] <= n


def test_ayni_yuz_sayisi_farkli_geometride_farkli_hukum():
    """Ölçütün göreli olmasının tüm anlamı bu: sayı aynı, hüküm farklı."""
    n = 20_000
    buyuk = yuzey_cozunurluk_hukmu("temiz", n, en_kucuk_boyut_m=0.20,
                                   yuzey_alani_m2=4.0)
    kucuk = yuzey_cozunurluk_hukmu("temiz", n, en_kucuk_boyut_m=0.002,
                                   yuzey_alani_m2=4.0)
    assert buyuk["geometri_goreli"]["ozellik_cozuldu"] is True
    assert kucuk["geometri_goreli"]["ozellik_cozuldu"] is False


def test_geometri_verilmezse_olcum_YAPILMADI_yazilir():
    """Sessizce 'geçti' sayılmaz — zayıf ölçütle geçildiği söylenir."""
    h = yuzey_cozunurluk_hukmu("temiz", 1704)
    assert h["cozuldu"] is True
    assert h["geometri_goreli"]["uygulandi"] is False
    assert "YAPILMADI" in h["geometri_goreli"]["neden"]


def test_butce_acligi_hala_tek_basina_reddeder():
    log = "No cells marked for refinement since reached limit 2500000\n" * 2
    h = yuzey_cozunurluk_hukmu(log, 50_000, en_kucuk_boyut_m=0.005,
                               yuzey_alani_m2=1.0)
    assert h["cozuldu"] is False
    assert any("butcesini TUKETTI" in g for g in h["gerekce"])


def test_arac_hatti_geometriyi_GERCEKTEN_geciriyor():
    """Ölçütü göreli yapmak, çağıran geometriyi geçirmezse hiçbir şey değiştirmez.
    (`en_kucuk_boyut_m` imzada zaten vardı ve gövdede HİÇ kullanılmıyordu.)"""
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    i = src.index("_yc = yuzey_cozunurluk_hukmu(")
    cagri = src[i:i + 400]
    assert "en_kucuk_boyut_m=" in cagri
    assert "yuzey_alani_m2=geo" in cagri
    assert YUZEY_YUZ_ESIGI == 500


def test_kosu_arsivinde_olculdu():
    """Ölçümün SONUCU: arşivde hangi koşuda hangi özellik temsil edilmiyor."""
    import json
    d = json.loads((KOK / "yuzey_ozellik_cozunurlugu.json").read_text(encoding="utf-8"))
    olculen = [k for k in d["kosular"] if k["olculebildi"]]
    assert len(olculen) >= 10
    cozulmeyen = [k["kosu"] for k in olculen if k["ozellik_cozuldu"] is False]
    assert "minihawk" in cozulmeyen, "ince firar kenarı çözülmemiş olmalı"
    assert any(k["ozellik_cozuldu"] for k in olculen), "hepsi başarısız olamaz"
