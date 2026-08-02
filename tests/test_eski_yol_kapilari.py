"""Eski motor (`simulation_runner`) artık araç hattının KAPILARINDAN geçiyor.

Bu yolda YALNIZ fizik kapısı vardı. "Cd fiziksel mi" sorusu, "Cd OTURDU MU" ve
"gövde ÇÖZÜLDÜ MÜ" sorularının yerine geçmez — MiniHawk vakasında ikincisinin
yokluğu y⁺≈5000'i ve %379'luk GCI'yı görünmez kılmıştı.

Tanımlar KOPYALANMIYOR: kanonik fonksiyonlar çağrılıyor. Günlük adları bu yolda
farklı (`log.solver`, `log.snappy`); sabit ad varsayımı rezidüelleri hiç
bulamayıp sessizce "yakınsamadı" derdi.
"""
import inspect
from pathlib import Path

import simulation_runner as sr

ROOT = Path(__file__).resolve().parent.parent


def test_kuvvet_TARIHCESI_tum_satirlardan():
    """Tek nokta yakınsama hakkında hiçbir şey söylemez; drift/salınım tarihçe ister."""
    satir = "0.1 ((1.0 0 2.0) (0.5 0 0.5)) ((0 1 0) (0 1 0))"
    h = sr._kuvvet_tarihcesi([satir] * 5, q=100.0, S=0.5)
    assert len(h) == 5 and len(h[0]) == 4
    assert abs(h[0][1] - (1.5 / 50.0)) < 1e-9        # Cd = (Fpx+Fvx)/(q·S)
    assert abs(h[0][2] - (2.5 / 50.0)) < 1e-9        # Cl = (Fpz+Fvz)/(q·S)


def test_bozuk_satir_tarihceyi_dusurmuyor():
    iyi = "0.1 ((1.0 0 2.0) (0.5 0 0.5)) ((0 1 0) (0 1 0))"
    h = sr._kuvvet_tarihcesi([iyi, "bozuk satir", iyi], q=100.0, S=0.5)
    assert len(h) == 2


def test_GUNLUK_ADI_acikca_geciliyor():
    """`log.solver` sabit ad varsayımıyla bulunamıyordu."""
    src = inspect.getsource(sr._kalan_kapilar)
    assert 'log_adi="log.solver"' in src
    assert '"log.snappy"' in src


def test_kanonik_fonksiyonlar_CAGRILIYOR_kopya_YOK():
    src = inspect.getsource(sr._kalan_kapilar)
    for ad in ("yakinsama_teshisi", "yuzey_cozunurluk_hukmu", "sonuc_kapisi"):
        assert ad in src, ad
    # kopya tanım işareti: bu dosyada bu isimlerde fonksiyon TANIMI olmamalı
    tam = (ROOT / "simulation_runner.py").read_text(encoding="utf-8")
    for ad in ("def yakinsama_teshisi", "def sonuc_kapisi",
               "def yuzey_cozunurluk_hukmu"):
        assert ad not in tam, ad


def test_BELIRSIZLIK_uydurulmuyor():
    """Bu yolda mesh-bağımsızlık koşulmuyor; band YOK demek uydurmaktan iyidir."""
    src = inspect.getsource(sr._kalan_kapilar)
    assert "sonuc_kapisi(fizik, conv, None)" in src
    assert "belirsizlik_notu" in src


def test_yakinsama_teshisi_GERIYE_UYUMLU():
    """Kanonik çağıranlar parametresiz çağırmaya devam edebilmeli."""
    from vehicle_pipeline import yakinsama_teshisi
    p = inspect.signature(yakinsama_teshisi).parameters
    assert p["log_adi"].default == "log.foamRun"


def test_extract_results_kapilari_CAGIRIYOR():
    src = inspect.getsource(sr.SimulationRunner._extract_results)
    assert "_kalan_kapilar(" in src and "_kuvvet_tarihcesi(" in src
    assert "force_admissibility" in src               # fizik kapısı korundu
