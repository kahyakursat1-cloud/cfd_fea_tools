"""Yapılamayan kontrol, yapılıp geçen kontrolle karıştırılmamalı.

`except Exception: pass` ile düşen bir çapraz-kontrol (iz-momentum Cd, y⁺ ölçümü) hiçbir
iz bırakmıyordu; rapor sessizce o bölümü atlıyor, mühendis "kontrol edildi ve sorun yok"
sanıyordu. Kaynak-düzeyi çapa: kontrol düştüğünde AÇIK uyarı üretilmeli.
"""
import inspect
from pathlib import Path

import vehicle_pipeline

ROOT = Path(__file__).resolve().parent.parent


def test_iz_momentum_dususu_uyari_uretir():
    src = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)
    assert "İz-momentum çapraz-kontrolü YAPILAMADI" in src
    # cd_wake None iken uyarı kolu bulunmalı (sessiz geçiş yok)
    i_kontrol = src.index("cd_wake is not None and cd")
    i_uyari = src.index("İz-momentum çapraz-kontrolü YAPILAMADI")
    assert i_uyari > i_kontrol


def test_yplus_olculemedi_uyari_uretir():
    src = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)
    assert "y⁺ ÖLÇÜLEMEDİ" in src


def test_sessiz_yutma_guven_kritik_yolda_sayilabilir():
    """Bilinçli `except: pass` sayısı artarsa bu test hatırlatır (bütçe çapası)."""
    src = (ROOT / "vehicle_pipeline.py").read_text(encoding="utf-8").splitlines()
    sessiz = sum(1 for i, s in enumerate(src[:-1])
                 if s.strip().startswith("except") and src[i + 1].strip() == "pass")
    assert sessiz <= 7, (f"vehicle_pipeline'da {sessiz} sessiz yutma var — yeni eklenen "
                          "her biri bir güven sinyalini yok edebilir; ya logla ya uyarı üret")
