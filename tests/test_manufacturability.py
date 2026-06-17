"""3D-baskı üretilebilirlik değerlendirmesi — saf-geometri birim testleri (solver yok)."""
import numpy as np

import manufacturability as mf


def test_overhang_predicate_flat_downface():
    # facet0: plakaya oturan alt yüzey (z=0, hariç), facet1: havada aşağı-bakan (z=1, ihlal)
    normals = np.array([[0, 0, -1.0], [0, 0, -1.0]])
    areas = np.array([1.0, 1.0])
    centroids = np.array([[0, 0, 0.0], [0, 0, 1.0]])
    assert mf._overhang_area_frac(normals, areas, centroids, (0, 0, 1)) == 0.5  # 1/2 alan


def test_overhang_vertical_wall_safe():
    # Dikey duvar (normal yatay, n·b=0) → asla overhang; alt-referans + duvar
    normals = np.array([[0, 0, -1.0], [1.0, 0, 0]])
    areas = np.array([1.0, 2.0])
    centroids = np.array([[0, 0, 0.0], [0, 0, 0.5]])     # duvar plakanın üstünde
    assert mf._overhang_area_frac(normals, areas, centroids, (0, 0, 1)) == 0.0


def test_overhang_45_threshold():
    # Alt-referans (plaka) + havada eğimli yüzey. 40° (sığ)→ihlal, 50° (dik)→güvenli
    plate_n, plate_c = [0, 0, -1.0], [0, 0, 0.0]
    a = np.radians(40)
    n = np.array([plate_n, [0, np.sin(a), -np.cos(a)]])  # n·ẑ=-cos40≈-0.766 < -0.707
    c = np.array([plate_c, [0, 0, 1.0]])
    assert mf._overhang_area_frac(n, np.array([1.0, 1.0]), c, (0, 0, 1)) == 0.5
    a2 = np.radians(50)
    n2 = np.array([plate_n, [0, np.sin(a2), -np.cos(a2)]])  # n·ẑ=-cos50≈-0.643 > -0.707
    assert mf._overhang_area_frac(n2, np.array([1.0, 1.0]), c, (0, 0, 1)) == 0.0


def test_recommend_orientation_picks_best():
    import trimesh
    # Üstü kapalı, altı açık bir "T" yerine basit: yatay bir tava (geniş düz plaka)
    # +z basılırsa alt yüzü overhang; yan (+x) basılırsa plaka dikleşir → az overhang
    box = trimesh.creation.box(extents=(1.0, 1.0, 0.05))
    box.apply_translation([0, 0, 2.0])             # plakadan yüksekte (oturmasın)
    best, scores = mf.recommend_orientation(box)
    # ince eksen (+z/−z) overhang'i yüksek; geniş yüzleri dikleştiren yön daha iyi
    assert scores[best] <= min(scores["+z"], scores["-z"]) + 1e-9


def test_assess_min_feature_flag():
    import trimesh
    box = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
    # kalın üye → basılabilir
    ok = mf.assess_manufacturability(box, rmin_m=2e-3)
    assert ok["min_uye_verdict"].startswith("✅")
    # ince üye (0.3 mm < 2×0.4 mm) → uyarı
    thin = mf.assess_manufacturability(box, rmin_m=3e-4)
    assert thin["min_uye_verdict"].startswith("⚠️")
    assert "overhang_orani" in ok and ok["onerilen_yon"] in mf.BUILD_AXES
