"""Ağ kapısı: bir yol KAPANDI ve bu kayıtta durmalı.

BULGU ARACIN KENDİSİNDEN GELDİ, bir ayar denemesinden değil:

    snappyHexMesh: "Mesh provided is not fully 3D as required for mesh
    relaxation after snapping. Convert all empty patches to appropriate
    types for a 3D mesh"

Yani bu depoda gövde-etrafı ağ kuran TEK yol (snappy) 2B vakada
KULLANILAMAZ. Turek--Hron için ağ elle `blockMeshDict` ile kurulmalı ve bu
ayrı, büyük bir iştir.

SONDANIN KENDİSİNDE DE BİR KUSUR ÇIKTI. İlk koşuda gerekçe BOŞ göründü:
komut çıktısını `> log.snappy` ile dosyaya yönlendiriyor, sonra `stdout`u
gerekçe diye yazıyorduk. OpenFOAM'ın FATAL ERROR'u log dosyasındaydı ve
kimse okumuyordu --- bu deponun tekrarlayan kusuru, bu kez sondanın
kendisinde: sebep VAR, tüketici YOK.

BU TESTLER BİR BAŞARISIZLIĞI PİNLEMİYOR. Kapı geçilirse (ör. blockMesh yolu
yazılırsa) testler DÜŞMEZ --- ölçüt, kaydın ölçümle tutarlı olmasıdır.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_ag_kapisi.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_ag_kapisi.json yok "
                    "(python experiments/turek_hron_ag_kapisi.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_TABAN_AG_gercekten_2B(kanit):
    """Kapının sınadığı şey 2B'lik; taban ağ 2B değilse soru anlamsız."""
    t = kanit["taban_ag"]
    assert t["nz"] == 1, "taban ağ z'de tek hücreli değil — kapı bir şey ölçmüyor"


def test_HUKUM_ile_ALANLAR_tutarli(kanit):
    """Verdikt ile yapısal alanlar ayrışmamalı; ayrışırsa hangisinin doğru
    olduğu bilinemez."""
    gecti = kanit["kapi_gecildi"]
    assert gecti == (kanit["yanlar_empty_kaldi"]
                     and kanit["govde_yamasi_var"]
                     and kanit["z_yonunde_tek_hucre"])
    if gecti:
        assert "GEÇİLDİ" in kanit["verdikt"]
    else:
        assert "GEÇİLMEDİ" in kanit["verdikt"] or "DÜŞTÜ" in kanit["verdikt"]


def test_GEREKCE_LOGTAN_okunuyor_BOS_degil(kanit):
    """İlk sürümde gerekçe boştu (stdout okunuyordu, log değil). Düşen bir
    adımın sebebi GÖRÜNMEZSE, kapı 'bir şey oldu' demekten öteye geçmez."""
    dusen = [a for a in kanit["kosu"].get("adimlar", []) if a["rc"] != 0]
    if not dusen:
        pytest.skip("hiçbir adım düşmedi")
    for a in dusen:
        assert len(a["kuyruk"].strip()) > 40, \
            f"{a['komut']} düştü ama gerekçe boş/kısa: {a['kuyruk']!r}"


def test_KOSUCU_LOG_dosyasini_GERCEKTEN_okuyor():
    """Kaynak denetimi: yönlendirme varsa log okunmalı. Kayıt bugün dolu
    olabilir ama kod yine stdout'a bakıyor olabilirdi."""
    import inspect

    import turek_hron_ag_kapisi as K
    src = inspect.getsource(K._kos)
    assert "read_text" in src and "log" in src
    assert "FOAM FATAL" in src, "FATAL ERROR bloğu aranmıyor"


def test_ARIZA_ADLANDIRILIYOR_ham_log_dokulmuyor(kanit):
    """Okur bir hüküm bekler. Ham log kayıtta zaten duruyor."""
    if kanit["kapi_gecildi"]:
        pytest.skip("kapı geçildi")
    v = kanit["verdikt"]
    if "not fully 3D" in json.dumps(kanit["kosu"], ensure_ascii=False):
        assert "ARACIN KENDİSİ" in v, "engel ayar mı araç mı, söylenmiyor"
        assert "blockMeshDict" in v, "alternatif yol adlandırılmıyor"
        # UCUNCU YOL (createPatch) da ELENMIS olmali --- yoksa okur onu
        # denemeye kalkar ve ayni duvara carpar.
        assert "createPatch" in v


def test_KISIT_AKIS_COZULMEDIGINI_soyluyor(kanit):
    assert "AKIS COZMEZ" in kanit["_kisit"]
    # AG KALITESI hukme sokulmuyor --- gecen bir ag iyi bir ag demek degil
    assert "iyi bir ag demek" in kanit["_kisit"]


def test_STL_KAPIDAN_ONCE_dogrulanmis():
    """Kapı geometriye dayanır; geometri doğrulanmamışsa kapı yanlış şeyi
    ölçer. İki kayıt AYRI ve sıralı."""
    g = KOK / "turek_hron_ag.json"
    if not g.exists():
        pytest.skip("geometri kanıtı yok")
    d = json.loads(g.read_text(encoding="utf-8"))
    assert d["geometri_dogru_mu"] is True, \
        "geometri doğrulanmadan ağ kapısı anlamsız"


def test_RAPOR_kapiyi_ve_GEOMETRIYI_kanittan_yaziyor(kanit):
    """Rapor bu ölçümü taşıyorsa kanıtla aynı olmalı --- ve engelin YERİNİ
    söylemeli: yetenek hazır, AĞ hazır değil."""
    tex = KOK / "docs" / "teknik_rapor.tex"
    g = KOK / "turek_hron_ag.json"
    if not (tex.exists() and g.exists()):
        pytest.skip("rapor ya da geometri kanıtı yok")
    t = tex.read_text(encoding="utf-8")
    if "Turek" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    d = json.loads(g.read_text(encoding="utf-8"))
    assert str(d["stl"]["ucgen"]) in t, "üçgen sayısı raporda yok"
    hata = f"{abs(d['stl']['hacim_hatasi_pct'])}".replace(".", "{,}")
    assert hata in t, f"hacim sapması ({hata}) raporda yok"
    if not kanit["kapi_gecildi"]:
        assert "fully 3D" in t, "aracın reddi raporda alıntılanmıyor"
        assert "blockMeshDict" in t
