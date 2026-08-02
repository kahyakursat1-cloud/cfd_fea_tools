"""SINIRLAYAN band: salınımlı ≥3 seviye için ekstrapolasyonsuz kabul yolu.

Kabul hiyerarşisi yalnız EKSTRAPOLE EDEN yolları tanıyordu (asimptotik GCI,
≥4-seviye LSR). Salınımlı üçlü hiçbirine girmiyor ve "mesh-bağımsızlığı
gösterilemedi" oluyordu — değerler birbirine çok yakınken bile.

ÖLÇÜLDÜ (disk çapası): 66.858 / 203.798 / 648.569 hücrede Cd = 1.2049 / 1.19256 /
1.20956. On kat hücre aralığında saçılma %1.4; h oranları 1.450 ve 1.471.
Bant U = 3·Δ_M = %4.22, Hoerner'a sapma %3.38 → sapma bandın İÇİNDE.

Bu "yakınsamış değer" kanıtı DEĞİL, SINIRLAMA kanıtıdır — ve çapanın işi budur.
"""
import validate_pipeline as vp

_DISK = [{"cells": 66858, "Cd": 1.2049},
         {"cells": 203798, "Cd": 1.19256},
         {"cells": 648569, "Cd": 1.20956}]


def test_OLCULEN_disk_serisi_bandi():
    b = vp._sinirlayan_band(_DISK)
    assert b is not None
    assert abs(b["u_pct"] - 4.22) < 0.05
    assert b["r_min"] >= 1.3 and b["n"] == 3
    assert b["f"] == 1.20956                       # EKSTRAPOLASYON YOK


def test_disk_artik_KABUL_ediliyor():
    ok, cd, yontem = vp._accept({}, None, None, 1.20956, None, _DISK)
    assert ok is True and cd == 1.20956
    assert "SINIRLAYAN" in yontem and "ekstrapolasyon YOK" in yontem


def test_SIKISIK_seviyeler_sahte_dar_band_uretemiyor():
    """r<1.3'te küçük Δ sahte-dar bant verir; küpte ölçülmüştü (r=1.076 → p=-2.338)."""
    sikisik = [{"cells": 1_000_000, "Cd": 1.000},
               {"cells": 1_150_000, "Cd": 1.002},
               {"cells": 1_300_000, "Cd": 1.001}]
    assert vp._sinirlayan_band(sikisik) is None
    ok, _, _ = vp._accept({}, None, None, 1.001, None, sikisik)
    assert ok is False


def test_GENIS_band_kabul_edilmiyor():
    """Bant model-öncülünden dar olmalı; değilse çapa model hatasını ayırt edemez."""
    genis = [{"cells": 60000, "Cd": 1.00},
             {"cells": 200000, "Cd": 1.40},
             {"cells": 650000, "Cd": 1.10}]
    b = vp._sinirlayan_band(genis)
    assert b["u_pct"] > vp.LSR_U_MAX_PCT
    ok, _, _ = vp._accept({}, None, None, 1.10, None, genis)
    assert ok is False


def test_IKI_seviye_yetmiyor():
    assert vp._sinirlayan_band(_DISK[:2]) is None
    assert vp._sinirlayan_band(None) is None


def test_eksik_alan_bant_uretmiyor():
    assert vp._sinirlayan_band([{"cells": None, "Cd": 1.0}] * 3) is None
    assert vp._sinirlayan_band([{"cells": 1000, "Cd": None}] * 3) is None


def test_EKSTRAPOLE_eden_yollar_ONCE_geliyor():
    """Sınırlayan band SON çare olmalı: asimptotik GCI varsa o kullanılır."""
    gci = {"monotonic": True, "p_in_range": True, "gci_fine_pct": 1.0,
           "asymptotic": 1.02}
    ok, cd, yontem = vp._accept(gci, None, 1.1111, 1.10, None, _DISK)
    assert ok and cd == 1.1111 and "asimptotik" in yontem
