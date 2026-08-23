"""EĞİLME mi BURULMA mı — sehim/açıklık oranının göremediği ayrım.

Tahrik bandı (sehim/açıklık %1--3) arandı ve bulundu (fsi_tahrikH: %2,47), ağ
gerçekten hareket etti, ilmek yakınsadı --- ama CFD yüzeyindeki aerodinamik
yük yalnız %0,2 değişti. Sehim yeterliydi, kuplaj yine sürülmedi.

ÖLÇÜLDÜ (2026-08-22, fsi_tahrikH t=294): eğilme 6,51 mm, burulma −0,041°.
Düz konsol levha SAF EĞİLME yapıyor: kesit yukarı çıkıyor ama yerel hücum
açısı değişmiyor, dolayısıyla basınç dağılımı da değişmiyor.

Bu, sehim/açıklık ölçütünün GEREK ama YETER olmadığını gösterir. Aracın eski
öğüdü ("daha esnek yapı ya da daha yüksek dinamik basınç gerekir") bu
konfigürasyonda YANLIŞTIR --- daha çok eğilme yine burulma üretmez.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from fsi_burulma import BURULMA_ESIGI_DEG, ayristir  # noqa: E402


def _uc_kesit(n=20, veter=0.04, sehim=0.0074, burulma_deg=0.0, x0=0.0):
    x = np.linspace(x0, x0 + veter, n)
    p = np.c_[x, np.full(n, 0.30), np.zeros(n)]
    w = sehim + np.tan(np.radians(burulma_deg)) * (x - x.mean())
    return p, np.c_[np.zeros(n), np.zeros(n), w]


def test_AYNI_SEHIM_zit_hukum():
    """Ayırımın bütün değeri burada: sehim aynı, hüküm zıt.

    Sehim/açıklık oranına bakan bir ölçüt ikisini AYIRT EDEMEZ ve büyük bir
    sehimi "kuplaj sürülüyor" diye okur.
    """
    duz = ayristir(*_uc_kesit(burulma_deg=0.0))
    burulmali = ayristir(*_uc_kesit(burulma_deg=-0.94))

    assert duz["egilme_mm"] == pytest.approx(burulmali["egilme_mm"], abs=1e-6)
    assert duz["burulma_baskin_mi"] is False
    assert burulmali["burulma_baskin_mi"] is True
    assert burulmali["burulma_deg"] == pytest.approx(-0.94, abs=0.01)


def test_OK_ACISI_burulma_sanilmiyor():
    """Ok açılı gövdede veter açıklıkla KAYAR; ham x kullanmak ok açısını
    burulma sanmaya yol açardı."""
    p, d = _uc_kesit(burulma_deg=0.0, x0=0.1732)      # 30 derece okta uc kesit
    r = ayristir(p, d)
    assert r["burulma_deg"] == pytest.approx(0.0, abs=1e-6)
    assert r["burulma_baskin_mi"] is False


def test_esik_ALTINDAKI_burulma_yeter_sayilmiyor():
    r = ayristir(*_uc_kesit(burulma_deg=0.5 * BURULMA_ESIGI_DEG))
    assert r["burulma_baskin_mi"] is False
    assert "SAF EĞİLME" in r["hukum"]


def test_VETER_boyunca_yayilim_yoksa_hukum_YOK():
    """Tek noktadan burulma ölçülemez; sıfır dönmek onu 'yok' göstermek olurdu."""
    p = np.c_[np.zeros(5), np.full(5, 0.30), np.zeros(5)]
    r = ayristir(p, np.c_[np.zeros(5), np.zeros(5), np.full(5, 0.007)])
    assert r["durum"] != "ok"
    assert "burulma_deg" not in r


def test_GERCEK_kosuda_duz_levha_SAF_EGILME():
    """Ölçüm koşudan okunuyor; hipotez değil."""
    case = KOK / "vehicle_runs" / "fsi_tahrikH" / "fsi_tahrikH"
    if not case.exists():
        pytest.skip("fsi_tahrikH koşusu diskte yok")
    from fsi_burulma import vakadan
    r = vakadan(case, "fsi_tahrikH_prep")
    if r.get("durum") != "ok":
        pytest.skip(f"okunamadı: {r.get('durum')}")
    assert abs(r["burulma_deg"]) < BURULMA_ESIGI_DEG, (
        f"düz levhada burulma {r['burulma_deg']}° — beklenen ~0; geometri "
        f"değiştiyse bu testin dayanağı da değişmiştir")
    assert r["egilme_mm"] > 5.0, "eğilme var ama burulma yok — asıl bulgu bu"


def test_LISTE_SONU_dogru_araniyor():
    """`)` ilk vektörün kapanışıdır; `);` listenin sonudur.

    Ölçüldü: ilk sürüm 122 vektörlük yamayı "alan 0" diye okudu. Aynı tuzak
    `write_point_displacement`'ta yazarken de yaşanmıştı.
    """
    src = (KOK / "fsi_burulma.py").read_text(encoding="utf-8")
    i = src.index("def vakadan(")
    govde = src[i:i + 3000]
    assert 'blok.find(");"' in govde, "liste sonu `);` ile aranmıyor"
    assert "beklenen" in govde, "bildirilen vektör sayısı doğrulanmıyor"
