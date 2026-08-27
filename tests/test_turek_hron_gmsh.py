"""gmsh yolu: snappy'nin reddettiği ağ KURULABİLDİ.

BİR TAHMİN ÇÜRÜDÜ VE O TAHMİN BU OTURUMDA YAZILMIŞTI. Ağ kapısı snappy'nin
`empty` yamalı ağı reddettiğini ölçtü --- o kısım doğru. Ama rapora şu da
yazıldı: ``Turek-Hron için ağ elle `blockMeshDict` ile (silindir çevresinde
O-grid) kurulmalıdır ve bu ayrı, büyük bir iştir.'' Bu ÖLÇÜLMEMİŞ bir
kestirimdi ve olgu gibi yazılmıştı.

Üçüncü yol vardı ve depo onu zaten kullanıyordu: gmsh. Denendi, kapı
geçildi. Ders ağ hakkında değil: sınanmadan bir yol kapalı ilan edilirse,
kapanan yol o değil ONU DENEMEK olur.

İKİ SAYIM KUSURU DA BU YOLDA ÇIKTI ve ikisi de kendi kaydımdaydı:
  1. `getElementsByType` (elemanTag, düğümTag) döndürür; ikincisi
     sayılıyordu ve hekza 8 kat fazla görünüyordu. `checkMesh`in hücre
     sayısı YANINDA duruyordu, yani fark görülebilirdi.
  2. non-ortogonallik regex'i `checkMesh`in gerçek biçimini (`Max:`) değil
     `= ` biçimini arıyordu ve ÇARPIKLIK satırını yakalıyordu --- iki
     metrik aynı sayı görünüyordu.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_gmsh.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_gmsh.json yok "
                    "(python experiments/turek_hron_gmsh.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_KAPI_GECILDI_ve_ALANLAR_tutarli(kanit):
    assert kanit["kapi_gecildi"] == (kanit["yanlar_empty_kaldi"]
                                     and kanit["govde_yamasi_var"]
                                     and kanit["z_yonunde_tek_hucre"])
    if kanit["kapi_gecildi"]:
        assert "GEÇİLDİ" in kanit["verdikt"]


def test_HEKZA_SAYISI_checkMesh_ile_BIREBIR(kanit):
    """SAYIM KUSURU BURADAN GÖRÜLÜRDÜ. gmsh'in hekza sayısı ile OpenFOAM'ın
    hücre sayısı AYNI olmalı; ilk sürümde 265.344 vs 33.168 idi ve iki sayı
    kayıtta yan yana duruyordu."""
    if not kanit["msh"].get("uretildi"):
        pytest.skip("ağ üretilmedi")
    assert kanit["msh"]["hexa"] == kanit["checkMesh"]["hucre"], (
        f"gmsh {kanit['msh']['hexa']} hekza, checkMesh "
        f"{kanit['checkMesh']['hucre']} hücre --- sayım ayrışmış")


def test_NONORTHO_ve_SKEWNESS_AYRI_metrikler(kanit):
    """İkisi aynı çıkıyorsa regex yanlış satırı yakalıyordur --- tam olarak
    oldu (ikisi de 0,817578 görünüyordu)."""
    c = kanit["checkMesh"]
    if c.get("max_nonortho") is None or c.get("max_skewness") is None:
        pytest.skip("metrikler okunamadı")
    assert c["max_nonortho"] != c["max_skewness"], \
        "non-ortho ile skewness aynı — regex çarpıklık satırını yakalıyor"


def test_AG_deponun_KENDI_esiklerini_geciyor(kanit):
    """CLAUDE.md: maxNonOrthogonality < 70, maxSkewness < 4."""
    c = kanit["checkMesh"]
    if c.get("max_nonortho") is None:
        pytest.skip("kalite okunamadı")
    assert c["max_nonortho"] < 70.0
    assert c["max_skewness"] < 4.0
    assert c["mesh_ok"] is True


def test_TUM_HUCRELER_HEKZA(kanit):
    """Prizma kalırsa gmsh recombine tam başarılı olmamıştır ve ağ karışık
    olur --- kayıt bunu göstermeli."""
    if not kanit["msh"].get("uretildi"):
        pytest.skip("ağ üretilmedi")
    assert kanit["msh"]["prizma"] == 0, \
        f"{kanit['msh']['prizma']} prizma kaldı — recombine tam değil"


def test_BAYRAK_KALINLIGI_yeterince_COZULUYOR():
    """Bayrağın iki yüzü ayrı hücrelere düşmezse basınç FARKI kaybolur ve
    FSI anlamsızlaşır. Hücre boyu kalınlıktan TÜRETİLİR."""
    import turek_hron_gmsh as G
    assert G.H_GOVDE == G.BAYRAK_KALINLIK / G.BAYRAK_BASINA_HUCRE
    assert G.BAYRAK_BASINA_HUCRE >= 4, "bayrak kalınlığı yeterince bölünmüyor"


def test_YAMA_SINIFLANDIRMASI_KONUMDAN_etiketten_DEGIL():
    """OCC boolean sonrası etiket sırası kararlı değildir; sınıflandırma
    konuma bakmalı yoksa geometri az değişince sessizce kayar."""
    import inspect

    import turek_hron_gmsh as G
    src = inspect.getsource(G._yamalar)
    assert "getBoundingBox" in src
    assert "siralama" in src or "sırasına" in src


def test_Z_DUZLEM_TOLERANSI_MODELDEN_turetiliyor():
    """gmsh'in sınır kutusu ±1e-7 tolerans taşıyor; 1e-12 şart koşan ilk
    sürüm ön/arka yüzleri HİÇ bulamadı ve 2B'lik en baştan kayboldu."""
    import inspect

    import turek_hron_gmsh as G
    src = inspect.getsource(G.msh_yaz)
    assert "Z_DUZLEM_TOL" in src and "Z_KALINLIK" in src
    assert "1e-12" not in src.split("Z_DUZLEM_TOL")[1][:200]


def test_MSH_SURUMU_22(kanit):
    """`gmshToFoam` 4.x biçimini okumuyor ve arızası OKUNAKSIZ --- biçim
    uyuşmazlığını söylemiyor, ayrıştırıcı ortasında çöküyor."""
    import inspect

    import turek_hron_gmsh as G
    src = inspect.getsource(G.msh_yaz)
    assert "MshFileVersion" in src and "2.2" in src


def test_KISIT_AKIS_COZULMEDIGINI_soyluyor(kanit):
    assert "AKIS COZMEZ" in kanit["_kisit"]
    assert "ag-bagimsizligi SINANMADI" in kanit["_kisit"]


def test_RAPOR_CURUYEN_TAHMINI_isaretliyor(kanit):
    """Rapor 'elle blockMesh şart' diye yazmıştı; tahmin çürüdüyse metin
    bunu SÖYLEMELİ, sessizce silinmemeli."""
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists() or "gmsh" not in tex.read_text(encoding="utf-8"):
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    t = tex.read_text(encoding="utf-8")
    if kanit["kapi_gecildi"]:
        assert "ÇÜRÜDÜ" in t or "çürüdü" in t
        assert str(kanit["checkMesh"]["hucre"]) in t.replace(".", "")
