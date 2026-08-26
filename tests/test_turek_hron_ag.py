"""Turek--Hron geometrisi: referans ÖNCE doğrulanır, sonra geometri.

BİR KUSUR ÖLÇÜM SIRASINDA ÇIKTI VE REFERANSTAYDI. Hacim denetimi %-0,098
sapma gösterdi ve ilk okumada geometri kuşkulu göründü. Ölçülünce sapmanın
kaynağı ANALİTİK FORMÜLÜN KENDİSİ çıktı: kod `daire + dikdörtgen` yazıyordu
ve yorumu ``örtüşme çıkarılarak'' diyordu --- ama kod bunu YAPMIYORDU.
Çemberin kiriş sağında kalan dairesel dilim iki kez sayılıyordu. Düzeltince
sapma %-0,007'ye indi ve kalan fark çemberin 200 kenarla ayrıklaştırılması
(doğru yön, doğru büyüklük).

Ders: yanlış bir referans, doğru bir geometriyi suçlar.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

import turek_hron_ag as G  # noqa: E402

KANIT = KOK / "turek_hron_ag.json"


def test_TUTTURMA_NOKTASI_cemberden_TURETILIYOR():
    """`x_bas` sabit yazılırsa bayrak silindire teğet değil KESİK durur ve
    aradaki yarık snappy'de hücreyle dolar."""
    xb = G.bayrak_bas_x()
    dy = G.BAYRAK_KALINLIK / 2
    r = math.hypot(xb - G.MERKEZ[0], dy)
    assert abs(r - G.YARICAP) < 1e-12, "tutturma noktası çember üstünde değil"
    assert abs(xb - 0.248990) < 1e-5


def test_KONTUR_KAPALI_ve_KENDINI_KESMIYOR():
    from shapely.geometry import Polygon
    p = Polygon(G.govde_kesiti())
    assert p.is_valid, f"kontur geçersiz: {p.is_valid_reason}"
    assert p.exterior.is_ring


def test_ANALITIK_REFERANS_ORTUSMEYI_cikariyor():
    """Referansın kendisi sınanır --- yanlış referans doğru geometriyi
    suçlar ve bu TAM OLARAK oldu."""
    xb = G.bayrak_bas_x()
    d = xb - G.MERKEZ[0]
    dilim = (G.YARICAP**2 * math.acos(d / G.YARICAP)
             - d * math.sqrt(G.YARICAP**2 - d**2))
    assert dilim > 0, "örtüşme dilimi pozitif olmalı"
    naif = (math.pi * G.YARICAP**2
            + (G.BAYRAK_SON_X - xb) * G.BAYRAK_KALINLIK) * G.Z_KALINLIK
    dogru = G._beklenen_hacim()
    assert dogru < naif, "örtüşme çıkarılmıyor"
    assert abs((naif - dogru) - dilim * G.Z_KALINLIK) < 1e-12


def test_ANALITIK_REFERANS_SHAPELY_ile_de_UYUSUYOR():
    """İki bağımsız yol: kapalı-form ve poligon alanı. Ayrışırlarsa hangisi
    doğru bilinemez, o yüzden ikisi de sınanır."""
    from shapely.geometry import Polygon
    alan = Polygon(G.govde_kesiti()).area
    bekl = G._beklenen_hacim() / G.Z_KALINLIK
    assert abs(alan - bekl) / bekl < 2e-3, \
        f"poligon alanı {alan:.6e}, kapalı-form {bekl:.6e}"


def test_CEMBER_AYRIKLASTIRMASI_HACMI_ALTTAN_yaklasiyor():
    """İç-teğet poligon çemberden KÜÇÜK alan verir --- sapmanın YÖNÜ
    bilinmeli, yoksa 'küçük fark' her yöne mazeret olur."""
    from shapely.geometry import Polygon
    alan = Polygon(G.govde_kesiti()).area
    bekl = G._beklenen_hacim() / G.Z_KALINLIK
    assert alan <= bekl, "poligon alanı analitikten BÜYÜK — yön yanlış"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_ag.json yok (python experiments/turek_hron_ag.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_STL_SU_GECIRMEZ_ve_HACIM_TUTUYOR(kanit):
    s = kanit["stl"]
    assert s["uretildi"] and s["su_gecirmez"], \
        "su-geçirmez değilse snappy gövde içi/dışı ayrımı yapamaz"
    assert abs(s["hacim_hatasi_pct"]) < 0.05, \
        f"hacim analitikten %{s['hacim_hatasi_pct']} sapıyor"


def test_STL_SINIRLARI_geometriyle_uyusuyor(kanit):
    """TOLERANS AYRIKLAŞTIRMADAN TÜRETİLİR, tahmin edilmez.

    Ilk surum 1e-6 yazdi ve dustu: olculen sapma 5,5e-6 idi. Sebep kusur
    degil GEOMETRI --- ic-teget poligonun en sol dugumu cemberin en sol
    noktasina denk gelmez, aradaki mesafe SAGITTA'dir:
        s = r (1 - cos(pi/N)) = 0,05 (1 - cos(pi/200)) = 6,2e-6
    Keyfi bir tolerans ya bunu reddeder ya da genisletilince gercek bir
    kaymayi da gecirir. Esik modelden gelir.
    """
    sagitta = G.YARICAP * (1 - math.cos(math.pi / G.CEMBER_N))
    tol = 2 * sagitta
    (x0, y0, z0), (x1, y1, z1) = kanit["stl"]["sinirlar"]
    assert abs(x0 - (G.MERKEZ[0] - G.YARICAP)) < tol
    assert abs(y0 - (G.MERKEZ[1] - G.YARICAP)) < tol
    # BAYRAK UCU ayriklastirmaya bagli DEGIL --- tam kose, tam deger.
    assert abs(x1 - G.BAYRAK_SON_X) < 1e-12
    assert abs(z1 - z0 - G.Z_KALINLIK) < 1e-12


def test_KISIT_AGIN_SINANMADIGINI_soyluyor(kanit):
    """En tehlikeli okuma: 'geometri hazır' = 'çapa koşulabilir'. Ağ adımı
    ayrıdır ve FSI çapasının gerçek kapısı odur."""
    assert "SINANMADI" in kanit["_kisit"]
    assert "AKIS COZMEZ" in kanit["_kisit"]
    assert "SINANMADI" in kanit["verdikt"] or "HENÜZ" in kanit["verdikt"]
    # REFERANS DEGERLERININ DOGRULANMADIGI da yazmali
    assert "DOGRULANMADI" in kanit["_kisit"]


def test_KESIT_bayragi_GERCEKTEN_iceriyor():
    """Kontur yalnız çember olsaydı hacim yine 'tutabilirdi' (referans da
    yanlışsa). Bayrağın varlığı ayrıca sınanır."""
    k = G.govde_kesiti()
    assert np.isclose(k[:, 0].max(), G.BAYRAK_SON_X), "bayrak ucu konturda yok"
    uc = k[np.isclose(k[:, 0], G.BAYRAK_SON_X)]
    assert len(uc) == 2, "bayrak ucu iki köşe olmalı"
    assert abs(abs(uc[0, 1] - uc[1, 1]) - G.BAYRAK_KALINLIK) < 1e-12
