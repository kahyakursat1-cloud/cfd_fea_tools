"""Bağımsız dış korpus: bulaşma dışlaması ve oran-yayınlama disiplini.

Bu modülün değeri sayının kendisinde değil, YAYINLAMAYI REDDETMESİNDE: tek
negatif hücreden özgüllük, tek kümeden genelleme çıkarılamaz. Testler o reddin
gerçekten çalıştığını ölçer --- aksi halde modül, ölçmediği bir şeyi ölçmüş
gibi raporlardı.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "experiments"))

import dis_korpus as dk  # noqa: E402


def test_bulasik_vaka_PUANLANMAZ_ama_korpusta_kalir():
    """FEA kabul sınırını besleyen vaka aynı kapıya karşı puanlanamaz."""
    s = dk.degerlendir(dk.korpus())
    bulasik = [x for x in s if x["besledigi_kapilar"]]
    assert bulasik, "bulaşık vaka hiç yoksa dışlama mekanizması sınanmamış olur"
    for x in bulasik:
        assert not x["puanlanir"]
        assert x["puanlanmama_nedeni"], "dışlama GEREKÇESİZ olamaz"
        # Korpusta KALIR: dışlananı silmek, dışlandığını da gizlerdi.
        assert x in s


def test_tek_negatif_hucreden_OZGULLUK_YAYINLANMAZ():
    o = dk.ozet([{"puanlanir": True, "hucre": h, "vaka": "x a"}
                 for h in ("TP", "TP", "TP", "TN")])
    assert o["spec"] is None and "KESTİRİLEMEZ" in o["spec_notu"]


def test_yeterli_hucre_varsa_oran_YAYINLANIR():
    """Kapı her şeyi reddetmiyor: sayı yeterince olunca oran çıkar."""
    o = dk.ozet([{"puanlanir": True, "hucre": h, "vaka": f"v{i} a"}
                 for i, h in enumerate(("TP", "TP", "TP", "TN", "TN", "TN"))])
    assert o["spec"] == 1.0 and o["sens"] == 1.0


def test_ayni_geometrinin_kurulumlari_TEK_KUME_sayilir():
    o = dk.ozet([{"puanlanir": True, "hucre": "TP", "vaka": v} for v in (
        "silindir 2B URANS", "silindir 3B URANS", "silindir 3B DES")])
    assert o["n_kume"] == 1, "dört kurulum dört bağımsız örnek değildir"


def test_hukum_ELLE_yazilmiyor_siniflandirici_kosuluyor():
    """Korpus `flagged` alanını taşımaz; sınıf koşudan gelir."""
    for c in dk.korpus():
        assert "flagged" not in c and "guard_sinif" not in c
    for x in dk.degerlendir(dk.korpus()):
        assert x["guard_sinif"] in ("VALIDATED", "TREND", "OUT")


def test_sayilar_KANIT_DOSYASINDAN_okunuyor():
    """Elle kopyalanmış bir sayı, kanıt yenilenince sessizce eskir."""
    kaynak = (KOK / "experiments" / "dis_korpus.py").read_text(encoding="utf-8")
    assert "_oku(" in kaynak
    for c in dk.korpus():
        assert c["kaynak_dosya"].endswith(".json")
        assert (KOK / c["kaynak_dosya"]).exists(), c["kaynak_dosya"]


def test_her_vaka_DIS_referans_kunyesi_tasiyor():
    """'Dış korpus' iddiası, her hücrenin yayımlanmış bir kaynağa dayanmasıdır."""
    for c in dk.korpus():
        assert len(c["dis_referans"]) > 15, c["vaka"]
