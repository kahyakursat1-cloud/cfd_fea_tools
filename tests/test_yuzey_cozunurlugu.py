"""Yüzey çözünürlüğü: NİYET değil SONUÇ ölçülür.

MiniHawk'ta ölçülen kök sebep: `bg_cell_size` geometriden (lmax/bg_div) hesaplanıyordu
ama hücre SAYISINI domain belirler. Gövde 0.7×1.5×0.08 m, domain 38×22.5×21 m,
istenen hücre 0.167 m → arka plan TEK BAŞINA 3.94M hücre, `hassas` tavanı 2.5M.
snappyHexMesh daha ilk adımda bütçeyi tüketip kendi logunda yazdı:
    "No cells marked for refinement since reached limit 2500000."
Sonuç: hiçbir yüzey iyileştirmesi yapılmadı, uçağın tamamı 74 YÜZLE temsil edildi
(uzak-alan yamaları 17-31 bin yüz). Bu TEK kusur şunları birlikte açıklar:
y⁺≈5000, 12 katmanın 0 örülmesi, Cl'in beklenenin 1/16'sı çıkması, GCI %379.

Eski `resolution_warning` bunu göremiyordu çünkü yüzey hücresini niyetten
hesaplıyordu: 0.010 m rapor edip "sorun yok" derken snappy 0.167 m teslim etti.
"""
import numpy as np
import pytest

from analysis.openfoam_runner import (
    arka_plan_hucre_boyu,
    parse_iyilestirme_acligi,
    yuzey_cozunurluk_hukmu,
)

# MiniHawk'in GERCEK domain'i (log.blockMeshDict'ten)
DMIN = np.array([-10.38, -11.25, -10.54])
DMAX = np.array([27.824, 11.25, 10.54])
ACLIK = "No cells marked for refinement since reached limit 2500000.\n"


def test_MINIHAWK_VAKASI_arka_plan_kabalastiriliyor():
    _, i = arka_plan_hucre_boyu(DMIN, DMAX, 0.1667, 2_500_000)
    assert i["kabalastirildi"] is True
    assert i["arka_plan_hucre"] <= 2_500_000 * 0.25 * 1.05
    assert i["secilen_m"] > 0.1667


def test_arka_plan_asla_INCELTILMEZ():
    """Bütçe bolsa istenen boy korunur — kapı yalnız kabalaştırır."""
    b, i = arka_plan_hucre_boyu(DMIN, DMAX, 5.0, 50_000_000)
    assert b == pytest.approx(5.0)
    assert i["kabalastirildi"] is False


def test_aclik_LOGDAN_olculuyor():
    a = parse_iyilestirme_acligi(ACLIK * 3)
    assert a["aclik"] is True and a["kez"] == 3 and a["limit"] == 2_500_000
    assert parse_iyilestirme_acligi("her sey yolunda")["aclik"] is False


def test_74_YUZ_reddedilir():
    h = yuzey_cozunurluk_hukmu(ACLIK, 74)
    assert h["cozuldu"] is False
    assert any("74 yuz" in g for g in h["gerekce"])
    assert any("TUKETTI" in g for g in h["gerekce"])


def test_saglikli_mesh_gecer():
    h = yuzey_cozunurluk_hukmu("Finished meshing without any errors", 25000)
    assert h["cozuldu"] is True and h["gerekce"] == []


def test_aclik_TEK_BASINA_reddeder():
    """Yüz sayısı iyi görünse bile bütçe tükenmişse iyileştirme yapılmamıştır."""
    h = yuzey_cozunurluk_hukmu(ACLIK, 25000)
    assert h["cozuldu"] is False


def test_yuz_sayisi_OLCULEMEZSE_iyi_SAYILMAZ_degil_ama_aclik_bakilir():
    h = yuzey_cozunurluk_hukmu("temiz log", None)
    assert h["cozuldu"] is True          # kanit yok, aclik da yok
    assert h["yuzey_yuz"] is None


def test_hukum_SONUCA_baglaniyor():
    """Ölçüm tüketilmezse yine sessiz kalır — bu oturumun tekrarlayan deseni."""
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    assert "yuzey_cozunurluk_hukmu" in src
    assert "yuzey_cozunurlugu" in src
    assert "GÖVDE YÜZEYİ ÇÖZÜLMEDİ" in src


def test_uyari_EN_BASA_ekleniyor():
    """Bu kusur diğer tüm uyarıları geçersizler; listenin başında olmalı."""
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    i = src.index("GÖVDE YÜZEYİ ÇÖZÜLMEDİ")
    assert "uyarilar.insert(0," in src[max(0, i - 200):i]


def test_resolution_warning_GERCEK_arka_plani_kullanir():
    """Niyetle hesaplamak çözünürlüğü OLDUĞUNDAN İYİ gösterir.

    MiniHawk: niyet 0.1667 m, snappy'nin teslim ettiği 0.3072 m. Aynı geometri
    için bekçi niyetle "yeterli" derken gerçekle "yetersiz" demeli."""
    from vehicle_pipeline import resolution_warning
    # ince ozellik 0.021 m, ref_max=3 -> niyet hucresi 0.1667/8=0.0208 -> ~1 hucre
    niyet = resolution_warning(1.5, 9, 3, 0.021)
    gercek = resolution_warning(1.5, 9, 3, 0.021, bg_cell_m=0.3072)
    assert niyet is not None and gercek is not None
    # gercek arka plan KABA oldugu icin oran daha kotu cikmali
    import re
    o_n = float(re.search(r"~([\d.]+) kat", niyet).group(1))
    o_g = float(re.search(r"~([\d.]+) kat", gercek).group(1))
    assert o_g < o_n, f"gercek({o_g}) niyetten({o_n}) daha iyi gorunuyor"


def test_bekci_bol_butcede_susuyor():
    from vehicle_pipeline import resolution_warning
    assert resolution_warning(1.5, 9, 4, 0.5, bg_cell_m=0.1667) is None


def test_pipeline_bekciye_GERCEK_boyu_geciriyor():
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    i = src.index("resolution_warning(")
    assert "bg_cell_m=" in src[i:i + 400], "gercek arka plan boyu gecirilmiyor"
