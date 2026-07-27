"""Süpersonik rapor, fizik kapısı hükmünü GÖSTERMELİ.

`supersonic_cfd` hükmü `fizik` / `uyari_fizik` alanlarına yazıyordu ama rapor onları
HİÇ okumuyordu: Cd, hükmü olmadan sunuluyordu. `vehicle_report`'ta kapatılan boşluğun
aynısı — kapı kurmak yetmiyor, mühendisin baktığı yere ulaşması gerekiyor.
"""
import inspect

import supersonic_cfd
import supersonic_report

SRC = inspect.getsource(supersonic_report.build_supersonic_report)


def test_rapor_fizik_hukmunu_okuyor():
    assert 'result.get("fizik")' in SRC, "rapor kapı hükmünü hiç okumuyor"


def test_hukum_baslikta_ozetten_ONCE():
    """Okuyucu Cd'yi görmeden önce hükmü görmeli."""
    i_kapi = SRC.index('result.get("fizik")')
    i_ozet = SRC.index('"## Özet"')
    assert i_kapi < i_ozet


def test_iki_seviye_de_gosteriliyor():
    assert "inadmissible" in SRC and "suspect" in SRC
    i = SRC.index("inadmissible")
    assert "KULLANILMAZ" in SRC[i - 400:i + 400], "fizik-dışı koşuda net dil gerekli"


def test_saglikli_kosuda_banner_cikmaz():
    """Kapı 'ok' ise rapor gereksiz uyarıyla kirlenmemeli."""
    assert "else []" in SRC, "koşulsuz banner eklenmiş olabilir"


def test_supersonic_cfd_hukmu_yaziyor():
    """Zincirin diğer ucu: üretici alanları gerçekten dolduruyor mu."""
    src = inspect.getsource(supersonic_cfd)
    assert 'out["fizik"] = fz' in src
    assert 'out["uyari_fizik"]' in src
    # süpersonikte künt burun dalga sürüklemesi yüksektir; dar eşik yanlış alarm verir
    i = src.index('out["fizik"] = fz')
    assert "CD_MAX_STREAMLINED" not in src[i - 500:i], "süpersonikte dar eşik kullanılmamalı"
