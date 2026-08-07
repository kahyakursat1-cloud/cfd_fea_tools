"""SIMP topoloji optimizasyonu çekirdek matematiği — saf-fonksiyon birim testleri
(ccx/CFD çalıştırmaz). Tek test-boşluğu olan modül (ADR-4 araç katmanı)."""
import numpy as np

from vehicle_topopt import RHO_MIN, _oc_update, _sens_filter, _stress_gate, _tet_volumes


def test_stress_gate_branches():
    """#2: kompliyans-körlük stres-kapısı — 5 dal. 'ag_marjinda' sonradan eklendi:
    TO gridinde okunan tepe gerilme yakınsamamıştır (topopt_bagimsiz_dogrulama)."""
    from vehicle_topopt import _ag_buyumesi
    esik = 1.5 * (1 + _ag_buyumesi()[0])
    assert _stress_gate({"emniyet_faktoru_temsili": esik * 1.1})["durum"] == "güvenli"
    assert _stress_gate({"emniyet_faktoru_temsili": 1.6})["durum"] == "ag_marjinda"
    assert _stress_gate({"emniyet_faktoru_temsili": 1.2})["durum"] == "marjinal"
    akma = _stress_gate({"emniyet_faktoru_temsili": 0.7})
    assert akma["durum"] == "akma_asildi" and "stress_topopt" in akma["mesaj"]
    assert _stress_gate({})["durum"] == "değerlendirilemedi"
    # temsili yoksa tepe-SF kullanilir (deger degil, KAYNAK testi)
    assert _stress_gate({"emniyet_faktoru": esik * 1.1})["durum"] == "güvenli"


def test_tet_volumes_unit_tet():
    # Birim tetrahedron hacmi = 1/6; iki tet → doğru ölçeklenir
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.0]])
    vol = _tet_volumes(P, np.array([[0, 1, 2, 3]]))
    assert np.isclose(vol[0], 1 / 6)
    P2 = np.vstack([P, [2, 0, 0]])                       # ikinci tet (kayık) yine 1/6
    vol2 = _tet_volumes(P2, np.array([[0, 1, 2, 3], [1, 4, 2, 3]]))
    assert np.allclose(vol2, [1 / 6, 1 / 6])


def test_oc_update_respects_volume_constraint():
    # OC: üniform duyarlılıkta hacim hedefe oturur, [RHO_MIN,1] sınırında
    n = 50
    rho = np.full(n, 0.5)
    sens = np.full(n, 1.0)                               # üniform → eşit muamele
    vol = np.full(n, 1.0)
    passive = np.zeros(n, bool)
    rho_new = _oc_update(rho, sens, vol, volfrac=0.4, passive=passive)
    assert (rho_new * vol).sum() <= 0.4 * vol.sum() + 1e-6   # hacim kısıtı tutuldu
    assert rho_new.min() >= RHO_MIN - 1e-9 and rho_new.max() <= 1.0 + 1e-9
    assert abs(rho_new.mean() - 0.4) < 0.06                  # üniform → ~volfrac


def test_oc_update_passive_stays_solid():
    n = 20
    passive = np.zeros(n, bool); passive[:5] = True
    rho_new = _oc_update(np.full(n, 0.5), np.full(n, 1.0), np.full(n, 1.0),
                         volfrac=0.5, passive=passive)
    assert np.allclose(rho_new[:5], 1.0)                 # pasif elemanlar katı kalır


def test_sens_filter_smooths_spike():
    # Duyarlılık filtresi (Sigmund): tek-eleman tepesi komşulara yayılır (yumuşar)
    cc = np.array([[float(i), 0, 0] for i in range(7)])  # 1B dizi, aralık 1
    rho = np.ones(7)
    sens = np.zeros(7); sens[3] = 10.0                    # ortada tepe
    out = _sens_filter(cc, rho, sens, rmin=1.5)
    assert out[3] < sens[3]                               # tepe düştü (yayıldı)
    assert out[2] > 0 and out[4] > 0                     # komşulara taştı
    assert np.all(out >= -1e-9)                          # üniform rho → negatif yok
