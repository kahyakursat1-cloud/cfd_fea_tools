"""construct2d_bridge.run_validation'ın üç kapısı.

Üçü de gerçek bir yanlış sonuçtan doğdu (NACA2412 2B çapası, ölçülen):
  1. Koşu 2000 iterasyonu doldurup durdu, p ilk-rezidüeli 4.1e-2'de SALINIYORDU
     (hedef 1e-6) — sonuç yine de `status: SUCCESS` dönüp Cl yayınlandı.
  2. Referans alan çağıranın verdiği fiziksel korddan (0.25) hesaplanıyordu, oysa
     grid BİRİM KORDLU — alan 4 kat küçük, Cl/Cd 4 kat şişik.
  3. Cl/Cd forces.dat'ın SON SATIRINDAN okunuyordu; kuvvet geçmişi ~500 iterasyonluk
     bir limit çevrimi gösteriyordu (Fy 0.95 → 0.12), yani tek anlık değer salınımın
     neresinde durulduğuna bağlıydı.
"""
from pathlib import Path

import pytest

pytest.importorskip("numpy")
from construct2d_bridge import _kord_span_olc, _yakinsama  # noqa: E402


def _log(case: Path, govde: str):
    case.mkdir(parents=True, exist_ok=True)
    (case / "log.run").write_text(govde)
    return case


def _rezidualler(degerler, alan="p"):
    return "".join(f"\nTime = {i}\n\nGAMG:  Solving for {alan}, "
                   f"Initial residual = {v:.6g}, Final residual = 1e-9, No Iterations 3\n"
                   for i, v in enumerate(degerler, 1))


def test_log_yoksa_YAKINSADI_DEMEZ(tmp_path):
    y = _yakinsama(tmp_path)
    assert y["yakinsadi"] is False and "log.run yok" in y["neden"]


def test_SIMPLE_converged_mesaji_taniniyor(tmp_path):
    c = _log(tmp_path / "a", _rezidualler([1e-3] * 30)
             + "\nSIMPLE solution converged in 412 iterations\n")
    assert _yakinsama(c)["yakinsadi"] is True


def test_iterasyon_dolduran_kosu_YAKINSAMIS_SAYILMAZ(tmp_path):
    """ASIL HATA: 'endTime'a ulaştı' ile 'yakınsadı' aynı şey değil."""
    c = _log(tmp_path / "b", _rezidualler([4.1e-2] * 40))
    y = _yakinsama(c)
    assert y["yakinsadi"] is False
    assert "endTime" in y["neden"]
    assert y["iterasyon"] == 40


def test_PLATO_yakalaniyor(tmp_path):
    """Rezidüel sabitse düşüş durmuştur — sabit nokta değil, limit çevrimi."""
    c = _log(tmp_path / "c", _rezidualler([4.0e-2, 4.1e-2] * 20))
    assert "p" in _yakinsama(c)["platoda"]


def test_DUSEN_rezidual_platoda_sayilmiyor(tmp_path):
    """Kapı yalnız platoyu işaretlemeli; gerçekten düşen koşuyu suçlamamalı."""
    c = _log(tmp_path / "d", _rezidualler([10 ** (-i / 5) for i in range(40)]))
    y = _yakinsama(c)
    assert y["platoda"] == []
    assert y["yakinsadi"] is False          # residualControl yine de tetiklenmedi


def test_kord_olcumu_polyMesh_yoksa_COKMEZ_ama_SESSIZ_de_kalmaz(tmp_path):
    o = _kord_span_olc(tmp_path)
    assert "olculemedi" in o and o["olculemedi"]
    assert "kord" not in o                  # uydurma deger dondurmuyor


def test_kord_olcumu_airfoil_yamasi_yoksa_SEBEBI_soyluyor(tmp_path):
    pm = tmp_path / "constant" / "polyMesh"
    pm.mkdir(parents=True)
    (pm / "boundary").write_text("FoamFile{}\n(\nfarfield{ type patch; nFaces 4; }\n)\n")
    o = _kord_span_olc(tmp_path)
    assert "airfoil" in o["olculemedi"]
