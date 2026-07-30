"""Prizma katman YIĞINI yerel kalınlığa sığmalı.

ÖLÇÜLEN ÇÖKME MEKANİZMASI (MiniHawk log.snappyHexMesh, kök-sebep düzeltmesinden
SONRA — yani yüzey artık 3060 yüzle iyi çözülmüşken):

    patch         faces  layers  near-wall  overall
    minihawk_prep 3060   12      4.84e-05   0.00263     <- snappy 12 katmani EKLEDI
    Detected 53939 illegal faces (concave, zero area or negative pyramid volume)
    Extruding 0 out of 3060 faces (0%). Removed extrusion at 1658 faces.

Ondan ÖNCEKİ ve SONRAKİ kalite kontrollerinde bozuk yüz 0 — mesh sağlam, bozulmayı
katman ekleme adımının KENDİSİ üretiyor. Aritmetik: istenen yığın 2.63 mm, firar
kenarı 1.19 mm. İnce özellikte katmanlar İKİ yüzeyden içeri büyür → her yakaya
0.595 mm kalır. 2.63 mm istemek katmanları çakıştırıp negatif hacim üretir.

Az katman istemek, çok katman isteyip HİÇ alamamaktan iyidir.
"""
import pytest

from vehicle_pipeline import katman_sayisi_sigdir


def test_MINIHAWK_VAKASI_12den_4e_dusuruluyor():
    r = katman_sayisi_sigdir(12, 4.84e-05, 0.00119)
    assert r["kisitlandi"] is True
    assert r["n"] == 4
    assert r["yigin_m"] <= r["sinir_m"]
    assert r["istenen_yigin_m"] == pytest.approx(0.00262, abs=5e-5)


def test_bol_yerde_DOKUNULMUYOR():
    r = katman_sayisi_sigdir(12, 4.84e-05, 0.05)
    assert r["kisitlandi"] is False and r["n"] == 12


def test_olculemezse_DOKUNULMUYOR_ama_SEBEBI_yazili():
    """Uydurma bir sınırla katman kırpmak, ölçmemekten kötüdür."""
    r = katman_sayisi_sigdir(12, 4.84e-05, None)
    assert r["kisitlandi"] is False and r["n"] == 12
    assert "ölçülemedi" in r["neden"]


def test_yigin_formulu_snappy_ile_TUTUYOR():
    """h1·(r^n−1)/(r−1); snappy logu 12 katman için 0.00263 m yazdı."""
    r = katman_sayisi_sigdir(12, 4.84e-05, 1.0)     # sinir bol -> yigin kirpilmaz
    assert r["kisitlandi"] is False
    assert r["yigin_m"] == pytest.approx(0.00263, abs=2e-5)


def test_cok_ince_ozellikte_sifira_kadar_inebilir():
    r = katman_sayisi_sigdir(12, 1e-4, 1e-5)
    assert r["n"] == 0 and r["kisitlandi"] is True


def test_gerekce_SAYILARLA_yazili():
    n = katman_sayisi_sigdir(12, 4.84e-05, 0.00119)["neden"]
    for parca in ("2.62 mm", "1.19 mm", "4 katmana"):
        assert parca in n, f"{parca} gerekcede yok"


def test_pipeline_SONUCA_bagliyor():
    """Ölçüm tüketilmezse sessiz kalır — bu oturumun tekrarlayan deseni."""
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    assert "katman_sayisi_sigdir" in src
    assert "katman_sigdirma" in src
    assert "KATMAN SAYISI SINIRLANDI" in src


def test_kisitlama_CFDCase_KURULMADAN_ONCE_uygulaniyor():
    """Sonradan uygulanırsa mesh yine 12 katmanla üretilir."""
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    assert src.index("katman_sayisi_sigdir") < src.index("case = CFDCase(")
