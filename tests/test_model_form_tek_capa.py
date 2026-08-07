"""Model-form bandı: tek çapayla band DARALTILMAZ.

n=1 bir dağılım değil, tek örnektir. Ölçülen değer öncülden küçükse bu "model
daha iyi" demek değil, "bu tek vakada daha iyi çıktı" demektir; model-form
hatası rejim içinde geometriye göre güçlü değişir. Bandı tek ölçümle daraltmak,
bu deponun tam da savaştığı sahte-kesinliktir.

Kural asimetriktir ve bilerek öyledir: ölçüm öncülü AŞARSA her durumda ölçüm
kazanır — o zaman öncül kanıtla yanlışlanmış demektir (yukarı düzeltme hep
kabul, aşağı düzeltme n=1'de değil).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from model_form_bandi import _duvar_islemi, _kosudan_yplus, calistir  # noqa: E402

from validation_anchors import _MODEL_U_PCT  # noqa: E402


def test_tek_capa_bandi_DARALTMAZ():
    rec = calistir()
    for rejim, h in rec["olculen_hucreler"].items():
        for islem, v in h.items():
            oncul = _MODEL_U_PCT.get(rejim, {}).get(islem)
            if v["n_capa"] == 1 and oncul is not None:
                assert v["u_pct"] >= oncul, (
                    f"{rejim}.{islem}: tek çapayla band daraltıldı "
                    f"({v['olculen_pct']} < {oncul})")


def test_olcum_onculu_asarsa_OLCUM_kazanir():
    """Yukarı düzeltme her durumda kabul: öncül kanıtla yanlışlanmıştır."""
    rec = calistir()
    for h in rec["olculen_hucreler"].values():
        for v in h.values():
            if v["oncul_pct"] is not None and v["olculen_pct"] > v["oncul_pct"]:
                assert v["u_pct"] == v["olculen_pct"]
                assert v["oncul_korundu"] is False


def test_korunan_oncul_OLCUMU_de_kaydediyor():
    """Öncül korunsa bile ölçüm kaybolmamalı — sonraki çapa geldiğinde gerekir."""
    rec = calistir()
    korunan = [v for h in rec["olculen_hucreler"].values() for v in h.values()
               if v["oncul_korundu"]]
    assert korunan, "bu depoda en az bir korunan öncül hücresi var"
    for v in korunan:
        assert v["olculen_pct"] > 0
        assert "DARALTILMADI" in v["_anlam"]


# ── y⁺ bağı: ölçüm tüketicisine ULAŞIYOR mu ───────────────────────────────

def test_kup_capasinin_yplusu_artik_kosudan_geliyor():
    """Küp çapasının y⁺'ı ölçülmüştü ama çapa dosyasına yazılmamıştı; bu yüzden
    `bluff.wall_function` hiçbir zaman ölçülemiyordu."""
    rec = calistir()
    kup = next(x for x in rec["capalar"] if x["capa"] == "küp")
    assert kup["yplus_ort"] is not None
    assert kup["yplus_kosu"], "y⁺'ın hangi koşudan geldiği yazılmalı"
    assert "birebir" in kup["yplus_kaynak"]


def test_yplus_bagi_TAHMINLE_kurulmaz():
    """Hücre sayısı eşleşmeyen koşunun y⁺'ı çapaya iliştirilemez — y⁺ kademeye
    göre değişir, yanlış kademeninki ölçümü uydurmak olurdu."""
    assert _kosudan_yplus(None) is None
    assert _kosudan_yplus(123_456_789) is None


def test_bant_disi_yplus_hucreye_atanmaz():
    from validity_envelope import YPLUS_BANDI
    assert _duvar_islemi(YPLUS_BANDI[1] + 500) is None
    assert _duvar_islemi(None) is None
    assert _duvar_islemi(1.0) == "wall_resolved"
    assert _duvar_islemi(100.0) == "wall_function"


# ── dış kaynaklı hücreler ──────────────────────────────────────────────────

def test_bu_betigin_uretmedigi_hucreler_ISARETLENIR():
    """Band dosyasında başka kampanyadan gelen hücreler var; farklı kurallarla
    üretilmiş sayıları aynı tabloda eşitlemek sessiz bir hata olurdu."""
    rec = calistir()
    dis = rec["dis_kaynakli_hucreler"]
    assert isinstance(dis, list)
    for x in dis:
        assert "ÜRETMEDİ" in x["_not"]
        if x["oncul_pct"] is not None and x["u_pct"] < x["oncul_pct"]:
            assert "gözden geçirilmeli" in x["_not"]


def test_kanit_dosyasi_guncel():
    d = json.loads((KOK / "model_form_bandi.json").read_text(encoding="utf-8"))
    assert "dis_kaynakli_hucreler" in d
    assert d["olculen_hucreler"], "en az bir ölçülen hücre olmalı"
