"""MMA kararı ikinci problem ailesinde — L-braket'e özgü müydü?

DIŞ HAKEM P2 (2026-08-26): "MMA'yı başka geometri/problem ailesinde sınama
--- L-bracket ile sınırlı." Kısıt zaten `mma_bolum10.json`da yazılıydı.

BULGU BEKLENENDEN KESKİN ÇIKTI. Soru "MMA yine önde mi" idi; cevap bir
derece farkı değil: MBB kirişinde OC gerilme-min'i koştuğunda tepe gerilme
DÜŞMÜYOR, ARTIYOR (1,80 → 2,65). Yani benchmark'ın kendi ölçütünü ---
peak(stress) < peak(compliance) --- geçemiyor. MMA aynı problemde 1,73 →
1,35.

Bu testler o bulguyu ve onun DAYANAKLARINI bağlar: iki tasarım da hacim
kısıtını sağlamalı (yoksa düşük gerilme bedava gelir), kıyas eşit hesap
maliyetinde olmalı, ve iddia raporda kanıtla aynı yazılmalı.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "mma_ikinci_aile.json"


@pytest.fixture(scope="module")
def d():
    if not KANIT.exists():
        pytest.skip("mma_ikinci_aile.json yok (python experiments/mma_ikinci_aile.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_AILE_L_BRAKETTEN_gercekten_FARKLI(d):
    """İkinci aile ilkinin kopyası olmamalı; yoksa 'ikinci aile' demek
    ölçüm değil süslemedir."""
    p = d["problem"]
    assert p["girintili_kose"] is False and p["pasif_bolge"] is False
    assert "MBB" in p["ad"]


def test_IKI_TASARIM_da_HACIM_KISITINI_sagliyor():
    """Düşük tepe gerilme, hacim kısıtı ihlaliyle BEDAVA elde edilebilir.

    Kiyas gecerli olsun diye iki tasarimin da hacmi hedefte olmali; bu
    denetim %47'lik farka inanmadan ONCE kosuldu.
    """
    from mma_ikinci_aile import GERILME_ITER, KOMP_ITER, VF, build_mbb
    for g in ("oc", "mma"):
        t = build_mbb()
        t.optimize(VF, "compliance", max_iter=KOMP_ITER, guncelleyici=g)
        rho, _ = t.optimize(VF, "stress", max_iter=GERILME_ITER, tol=0.01,
                            guncelleyici=g)
        assert abs(float(rho.mean()) - VF) < 0.01, \
            f"{g}: hacim kısıtı sağlanmıyor ({rho.mean():.4f} vs {VF})"


def test_OC_BU_AILEDE_amaci_TERSINE_ceviriyor(d):
    """Bulgu bir derece farkı değil: bir güncelleyici hedefi kötüleştiriyor."""
    assert d["amaci_GERCEKTEN_dusurdu_mu"]["OC"] is False
    assert d["amaci_GERCEKTEN_dusurdu_mu"]["MMA"] is True
    assert d["kosular"]["OC"]["azalma_pct"] < 0
    assert "BAŞARISIZ" in d["verdikt"]


def test_KIYAS_ESIT_HESAP_MALIYETINDE(d):
    """Bölüm 10'da sabit-iterasyon kıyası MMA lehine yanlıydı; aynı hata
    burada tekrarlanmamalı."""
    assert "OC_esit_maliyet" in d["kosular"]
    beklenen = int(round(80 * d["maliyet_orani_MMA_bolu_OC"]))
    assert d["esit_maliyet_iterasyonu"] == beklenen
    # ESIT MALIYETTE DE ayni hukum
    assert d["amaci_GERCEKTEN_dusurdu_mu"]["OC_esit_maliyet"] is False


def test_DURMA_OLCUTU_iki_ailede_de_AYNI_yone_bakiyor(d):
    """L-brakette MMA kendi toleransıyla duruyor, OC limit çevriminde
    kalıyordu. Aynı davranış burada da görülmeli; görülmezse bulgu
    problem-özgüdür."""
    if d["MMA_kendi_olcutuyle_durdu"] is None:
        pytest.skip("--hizli koşusu; durma ölçütü sınavı yapılmadı")
    assert d["MMA_kendi_olcutuyle_durdu"] is True
    assert d["OC_kendi_olcutuyle_durdu"] is False


def test_KISIT_ucuncu_ailenin_SINANMADIGINI_soyluyor(d):
    """İki aile 'genel' demek değildir ve kayıt bunu yazmalı."""
    assert "SINANMADI" in d["_kisit"]
    assert "ayarlanmadi" in d["_kisit"] or "ayarlanmadı" in d["_kisit"]


def test_RAPOR_kanittan_sapmiyor(d):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "MBB" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    for k in (d["kosular"]["OC"]["peak_gerilme"],
              d["kosular"]["MMA"]["peak_gerilme"],
              d["kosular"]["OC"]["peak_komp"]):
        s = f"{k}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"
    assert "ARTIRDI" in t or "artırdı" in t, \
        "raporda OC'nin amacı tersine çevirdiği yazmıyor"
