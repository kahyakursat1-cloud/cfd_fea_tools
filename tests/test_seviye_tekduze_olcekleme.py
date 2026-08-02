"""GCI seviye ailesi TEKDÜZE ölçeklenmeli — ve eşiğin altına düşecek kademe koşulmamalı.

ESKİ KURULUM İKİ ŞEYİ AYNI ANDA YAPIYORDU: arka planı ×1.5 kabalaştırıyor VE
iyileştirme seviyesini 1 düşürüyordu. O zaman yüzey hücresi ×3, arka plan ×1.5
olur — aile TEKDÜZE DEĞİLDİR ve Richardson'ın dayandığı tek h ölçeği tanımsız
kalır.

ÖLÇÜLDÜ (küp çapası, 2026-08-02): yüzey yüzleri 10324 → 1860 → 436 → 176.
Tekdüze ×1.5 olsaydı bölen 2.25 olurdu (→ 4588 / 2039 / 906). Ölçülen bölenler
5.55 / 4.27 / 2.48. İki kaba seviye yüzey kapısının (500) altına düştü, GCI hiç
hesaplanamadı ve saatlerce CFD boşa gitti.
"""
import inspect

import vehicle_pipeline as vp
from analysis.openfoam_runner import YUZEY_YUZ_ESIGI, yuzey_cozunurluk_hukmu

_SRC = inspect.getsource(vp.run_vehicle_analysis)


def test_kademe_iyilestirme_seviyesini_DUSURMUYOR():
    """`dref` kalkmalı: kabalaştırma YALNIZ arka plandan gelir."""
    i = _SRC.index("kademeler = [")
    blok = _SRC[i:i + 1800]
    assert "dref" not in blok, "iyileştirme seviyesi hâlâ kademeye göre düşürülüyor"
    assert "bg_cell_size=bg_ince * oran" in blok
    assert "refinement_max=max(1, rmax + bump)" in blok


def test_TEKDUZE_olcekleme_yuzey_kaybini_dortte_bire_indiriyor():
    """Bölen 9 değil 2.25 olmalı: h oranı 1.5 ise alan oranı 1.5² = 2.25."""
    r = vp.yuzey_yuz_tahmini(1.0, 0.01, 3)
    r15 = vp.yuzey_yuz_tahmini(1.0, 0.015, 3)          # yalnız arka plan ×1.5
    assert abs(r / r15 - 2.25) < 0.05
    r_eski = vp.yuzey_yuz_tahmini(1.0, 0.015, 2)       # arka plan ×1.5 VE ref−1
    assert abs(r / r_eski - 9.0) < 0.2                 # eski kurulumun kaybı


def test_esik_alti_kademe_KOSULMADAN_eleniyor():
    """Reddi koşudan SONRA öğrenmek saatlerce CFD harcamaktır."""
    i = _SRC.index("kademeler = [")
    blok = _SRC[i:i + 1400]
    assert "YUZEY_YUZ_ESIGI" in blok
    assert "KOŞULMADI" in blok
    assert "basarisiz.append" in blok


def test_esik_TEK_kaynak():
    """Kapı ile ön-kapı aynı sayıyı kullanmalı; ayrışırsa ön-kapı ya boşuna eler
    ya da elemesi gerekeni geçirir."""
    assert YUZEY_YUZ_ESIGI == 500
    assert yuzey_cozunurluk_hukmu("", YUZEY_YUZ_ESIGI - 1)["cozuldu"] is False
    assert yuzey_cozunurluk_hukmu("", YUZEY_YUZ_ESIGI)["cozuldu"] is True
    assert "YUZEY_YUZ_ESIGI" in inspect.getsource(yuzey_cozunurluk_hukmu)


def test_OLCULEN_kup_serisi_yeni_kuralda_esigi_geciyor():
    """Küpün ölçülen ince-seviye yüzü 10324; tekdüze ailede üç kaba seviye de
    eşiğin üstünde kalır (4588 / 2039 / 906)."""
    yuz = 10324
    for k in range(1, 4):
        assert yuz / (2.25 ** k) > YUZEY_YUZ_ESIGI, k
