"""VLM çapası — VSPAERO'nun taşımasına ÖLÇÜLMÜŞ band verir.

VLM bu depoda hiçbir referansa karşı doğrulanmamıştı; `polar_birlestirme` Cl'i
"literatür-öncül" etiketiyle yayınlıyordu. Çapa o etiketi ölçüme çevirir.

ÖLÇÜT KAPALI-FORM (grafik/tablo değeri KULLANILMAZ):
    1/a_3B = 1/a_2B + (1+τ)/(π·AR)
1/AR'ye karşı doğru olmalı ve KESİŞİMİ 1/a_2B = 1/(2π) vermeli.

ÖLÇÜLEN (dikdörtgen kanat, AR=4/6/8/12, yakınsamış panel):
    R² = 0.99983,  kesişimden a_2B = 6.3601/rad,  2π = 6.2832  → sapma %1.22

VE BİR KUSUR BULDU: varsayılan panelde span verimi e = 1.0788 çıkıyordu —
eliptik yükleme MATEMATİKSEL ÜST SINIRDIR (e=1), yani fiziksel olarak imkânsız.
Panel taraması ayrımı yaptı: 12→1.0280, 24→1.0045, 40→0.9954. Artefakt
ayrıklaştırmadanmış. Taşıma eğimi de %6.6 kayıyordu (4.4523 → 4.1750).
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KANIT = ROOT / "vlm_capa.json"


def _d():
    return json.loads(KANIT.read_text(encoding="utf-8")) if KANIT.exists() else None


def test_olcut_KAPALI_FORM_kalsin():
    """τ/δ grafik değerleri ezberden alıntılanırsa kanıt olmaz."""
    src = (ROOT / "experiments" / "vlm_capa.py").read_text(encoding="utf-8")
    assert "1/a_2B" in src or "1/a_3B" in src
    assert "A_2B_TEORI = 2.0 * math.pi" in src


def test_kesisim_2pi_yi_geri_veriyor():
    d = _d()
    if not d:
        return
    u = d["uyum"]
    assert u["dogrusal_R2"] > 0.99, u
    assert abs(u["a_2B_olculen_per_rad"] - 2 * math.pi) / (2 * math.pi) * 100 < 5.0
    assert u["hata_pct"] < 5.0


def test_PANEL_yakinsamasi_olculmus():
    """e>1 iki farklı şey olabilir; ayrımı ölçüm yapar."""
    d = _d()
    if not d:
        return
    pk = d["panel_yakinsamasi"]
    e = [k["e_max"] for k in pk["kosular"] if k["e_max"]]
    assert len(e) >= 3
    assert e[0] > e[-1], "panel arttıkça e DÜŞMELİ"
    assert e[-1] <= 1.0, "yakınsamış panelde e eliptik sınırın içine girmeli"


def test_e_asimi_SINIFLANDIRILIYOR():
    """Ne göz ardı ediliyor ne de körü körüne reddediliyor."""
    d = _d()
    if not d:
        return
    a = d["span_verimi_asimi"]
    assert a["sinif"] in ("sinir icinde", "artik ayriklastirma")
    if a["asim"] and a["asim"] > 0:
        assert a["asim"] < a["panel_kaymasi"], a


def test_URETIM_yolu_yakinsamis_paneli_kullaniyor():
    """Çapa bir kusur buldu; üretim yolu düzelmezse ölçüm boşa gider."""
    src = (ROOT / "openvsp_bridge.py").read_text(encoding="utf-8")
    assert "VLM_SPAN_PANEL = 40" in src
    assert "SectTess_U" in src
    i = src.index("VLM_SPAN_PANEL = 40")
    assert "e=1.0788" in src[max(0, i - 400):i], "gerekçe sayısıyla yazılmalı"


def test_DOGRULAMA_ile_GECERLEME_karistirilmiyor():
    """VLM'i potansiyel-akış teorisiyle karşılaştırmak verification'dır;
    viskoz gerçekle farkı AYRI bir sorudur ve bu çapa onu ölçmez."""
    d = _d()
    if not d:
        return
    assert "verification" in d["_kisit"]
    assert "OLCMEZ" in d["_kisit"] or "ÖLÇMEZ" in d["_kisit"]
