"""DES bütçesi: kestirimin girdileri ÖLÇÜM mü KURAL mı, ayrı durmalı.

Yol haritası "kalan iş: DES/LES çapası" diyordu ve bu bir temenniydi. Bütçe
ölçülünce cevap netleşti: bu çapa Ahmed duvar-çözünür hücresinin AKSİNE bu
donanımda koşulabilir --- engel bellek değil süre.

Bir bütçe kestirimi, girdileri izlenebilir olmadıkça kanıt değildir. Bu
testler kestirimin sabitlerini ölçüme bağlar ve iki yönlü tutarlılığını
sınar (y⁺ tanımı, CFL, ölçeklenme yönü).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from des_fizibilite import KB_HUCRE, NU, butce, u_tau  # noqa: E402


def test_u_tau_olculen_yplus_ile_TUTARLI():
    """Geri çözülen u_τ, ölçülen y⁺'ı yeniden vermeli (hücre MERKEZİNDE)."""
    import des_fizibilite as m
    y_merkez = m.ILK_HUCRE_M / 2.0
    assert abs(y_merkez * u_tau() / NU - m.YPLUS_OLCULEN) < 1e-6


def test_yplus_bir_ilk_hucre_TERSTEN_dogrulaniyor():
    """y⁺=1 için verilen ilk hücrenin merkezi gerçekten y⁺=1 vermeli."""
    b = butce(0.05, bos_gb=100.0)
    y_merkez = b["ilk_hucre_m"] / 2.0
    # Tolerans yayimlanan degerin YUVARLAMASINDAN gelir (8 ondalik), fizikten
    # degil: 1e-4 bandi hala y+=1 ile y+=1,0001'i ayirir.
    assert abs(y_merkez * u_tau() / NU - 1.0) < 1e-4, b["ilk_hucre_m"]


def test_bellek_katsayisi_OLCULEN_dosyayla_ayni():
    """Kestirim kendi katsayısını taşımamalı; ölçülen kanıtla aynı olmalı."""
    p = KOK / "bellek_katsayisi.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    olculen = d.get("kb_hucre") or (d.get("dogrusal") or {}).get("b_kb_hucre")
    if olculen is None:
        pytest.skip('kanıt/girdi yok: olculen is None')
    assert abs(olculen - KB_HUCRE) < 0.01, f"kanıt {olculen} ≠ betik {KB_HUCRE}"


def test_ince_cozunurluk_DAHA_PAHALI():
    """Ölçeklenme yönü: Δz küçüldükçe hücre, bellek ve süre ARTMALI."""
    kaba, ince = butce(0.10, 100.0), butce(0.05, 100.0)
    assert ince["hucre"] > kaba["hucre"]
    assert ince["bellek_gb"] > kaba["bellek_gb"]
    assert ince["sure_saat"] > kaba["sure_saat"]


def test_zaman_adimi_CFL_ve_periyot_kisitinin_KUCUGU():
    """Δt iki kısıttan hangisi bağlıyorsa ondan gelmeli."""
    import des_fizibilite as m
    periyot_s = m.D / (m.ST * m.U)
    for dz_D in (0.10, 0.05, 0.025):
        b = butce(dz_D, 100.0)
        assert abs(b["dt_s"] - min(dz_D * m.D / m.U,
                                   periyot_s / m.PERIYOT_ADIM)) < 1e-9


def test_bellek_kapisi_BOS_bellekle_karsilastiriyor():
    """Sığma hükmü gerçek boş bellekle kıyaslanmalı, sabitle değil."""
    dar = butce(0.05, bos_gb=0.5)
    genis = butce(0.05, bos_gb=100.0)
    assert dar["bellege_sigar_mi"] is False
    assert genis["bellege_sigar_mi"] is True


def test_azimut_MEVCUT_agdan_kabalastirilmiyor():
    """İzotropi kuralı ağı kabalaştırmak için kullanılamaz.

    Δz/D=0,1'de izotropi π/0,1 ≈ 32 azimut hücresi ister; mevcut ağda 240 var.
    Kuralı düz uygulamak ağı 7 kat KABALAŞTIRIRDI.
    """
    import des_fizibilite as m
    b = butce(0.10, 100.0)
    assert b["n_cevre"] >= m.N_CEVRE_MEVCUT
    assert math.ceil(math.pi * m.D / 0.10) < m.N_CEVRE_MEVCUT


def test_kanit_OLCUM_ile_KURALI_ayri_tutuyor():
    """Hangi sayı ölçüm, hangisi seçim — okuyucu ayırt edebilmeli."""
    p = KOK / "des_fizibilite.json"
    if not p.exists():
        pytest.skip('kanıt/girdi yok: not p.exists()')
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "olculen_girdiler" in d and "kurallar" in d
    for alan in ("u_tau_kaynagi", "kb_hucre_kaynagi", "hiz_kaynagi"):
        assert d["olculen_girdiler"][alan], alan
    assert "SOYLEMEZ" in d["_ne_soylemez"]
