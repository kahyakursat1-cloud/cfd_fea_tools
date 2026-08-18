"""VLM zarfı: hızlı çözücünün sayısı SINIFIYLA birlikte çıkıyor mu.

Bu testler kapıların DİŞİ olduğunu ölçer. Her biri kaldırıldığında geçen bir
kapı, kapı değildir; testler tek tek o kusuru üretip hükmün değiştiğini görür.

Ölçülmüş girdiler `vlm_panel_yakinsamasi.json` ve `vlm_induklenen_capa.json`
dosyalarından gelir --- uydurulmuş sayı yok.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from validity_envelope import OUT, VALIDATED, classify_vlm, overall_class

KOK = Path(__file__).resolve().parent.parent


def _hukum(v, nicelik):
    return next(x for x in v if x.quantity == nicelik)


def test_toplam_cd_her_kosulda_reddedilir():
    """VLM ne kadar iyi koşarsa koşsun toplam sürükleme üretmez."""
    for a, m, e, band in ((0.0, 0.05, 0.90, 1.0), (4.0, 0.05, 0.95, 2.0),
                          (8.0, 0.2, 0.80, 0.5)):
        v = classify_vlm(a, m, Cl=0.4, CDi=0.01, e_span=e, panel_bandi_pct=band)
        h = _hukum(v, "C_D (toplam sürükleme)")
        assert h.klass == OUT and not h.design_safe
        assert h.kod == "VLM_CD_TOPLAM_YOK"


def test_olculen_span_ihlali_cdi_yi_reddeder():
    """Ölçülen e>1 (gerçek araç, HER panel kademesinde) tasarım kullanımını keser."""
    d = json.loads((KOK / "vlm_panel_yakinsamasi.json").read_text(encoding="utf-8"))
    ihlaller = [k for k in d["kayitlar"] if k["e_4"] > 1.0]
    assert len(ihlaller) == len(d["kayitlar"]), "e>1 tüm kademelerde sürmeliydi"

    en_ince = d["kayitlar"][-1]
    v = classify_vlm(4.0, 0.05, Cl=en_ince["Cl_4"], CDi=en_ince["CDi_4"],
                     e_span=en_ince["e_4"], panel_bandi_pct=1.22)
    h = _hukum(v, "C_Di (indüklenen sürükleme)")
    assert h.klass == OUT and not h.design_safe
    assert h.kod == "VLM_CDI_SPAN_IHLALI"


def test_span_ihlali_bandi_olcumus_olmayi_ezer():
    """Fiziksel imkânsızlık, ölçülmüş bir bandla kurtarılamaz."""
    iyi = classify_vlm(4.0, 0.05, Cl=0.4, CDi=0.01, e_span=0.92, panel_bandi_pct=1.0)
    assert _hukum(iyi, "C_Di (indüklenen sürükleme)").design_safe

    # Gerçek araçta ÖLÇÜLEN değer; toleransın belirgin biçimde ötesinde.
    kotu = classify_vlm(4.0, 0.05, Cl=0.4, CDi=0.01, e_span=1.204, panel_bandi_pct=1.0)
    assert not _hukum(kotu, "C_Di (indüklenen sürükleme)").design_safe


def test_tolerans_sinirinin_iki_yani():
    """Eşik gerçekten ayırıyor mu: toleransın altı geçer, üstü geçmez."""
    from validity_envelope import VLM_SPAN_TOLERANSI
    alt = classify_vlm(4.0, 0.05, Cl=0.4, CDi=0.01,
                       e_span=1.0 + VLM_SPAN_TOLERANSI - 0.01, panel_bandi_pct=1.0)
    ust = classify_vlm(4.0, 0.05, Cl=0.4, CDi=0.01,
                       e_span=1.0 + VLM_SPAN_TOLERANSI + 0.01, panel_bandi_pct=1.0)
    assert _hukum(alt, "C_Di (indüklenen sürükleme)").design_safe
    assert not _hukum(ust, "C_Di (indüklenen sürükleme)").design_safe


def test_beslenmemis_span_kapisi_GEVSEMEZ():
    """Kurulan kapının sessizce devre dışı kalması --- ilk koşuda ölçülen kusur.

    e hesaplanamadığında CDi DOĞRULANMIŞ alıyordu; yani fiziksel kontrol hiç
    çalışmadığı hâlde 'geçmiş' sayılıyordu.
    """
    v = classify_vlm(4.0, 0.05, Cl=0.4, CDi=0.01, e_span=None, panel_bandi_pct=1.2)
    h = _hukum(v, "C_Di (indüklenen sürükleme)")
    assert not h.design_safe and h.kod == "VLM_SPAN_OLCULMEDI"


def test_en_boy_orani_COZUCUDEN_degil_geometriden():
    """AR çözücü sonucunda yok; oradan okumaya çalışmak kapıyı aç bırakıyordu."""
    import hizmet

    class _Kanat:
        span, area = 3.0, 1.5

    class _Ucak:
        wing = _Kanat()

    assert hizmet._en_boy_orani(_Ucak()) == pytest.approx(6.0)
    assert hizmet._en_boy_orani(object()) is None      # kanat yoksa uydurma
    assert hizmet._span_verimi(0.4, 0.01, None) is None


def test_panel_kaniti_yoksa_kapi_gevsemez_sikilasir():
    v = classify_vlm(4.0, 0.05, Cl=0.4, CDi=0.01, e_span=0.92, panel_bandi_pct=None)
    for n in ("C_L (taşıma)", "C_Di (indüklenen sürükleme)"):
        h = _hukum(v, n)
        assert not h.design_safe and h.kod == "VLM_PANEL_KANITI_YOK"


def test_stall_olmadigi_acikca_soylenir():
    """VLM'de stall yok; α zarfı dışında hüküm 'eğilim' değil ZARF-DIŞI."""
    v = classify_vlm(14.0, 0.05, Cl=1.2, CDi=0.05, e_span=0.9, panel_bandi_pct=1.0)
    h = _hukum(v, "C_L (taşıma)")
    assert h.klass == OUT and h.kod == "VLM_ALPHA_STALL_YOK"


def test_temiz_kosuda_tasima_ve_cdi_kullanilabilir():
    """Kapılar her şeyi reddetmiyor: koşullar sağlanınca sayı kullanılabilir."""
    v = classify_vlm(4.0, 0.05, Cl=0.40, CDi=0.010, e_span=0.93, panel_bandi_pct=1.5)
    assert _hukum(v, "C_L (taşıma)").klass == VALIDATED
    assert _hukum(v, "C_Di (indüklenen sürükleme)").klass == VALIDATED
    # Ama genel sınıf yine de toplam-Cd reddi yüzünden düşer.
    assert overall_class(v) != VALIDATED


def test_capadaki_temiz_kanat_span_sinirini_asmaz():
    """vlm_capa: temiz dikdörtgen kanatta e≤1 --- kapı orada YANLIŞ ALARM vermez."""
    p = KOK / "vlm_capa.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    for kayit in d["kayitlar"]:
        ar = kayit["AR"]
        for n in kayit["noktalar"]:
            cl, cdi = n["Cl"], n["Cd_i"]
            if not cl or not cdi or cdi <= 0:
                continue
            e = (cl * cl) / (3.141592653589793 * ar * cdi)
            v = classify_vlm(n["alpha"], 0.05, Cl=cl, CDi=cdi, e_span=e,
                             panel_bandi_pct=1.22)
            h = _hukum(v, "C_Di (indüklenen sürükleme)")
            assert h.kod != "VLM_CDI_SPAN_IHLALI", (
                f"temiz kanatta AR={ar} α={n['alpha']} e={e:.3f} ihlal işaretlendi")


@pytest.mark.parametrize("dil", ["tr", "en"])
def test_hukum_kodlari_iki_dilde_de_metne_cevriliyor(dil):
    from mesajlar import gerekce_metni
    v = classify_vlm(4.0, 0.05, Cl=0.4, CDi=0.01, e_span=1.21, panel_bandi_pct=None)
    for h in v:
        assert h.kod, f"{h.quantity} kodsuz çıktı"
        m = gerekce_metni(h.kod, dil, **(h.parametreler or {}))
        assert m != h.kod, f"{h.kod} {dil} dilinde çevrilmemiş"
        assert "parametresi eksik" not in m, f"{h.kod} {dil}: {m}"
