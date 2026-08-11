"""A/B karşılaştırma: eşleşik band ORTAK model-form hatasını götürmeli.

Eski sürüm iki koşunun `u_toplam` (sayısal ⊕ model) bandını RSS'liyordu. Aynı
rejim + aynı duvar işlemindeki iki koşuda model-form hatası ORTAKTIR; iki kez
saymak farkı gizler ve hiçbir tasarım kararı ayırt edilemez hale gelir. Bu
dosya o ayrımı kilitler.
"""
from __future__ import annotations

import kosu_gecmisi


def _kosu(ad, cd, u_say, u_mod, tip="arac", duvar=True, kalite="standart"):
    return {"ad": ad, "cd": cd, "cl": 0.2, "ld": 5.0, "drag_N": cd * 100,
            "cells": 500_000, "yplus": 40.0, "tip": tip, "kalite": kalite,
            "hiz": 20.0, "duvar_cozunur": duvar,
            "u_sayisal_pct": u_say, "u_model_pct": u_mod,
            "u_pct": (u_say ** 2 + u_mod ** 2) ** 0.5}


def test_esles_ayni_rejim_ayni_duvar():
    a, b = _kosu("A", 0.30, 1.5, 12.0), _kosu("B", 0.33, 1.5, 12.0)
    esit, neden = kosu_gecmisi.esles(a, b)
    assert esit, neden


def test_esles_duvar_islemi_farkliysa_eslesmez():
    a = _kosu("A", 0.30, 1.5, 12.0, duvar=True)
    b = _kosu("B", 0.33, 1.5, 12.0, duvar=False)
    esit, neden = kosu_gecmisi.esles(a, b)
    assert not esit and "duvar" in neden


def test_esles_duvar_kaydi_yoksa_eslesmez():
    """Kayıt YOKLUĞU eşleşme sayılmaz — bilmemek, aynı olmak değildir."""
    a, b = _kosu("A", 0.30, 1.5, 12.0), _kosu("B", 0.33, 1.5, 12.0)
    b["duvar_cozunur"] = None
    esit, neden = kosu_gecmisi.esles(a, b)
    assert not esit and "kayıtlı değil" in neden


def test_eslesik_band_ortak_model_hatasini_goturur():
    """%10'luk gerçek fark: eşleşik bandla GÖRÜLÜR, eski toplam-bandla GİZLENİRDİ."""
    a, b = _kosu("A", 0.30, 1.5, 12.0), _kosu("B", 0.33, 1.5, 12.0)
    c = kosu_gecmisi.karsilastir(a, b)
    ay = c["ayirt_edilebilirlik"]
    assert ay["band_tipi"].startswith("eşleşik")
    assert ay["band_rss_pct"] < 3.0, "model-form hâlâ banda giriyor"
    assert "DIŞINDA" in ay["hukum"]
    # eski davranis: sqrt(12.09^2*2) = %17.1 -> %10'luk fark "ayirt edilemez"
    eski_band = (a["u_pct"] ** 2 + b["u_pct"] ** 2) ** 0.5
    assert ay["dCd_pct"] < eski_band


def test_eslesmemis_karsilastirmada_model_form_banda_girer():
    a = _kosu("A", 0.30, 1.5, 12.0, duvar=True)
    b = _kosu("B", 0.33, 1.5, 12.0, duvar=False)
    ay = kosu_gecmisi.karsilastir(a, b)["ayirt_edilebilirlik"]
    assert ay["band_tipi"].startswith("eşleşmemiş")
    assert ay["band_rss_pct"] > 15.0
    assert "İÇİNDE" in ay["hukum"]


def test_kalite_farkliysa_hukum_tasarim_farki_demez():
    """Fark bandın dışında olsa bile kaynağı karışıksa 'tasarım farkı' denemez."""
    a = _kosu("A", 0.30, 1.5, 12.0, kalite="hizli")
    b = _kosu("B", 0.33, 1.5, 12.0, kalite="hassas")
    ay = kosu_gecmisi.karsilastir(a, b)["ayirt_edilebilirlik"]
    assert "DIŞINDA" in ay["hukum"]
    assert "tasarım farkı" not in ay["hukum"]
    assert "karışık" in ay["hukum"]


def test_sayisal_band_yoksa_hukum_verilmez():
    a, b = _kosu("A", 0.30, 1.5, 12.0), _kosu("B", 0.33, 1.5, 12.0)
    b["u_sayisal_pct"] = None
    ay = kosu_gecmisi.karsilastir(a, b)["ayirt_edilebilirlik"]
    assert ay["band_rss_pct"] is None
    assert "HÜKÜM VERİLEMEZ" in ay["hukum"]


def test_cl_bandi_olculmus_sayilmaz():
    """Cl'ye Cd'nin bandını uygulamak ölçülmemişi ölçülmüş göstermek olur."""
    assert kosu_gecmisi.metrik_bandi("Cd") is not None
    assert kosu_gecmisi.metrik_bandi("Sürükleme (N)") is not None
    for m in ("Cl", "L/D", "y⁺ (gövde)", "Hücre"):
        assert kosu_gecmisi.metrik_bandi(m) is None, m


def test_satirlar_band_tasima_alanini_tasir():
    a, b = _kosu("A", 0.30, 1.5, 12.0), _kosu("B", 0.33, 1.5, 12.0)
    for s in kosu_gecmisi.karsilastir(a, b)["satirlar"]:
        assert "band_tasir" in s
