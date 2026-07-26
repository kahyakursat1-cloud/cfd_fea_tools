"""Polar taramasında tek fizik-dışı nokta eğri uydurmayı sessizce bozmamalı.

Mühendis lift eğimini ve L/D'yi polardan okur; kaba mesh'te bir α negatif Cd verirse
eğim yanlış çıkar ve hiçbir yerde uyarı görünmez. Kapı noktayı dışlar, gerekçesi tabloda
kalır (silinmez — dürüstlük).
"""
from pathlib import Path

import vehicle_polar
from validity_envelope import force_admissibility


def _satir(alpha, cd, cl):
    return {"alpha": alpha, "Cd": cd, "Cl": cl, "Cm": 0.0,
            "fizik": force_admissibility(cd, cl, alpha), "durum": "ok"}


def _out(rows):
    return {"status": "ok", "stl": "kanat.stl", "vehicle_type": "ucak", "velocity": 25.0,
            "aref_m2": 0.5, "cofr_notu": "test", "polar": rows}


def test_fizik_disi_nokta_egri_uydurmadan_dislanir(tmp_path):
    # α=-4 hem negatif Cd (fizik-dışı) hem de trendden sapan Cl taşıyor
    rows = [_satir(-4, -0.010, -0.90), _satir(0, 0.025, 0.00),
            _satir(4, 0.028, 0.40), _satir(8, 0.040, 0.80)]
    vehicle_polar._polar_report(_out(rows), tmp_path / "b")
    metin = (tmp_path / "b" / "POLAR.md").read_text(encoding="utf-8")
    assert "⛔ dışlandı" in metin
    assert "Fizik kapısı:" in metin and "α=-4°" in metin

    egim = float(metin.split("**Lift eğimi** ≈ ")[1].split("/°")[0])
    egim_dislanmis = (0.80 - 0.00) / (8 - 0)        # α=-4 hariç
    egim_dahil = (0.80 - (-0.90)) / (8 - (-4))      # α=-4 dahil olsaydı
    assert abs(egim - egim_dislanmis) < 1e-4
    assert abs(egim - egim_dahil) > 1e-3, "dışlanan nokta hâlâ eğime giriyor"
    # nokta tablodan SİLİNMEZ — mühendis neyin atıldığını görmeli
    assert "| -4 |" in metin


def test_saglikli_polar_kapiyi_tetiklemez(tmp_path):
    rows = [_satir(0, 0.025, 0.0), _satir(4, 0.028, 0.40), _satir(8, 0.040, 0.80)]
    metin = (Path(vehicle_polar._polar_report(_out(rows), tmp_path / "c") or
                  (tmp_path / "c" / "POLAR.md"))).read_text(encoding="utf-8")
    assert "⛔" not in metin and "Fizik kapısı:" not in metin
    assert metin.count("✅") == len(rows)


def test_kabul_yardimcisi():
    assert vehicle_polar._fizik_ok({"fizik": {"verdict": "ok"}})
    assert vehicle_polar._fizik_ok({})                      # eski kayıt -> hüküm yok
    assert vehicle_polar._fizik_ok({"fizik": {"verdict": "suspect"}})   # şüpheli dışlanmaz
    assert not vehicle_polar._fizik_ok({"fizik": {"verdict": "inadmissible"}})
