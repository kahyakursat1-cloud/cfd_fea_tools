"""`mesh_generator` geometri üreteçleri — %9 kapsamdaydı, NACA profili hiç doğrulanmamıştı.

Bu modül uçak geometrisinin KAYNAĞI: profil koordinatları yanlışsa tüm aerodinamik
sonuç yanlış olur ve hiçbir V&V kapısı bunu yakalayamaz (sayı fiziksel görünür, sadece
başka bir kanadın cevabıdır). Profil literatüre karşı çapalanır.
"""
import numpy as np
import pytest

from mesh_generator import MeshGenerator

# NACA0012 yarı-kalınlık ordinatları — Abbott & von Doenhoff, "Theory of Wing Sections"
NACA0012_REF = {0.0125: 0.01894, 0.05: 0.03555, 0.10: 0.04683, 0.20: 0.05737,
                0.30: 0.06002, 0.40: 0.05803, 0.60: 0.04580, 0.80: 0.02623,
                0.95: 0.00807}


def _ust_yuzey(m, p, t, n=200):
    prof = MeshGenerator._naca4_profile(m, p, t, n=n)
    return prof[:n, 0], prof[:n, 1]


def test_naca0012_literature_uyumlu():
    """Simetrik profil kalınlık dağılımı — en kötü sapma %1'in altında olmalı."""
    x, y = _ust_yuzey(0.0, 0.0, 0.12)
    for xr, yr in NACA0012_REF.items():
        yh = float(np.interp(xr, x, y))
        assert abs(yh - yr) / yr < 0.01, f"x/c={xr}: {yh:.5f} vs {yr:.5f}"


def test_simetrik_profil_kamburluksuz():
    x, yu = _ust_yuzey(0.0, 0.0, 0.12)
    prof = MeshGenerator._naca4_profile(0.0, 0.0, 0.12, n=200)
    yl = prof[200:, 1][::-1]
    assert np.allclose(yu, -yl, atol=1e-12), "simetrik profilde alt yüzey üstün aynası"


def test_maksimum_kalinlik_dogru_yerde():
    """NACA 4-haneli: maks kalınlık x/c=0.30'da, değeri t/2."""
    x, y = _ust_yuzey(0.0, 0.0, 0.12, n=400)
    i = int(np.argmax(y))
    assert 0.25 < x[i] < 0.35, f"maks kalınlık x/c={x[i]:.3f}"
    assert y[i] == pytest.approx(0.06, abs=0.001)


def test_kamburlu_profil_maks_kamburu_konumunda():
    """NACA2412: %2 kamburluk, x/c=0.4'te."""
    prof = MeshGenerator._naca4_profile(0.02, 0.4, 0.12, n=400)
    n = 400
    orta = (prof[:n, 1] + prof[n:, 1][::-1]) / 2      # kamburluk çizgisi
    x = prof[:n, 0]
    i = int(np.argmax(orta))
    assert orta[i] == pytest.approx(0.02, abs=0.002), f"maks kamburluk {orta[i]:.4f}"
    assert 0.35 < x[i] < 0.45, f"kamburluk konumu x/c={x[i]:.3f}"


def test_acik_firar_kenari_olculebilir():
    """NACA 4-haneli -0.1015 katsayısı AÇIK TE verir. Bu, prizma katmanının
    örülememesinin geometrik sebebi — büyüklüğü bilinmeli."""
    x, y = _ust_yuzey(0.0, 0.0, 0.12, n=400)
    te_yari = float(y[-1])
    assert te_yari > 0, "katsayı kapalı TE'ye çevrilmiş — katman davranışı değişir"
    assert 2 * te_yari == pytest.approx(0.00252, rel=0.05), "TE kalınlığı 0.25%c mertebesinde"


def test_profil_kapali_ve_burun_onde():
    """Kambur profilde üst yüzey hücum kenarını hafifçe SARAR (xu = x − yt·sinθ),
    bu yüzden x biraz negatif olabilir — doğru NACA davranışı, hata değil.
    Büyüklüğü ihmal edilebilir kalmalı (<%0.1 kord)."""
    prof = MeshGenerator._naca4_profile(0.02, 0.4, 0.12, n=100)
    assert prof.shape == (200, 2)
    assert -1e-3 < prof[:, 0].min() <= 0.0 + 1e-9
    assert prof[:, 0].max() == pytest.approx(1.0, abs=1e-3)
    # simetrik profilde sarma yok
    sim = MeshGenerator._naca4_profile(0.0, 0.0, 0.12, n=100)
    assert sim[:, 0].min() == pytest.approx(0.0, abs=1e-12)


def test_kalinlik_orani_olceklenir():
    for t in (0.06, 0.12, 0.18):
        _, y = _ust_yuzey(0.0, 0.0, t, n=300)
        assert y.max() == pytest.approx(t / 2, abs=0.002 * t / 0.12)


@pytest.mark.parametrize("n", [16, 64, 256])
def test_cozunurluk_degisimi_profili_bozmaz(n):
    """Panel sayısı değişince maks kalınlık kaymamalı (kosinüs dağılımı tutarlı)."""
    _, y = _ust_yuzey(0.0, 0.0, 0.12, n=n)
    assert y.max() == pytest.approx(0.06, abs=0.004)


# ── Döküntü temizliği ────────────────────────────────────────────────────────

def test_dokuntu_temizligi_sifir_alanli_parcalari_atar():
    """Ölçüldü (MiniHawk): üretilen STL 99 ayrık gövdeydi — gövde, kanat ve 96 adet
    tek-üçgenlik döküntü. Alan katkıları %0.0000 ama STL'i su-geçirmez olmaktan
    çıkarıp snappy'nin onlara yapışmasına yol açıyorlardı."""
    trimesh = pytest.importorskip("trimesh")
    from mesh_generator import _dokuntu_temizle

    saglam = trimesh.creation.box(extents=[1, 1, 1])
    dokuntu = trimesh.Trimesh(vertices=[[9, 9, 9], [9, 9, 9], [9, 9, 9]],
                              faces=[[0, 1, 2]], process=False)   # sıfır alan
    kirli = trimesh.util.concatenate([saglam, dokuntu])
    temiz = _dokuntu_temizle(kirli)

    assert len(temiz.faces) == len(saglam.faces), "döküntü atılmadı"
    assert temiz.area == pytest.approx(saglam.area, rel=1e-9), "gerçek alan kaybı"


def test_dokuntu_temizligi_gercek_geometriyi_korur():
    """İki meşru gövde (uçak + kanat) atılmamalı — eşik ORANSAL."""
    trimesh = pytest.importorskip("trimesh")
    from mesh_generator import _dokuntu_temizle

    a = trimesh.creation.box(extents=[1, 1, 1])
    b = trimesh.creation.box(extents=[0.2, 0.2, 0.2])
    b.apply_translation([5, 0, 0])
    birlesik = trimesh.util.concatenate([a, b])
    temiz = _dokuntu_temizle(birlesik)
    assert len(temiz.faces) == len(birlesik.faces)


def test_dokuntu_temizligi_tek_parcada_dokunmaz():
    trimesh = pytest.importorskip("trimesh")
    from mesh_generator import _dokuntu_temizle
    m = trimesh.creation.box(extents=[1, 1, 1])
    assert len(_dokuntu_temizle(m).faces) == len(m.faces)


def test_uretilen_stl_dokuntusuz():
    """generate_stl artık temizlenmiş geometri yazmalı (regresyon çapası)."""
    trimesh = pytest.importorskip("trimesh")
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "vehicle_runs" / "minihawk_temiz.stl"
    if not p.exists():
        pytest.skip("temiz STL üretilmemiş")
    m = trimesh.load(p, force="mesh")
    kucuk = [x for x in m.split(only_watertight=False) if len(x.faces) <= 2]
    assert not kucuk, f"{len(kucuk)} döküntü parça kaldı"


# ── Kanat profili gerçekten üretiliyor mu ────────────────────────────────────

def test_kanat_kutuya_dusmuyor():
    """shapely kurulu değilken NACA ekstrüzyonu `except Exception` ile yutuluyor ve
    kanat 12 üçgenlik DÜZ KUTUYA düşüyordu — tüm aerodinamik sonucu geçersizleyen
    sessiz gerileme. Artık kaydediliyor ve bağımlılıklar doctor'da."""
    pytest.importorskip("shapely")
    pytest.importorskip("mapbox_earcut")
    from aircraft_geometry import AircraftLibrary
    from mesh_generator import MeshGenerator

    g = MeshGenerator(AircraftLibrary().minihawk_uav())
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        g.generate_stl(str(Path(d) / "u.stl"))
    assert g.gerilemeler == [], f"geometri gerilemesi: {g.gerilemeler}"


def test_profil_ekstruzyonu_watertight_kanat_uretir():
    """Shapely hücum kenarındaki çakışan noktayı birleştirir; n GİRDİ profilinden
    alınırsa column_stack ValueError atar ve kanat kutuya düşerdi (off-by-one)."""
    pytest.importorskip("shapely")
    pytest.importorskip("mapbox_earcut")
    prof = MeshGenerator._naca4_profile(0.02, 0.4, 0.12, n=48)
    # Ornek uzerinden cagriliyor: kapak orme duserse gerileme KAYDEDILMELI ve o
    # kanal ornege ait. Eskiden staticmethod'du ve dususe sessiz kaliyordu.
    from aircraft_geometry import AircraftLibrary
    g = MeshGenerator(AircraftLibrary().minihawk_uav())
    w = g._extrude_profile_to_mesh(prof, 0.0, 0.75, 0.25, 0.175, 0.28, 0.30)
    assert w.is_watertight, "kesit kapakları oluşmamış (mapbox_earcut?)"
    d = w.bounds[1] - w.bounds[0]
    assert d[2] / d[0] == pytest.approx(0.12, abs=0.01), "profil kalınlık/kord NACA'ya uymuyor"
    assert w.volume > 0
    assert g.gerilemeler == [], "başarılı ekstrüzyonda gerileme kaydedilmemeli"


def test_gerileme_kaydi_bos_baslar():
    from aircraft_geometry import AircraftLibrary
    from mesh_generator import MeshGenerator
    assert MeshGenerator(AircraftLibrary().minihawk_uav()).gerilemeler == []


def test_uretilen_ucak_watertight():
    """DÖRDÜNCÜ sessiz bağımlılık: manifold3d yoksa trimesh.boolean.union düşüyor ve
    kanat/gövde/kuyruk AYRI cisim kalıyordu → STL su-geçirmez değil, snappyHexMesh iç
    yüzey/kaçak görüyordu. 'Geometri düzeltici gerekli' sanılan sorun buydu."""
    pytest.importorskip("manifold3d")
    pytest.importorskip("shapely")
    trimesh = pytest.importorskip("trimesh")
    import tempfile
    from pathlib import Path

    from aircraft_geometry import AircraftLibrary
    from mesh_generator import MeshGenerator
    g = MeshGenerator(AircraftLibrary().minihawk_uav(), mesh_size=0.01)
    with tempfile.TemporaryDirectory() as d:
        m = trimesh.load(g.generate_stl(str(Path(d) / "u.stl")), force="mesh")
    assert g.gerilemeler == [], f"geometri gerilemesi: {g.gerilemeler}"
    assert m.is_watertight, "gövdeler birleşmemiş (boolean union düşmüş olabilir)"
    assert m.volume > 0


def test_boolean_dususu_sessiz_degil():
    """Birleşim düşerse kayıt tutulmalı — 'üretildi' ile 'birleşti' aynı şey değil."""
    import inspect

    from mesh_generator import MeshGenerator
    src = inspect.getsource(MeshGenerator.generate_stl)
    i = src.index("boolean.union")
    assert "KATI BİRLEŞİM DÜŞTÜ" in src[i:i + 900]
    assert "manifold3d" in src[i:i + 900], "eksik bağımlılık adlandırılmalı"
