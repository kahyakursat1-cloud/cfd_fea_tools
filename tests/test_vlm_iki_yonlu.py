"""İki yönlü panel ailesi — tek yönde inceltmek yakınsama gösteremiyordu.

ÖLÇÜLDÜ: gövde çapı düzeltildikten sonra açıklık serisi monotonlaştı
(0.79144→0.72394) ama p<0.5 ve band %28.32'de kaldı. Kiriş yönü tek başına
Cl(8)'i %1.9 oynatıyor (Tess_W 17/25/33/49 → 0.72920/0.72256/0.73630/0.73711)
ve açıklık serisinin ince adımları (%0.5–1.2) o gürültünün ALTINDA. Sabit
tutulan yön bandın tabanını belirliyor.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAYNAK = ROOT / "experiments" / "vlm_iki_yonlu_yakinsama.py"
KANIT = ROOT / "vlm_iki_yonlu_yakinsama.json"


def _d():
    return json.loads(KANIT.read_text(encoding="utf-8")) if KANIT.exists() else None


def test_HER_IKI_yon_de_inceltiliyor():
    """Aile tek yönlü olsaydı bu deney mevcut ölçümün kopyası olurdu."""
    d = _d()
    if not d:
        return
    sp = [k["span"] for k in d["kademeler"]]
    kr = [k["kiris"] for k in d["kademeler"]]
    assert all(a < b for a, b in zip(sp, sp[1:])), "açıklık artmıyor"
    assert all(a < b for a, b in zip(kr, kr[1:])), "kiriş artmıyor"


def test_h_orani_Celik_sartini_SAGLIYOR():
    """r ≥ 1.3 h ORANINDA sağlanmalı; panel sayısında değil."""
    d = _d()
    if not d:
        return
    assert min(d["h_oranlari"]) >= 1.3, d["h_oranlari"]


def test_band_2B_kuraldan():
    """Panel 2B bir yüzeyi döşer: h ~ N^(-1/2). boyut=3 bandı şişirir."""
    src = KAYNAK.read_text(encoding="utf-8")
    assert "boyut=2" in src, "band 3B formülüyle hesaplanıyor"
    d = _d()
    if not d:
        return
    assert d["vlm_band_pct"] == d["kanonik_band"]["u_pct"]


def test_PANEL_ayari_gercekten_UYGULANDI():
    """Bu depoda panel ayarı bir kez YANLIŞ YERE konmuş ve sonuç birebir aynı
    çıkmıştı; hangi geometriye uygulandığı kayda geçmeli."""
    d = _d()
    if not d:
        return
    for k in d["kayitlar"]:
        assert k["span_uygulanan"], "açıklık paneli hiçbir kanada uygulanmamış"
        assert k["kiris_uygulanan"], "kiriş paneli hiçbir kanada uygulanmamış"


def test_VERDIKT_kendi_verisiyle_TUTARLI():
    """Rapor metni ölçtüğü seriyle çelişmemeli — bu depoda bir kez çelişti."""
    d = _d()
    if not d:
        return
    seri = d["seri"]
    gercek = (all(a <= b for a, b in zip(seri, seri[1:]))
              or all(a >= b for a, b in zip(seri, seri[1:])))
    assert d["monoton"] == gercek
    assert ("monoton" in d["verdikt"] if gercek
            else "MONOTON DEGIL" in d["verdikt"])
    # Daralma iddiasi SAYIYLA tutarli olmali; ters yonde iddia edilemez.
    if d["vlm_band_pct"] < d["tek_yonlu_band_pct"]:
        assert "KAT daraldi" in d["verdikt"]
    else:
        assert "daralma YOK" in d["verdikt"]


def test_KISIT_dogrulama_ile_karistirmiyor():
    d = _d()
    if not d:
        return
    assert "DOGRULAMA bandi DEGIL" in d["_kisit"] or "DOĞRULAMA" in d["_kisit"]
