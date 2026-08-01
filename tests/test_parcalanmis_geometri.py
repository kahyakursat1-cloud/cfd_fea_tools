"""Parçalanmış geometri kapısı — snappyHexMesh bunu ZAMAN AŞIMIYLA öğretiyordu.

ÖLÇÜLDÜ (su57, DÖRT koşu boyunca aynı):
    ucgen 354.710  |  GOVDE SAYISI 1398  |  su gecirmez DEGIL
    snap asamasi: 310.719 bozuk yuz ("face pyramid volume < 1e-13")
    snappyHexMesh 30 dk sinirini doldurdu -> status=failed

Ölçek onarımı ÇALIŞMIŞTI (mm→m, 20812 mm -> 20.81 m) ama gövdeleri BİRLEŞTİRMEZ:
ham 1398 gövde, onarım sonrası da 1398.

Bu bir HÜCRE BÜTÇESİ sorunu DEĞİL. Önceki turda "su57 sınıfı araçlar bu makinede
analiz edilemez" demiştim — YANLIŞTI: sorun sınıfı değil, DOSYASI. Aynı boyutta
temiz bir gövde için bütçe hesabı bump=3'ü tractable gösteriyor.

VE ÖLÇÜM ZATEN VARDI: `prepare_geometry` govde_sayisi'ni satır 217'de hesaplıyor.
Hiçbir kapı onu tüketmiyordu — bu oturumda avlanan "ölçüm var, hükmü yok"
deseninin onuncu örneği.
"""
from validity_envelope import GOVDE_SAYISI_ESIGI, geometry_sanity

TEMEL = {"lmax_m": 20.8, "on_alan_m2": 50.0, "yan_alan_m2": 200.0,
         "planform_alan_m2": 180.0, "ucgen_sayisi": 354710, "su_gecirmez": True}


def _uyarilar(**k):
    return geometry_sanity({**TEMEL, **k}, "ucak", 15.0)


def _parcali(u):
    return [x for x in u if "PARÇALANMIŞ" in x]


def test_SU57_VAKASI_yakalaniyor():
    u = _parcali(_uyarilar(su_gecirmez=False, hazirlik={"govde_sayisi": 1398}))
    assert len(u) == 1
    assert "1398" in u[0] and "su geçirmez DEĞİL" in u[0]


def test_temiz_geometri_SESSIZ():
    assert _parcali(_uyarilar(hazirlik={"govde_sayisi": 2})) == []
    assert _parcali(_uyarilar(hazirlik={"govde_sayisi": 1})) == []


def test_esik_sinirinda():
    assert _parcali(_uyarilar(hazirlik={"govde_sayisi": GOVDE_SAYISI_ESIGI - 1})) == []
    assert _parcali(_uyarilar(hazirlik={"govde_sayisi": GOVDE_SAYISI_ESIGI})) != []


def test_su_gecirmez_olsa_bile_PARCALIYSA_uyariyor():
    """Kapali ama coklu kabuk da snappy icin sorunludur."""
    u = _parcali(_uyarilar(su_gecirmez=True, hazirlik={"govde_sayisi": 200}))
    assert len(u) == 1 and "su geçirmez DEĞİL" not in u[0]


def test_olcum_YOKSA_uydurma_uyari_URETMIYOR():
    assert _parcali(_uyarilar(hazirlik={})) == []
    assert _parcali(_uyarilar()) == []


def test_BUTCE_SORUNU_OLMADIGI_yaziyor():
    """Yanlis teshise yonlendirmemeli — bu hucre butcesiyle cozulmez."""
    u = _parcali(_uyarilar(su_gecirmez=False, hazirlik={"govde_sayisi": 1398}))[0]
    assert "hücre bütçesi sorunu DEĞİLDİR" in u
    assert "geometri onarımı" in u


def test_prepare_geometry_govde_sayisini_OLCUYOR():
    """Kapinin dayandigi olcum gercekten uretiliyor mu."""
    import inspect

    import vehicle_pipeline as vp
    assert "govde_sayisi" in inspect.getsource(vp.prepare_geometry)


def test_kapi_COZUCUDEN_ONCE_cagriliyor():
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    assert src.index("geometry_sanity(") < src.index("case = CFDCase(")
