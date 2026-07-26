"""Fizik kapısı, kuvvet katsayısı ÜRETEN her yolda bulunmalı.

Kapının değeri kapsamıyla orantılı: gate'siz tek bir akış, mühendise hükümsüz bir Cd
verir. Bu test yeni bir çıktı yolu eklendiğinde (veya mevcut biri kapıyı kaybettiğinde)
kırılır — kaynak-düzeyi çapa, çözücü gerektirmez.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Kuvvet katsayısı üretip kullanıcıya/JSON'a veren modüller
KAPI_ZORUNLU = [
    "vehicle_pipeline.py",     # headless araç akışı
    "vehicle_polar.py",        # polar taraması (eğri uydurma)
    "vehicle_report.py",       # mühendisin okuduğu rapor
    "app_analyzer.py",         # GUI rozeti
    "report_generator.py",     # ASME V&V raporu
    "run_aoa_polar.py",        # 3D stall polar (standalone)
    "transition_polar.py",     # 2D geçiş polar (standalone)
    "supersonic_cfd.py",       # süpersonik Cd (standalone)
]


@pytest.mark.parametrize("dosya", KAPI_ZORUNLU)
def test_modul_fizik_kapisini_kullanir(dosya):
    src = (ROOT / dosya).read_text(encoding="utf-8")
    assert "force_admissibility" in src or "sonuc_kapisi" in src or "apply_physics_gate" in src, (
        f"{dosya} kuvvet katsayısı üretiyor ama fizik kapısından geçmiyor — "
        "validity_envelope.force_admissibility kullan")


def test_kapi_tek_kaynakta():
    """Kapı mantığı kopyalanmamalı; tanım YALNIZ validity_envelope'ta olmalı."""
    tanim = [p.name for p in ROOT.glob("*.py")
             if "def force_admissibility" in p.read_text(encoding="utf-8")]
    assert tanim == ["validity_envelope.py"], f"kapı çoğaltılmış: {tanim}"


def test_esikler_tek_kaynakta():
    """Mesh/yakınsama eşikleri de tek kaynakta tanımlı olmalı."""
    tanim = [p.name for p in list(ROOT.glob("*.py")) + list((ROOT / "analysis").glob("*.py"))
             if "NONORTHO_LIMIT =" in p.read_text(encoding="utf-8")]
    assert tanim == ["thresholds.py"], f"eşik çoğaltılmış: {tanim}"
