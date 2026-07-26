"""Kullanıcı-yüzü hüküm rozeti — fizik yakınsamadan ÖNCE gelir.

GUI'nin 'verdict' rozeti eskiden yalnız iterasyon yakınsamasını gösteriyordu: negatif Cd
üreten bir koşu ekranda '✅ yakınsadı' diyordu. Bu testler öncelik sırasını çapalar.
"""
import pytest

from validity_envelope import force_admissibility, sonuc_kapisi

YAKINSADI = {"drift_ok": True, "rezidual_ok": True}


def test_fizik_disi_yakinsamayi_ezer():
    k = sonuc_kapisi(force_admissibility(-0.0036, 0.44, 4.0), YAKINSADI)
    assert k["seviye"] == "engel"
    assert "fizik-dışı" in k["etiket"]
    assert k["gerekce"] and "negatif" in k["gerekce"][0]


def test_supheli_uyari_seviyesi():
    k = sonuc_kapisi(force_admissibility(0.03, -0.4, 4.0), YAKINSADI)
    assert k["seviye"] == "uyari" and "şüpheli" in k["etiket"]


def test_saglikli_kosu_yakinsadi():
    k = sonuc_kapisi(force_admissibility(0.032, 0.44, 4.0), YAKINSADI)
    assert k == {"seviye": "ok", "etiket": "✅ yakınsadı", "gerekce": []}


def test_yakinsamayan_kosu_gerekce_verir():
    k = sonuc_kapisi({"verdict": "ok"}, {"drift_ok": False, "rezidual_ok": True})
    assert k["seviye"] == "uyari" and k["etiket"] == "⚠️ sınırda"
    assert "kuvvet drifti" in k["gerekce"][0]


def test_eksik_veri_cokmez():
    assert sonuc_kapisi(None, None)["seviye"] == "uyari"


def test_gui_rozeti_kapiyi_kullanir():
    """app_analyzer._on_done ham convergence yerine sonuc_kapisi'nı sürmeli."""
    import inspect

    pytest.importorskip("PySide6", reason="GUI yığını yok (CI) — kaynak denetimi atlanır")
    import app_analyzer
    src = inspect.getsource(app_analyzer.AnalyzerWindow._on_done)
    assert "sonuc_kapisi" in src
    assert 'kapi["etiket"]' in src
    assert "drift_ok" not in src, "rozet yakınsamayı doğrudan okumamalı — kapı üzerinden geçmeli"
