"""TO sonrası bağımsız yeniden-analiz — ölçüm ve onun stres kapısına sonucu.

İki ayrı iddia bağlanır:
  A. Ölçüm doğru kurulmuş mu — ölçek dönüşümü, hacim-koruyan eşik, kayıpsız
     eleman-bölünmesi. (Ucuz, gridler küçük.)
  B. Ölçümün SONUCU var mı — TO'nun kendi gridinde okunan SF, ölçülen ağ
     büyümesiyle şişirilmiş eşiği geçmedikçe "güvenli" denemez.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from topopt_bagimsiz_dogrulama import (  # noqa: E402
    braket,
    buyut,
    esikle,
    olc,
    olcek_dogrulama,
)

# ── A. ölçümün kurulumu ─────────────────────────────────────────────────────

def test_olcek_donusumu_olculur_varsayilmaz():
    """c_fiz=(N/L)·c_birim yanlış olsaydı ölçekli kompliyans N ile ıraksardı."""
    o = olcek_dogrulama()
    assert o["gecti"], o
    assert o["son_iki_sapma_pct"] < o["ilk_son_sapma_pct"] + 1e-9


def test_esik_hacmi_korur():
    rng = np.random.default_rng(0)
    rho = rng.random(600)
    pasif = np.zeros(600, bool)
    pasif[:50] = True
    rho[pasif] = 1e-6
    ikili = esikle(rho, pasif, 1e-6)
    assert abs((ikili > 0.5).sum() - rho[~pasif].sum()) <= 1.0
    assert not (ikili[pasif] > 0.5).any()


def test_buyutme_kayipsiz():
    """Eleman bölünmesi GEOMETRİYİ değiştirmez — hacim fraksiyonu birebir korunur."""
    a = np.array([1.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0])   # nz=2, n=2
    b = buyut(a, 2, 2, 3)
    assert b.size == a.size * 27
    assert b.mean() == pytest.approx(a.mean())
    # ilk elemanin kopyalari BITISIK olmali (yanlis reshape sirasi burada patlar)
    assert b.reshape(6, 6, 6)[0, 0, :3].tolist() == [1.0, 1.0, 1.0]


def test_yuk_tek_dugumde_degil():
    """Nokta yük kendi başına tekillik üretir; ölçülen tekilliğin kaynağı
    ayrışmazdı. Yük şeridi fiziksel olarak sabit kalmalı (grid ile ölçeklenmeli)."""
    t1, _ = braket(16, 2)
    t2, _ = braket(32, 4)
    n1 = int((t1.f != 0).sum())
    n2 = int((t2.f != 0).sum())
    assert n1 > 1 and n2 > n1
    assert t1.f.sum() == pytest.approx(-1.0)
    assert t2.f.sum() == pytest.approx(-1.0)


def test_ayni_tasarim_ince_gridde_farkli_sayi_verir():
    """Ucuz kanıt: yeniden-analiz gerçekten BAŞKA bir ağda çözüyor."""
    t, pasif = braket(8, 2, rmin_el=1.1)
    rho = np.where(pasif, t.emin, 1.0)
    kaba = olc(t, rho, 8)
    tf, _ = braket(16, 4, rmin_el=1.1)
    ince = olc(tf, buyut(rho, 8, 2, 2), 16)
    assert ince["ne"] == kaba["ne"] * 8
    assert ince["hacim_fraksiyonu"] == pytest.approx(kaba["hacim_fraksiyonu"])
    assert ince["c_fiz"] != kaba["c_fiz"]


# ── B. ölçümün sonucu: stres kapısı ─────────────────────────────────────────

def test_kanit_dosyasi_var_ve_tekillik_kayitli():
    d = json.loads((KOK / "topopt_bagimsiz_dogrulama.json").read_text(encoding="utf-8"))
    a = d["2_ayriklastirma"]
    assert a["kompliyans_son_iki_sapma_pct"] < 5.0          # kompliyans yakınsıyor
    assert a["sigma_son_iki_sapma_pct"] > a["kompliyans_son_iki_sapma_pct"]
    assert a["sigma_r1_r3_degisim_pct"] > 10.0              # tepe gerilme yakınsamıyor
    assert d["olcek_dogrulamasi"]["gecti"]


def test_kapi_ham_1_5_esigine_artik_guvenli_demiyor():
    from vehicle_topopt import _ag_buyumesi, _stress_gate
    buyume, _ = _ag_buyumesi()
    assert buyume > 0.1
    sa = {"emniyet_faktoru_temsili": 1.6}
    g = _stress_gate(sa)
    assert g["durum"] == "ag_marjinda"
    assert "yakınsamış" in g["mesaj"]
    assert g["ag_marji"]["esik"] > 1.5


def test_yeterince_buyuk_SF_hala_guvenli():
    from vehicle_topopt import _stress_gate
    g = _stress_gate({"emniyet_faktoru_temsili": 4.0})
    assert g["durum"] == "güvenli"
    assert g["ag_marji"]["buyume_pct"] > 0


def test_akma_asildi_hukmu_degismedi():
    from vehicle_topopt import _stress_gate
    assert _stress_gate({"emniyet_faktoru_temsili": 0.8})["durum"] == "akma_asildi"
    assert _stress_gate({"emniyet_faktoru_temsili": 1.2})["durum"] == "marjinal"
