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


def test_SINANAN_NICELIGIN_hukmu_ayikliniyor():
    """Filtre tutmazsa ölçülen şey Cd kapısı değil, L/D'nin sabit hükmü olur.

    İlk sürüm küçük harf arıyordu ("C_d") ama alan "C_D (sürükleme)"; filtre
    hiç tutmuyor ve tüm hükümlere düşüyordu. Bandı olan küp bu yüzden TREND
    görünüyordu — yani kapı ölçülüyor sanılırken başka bir şey ölçülüyordu.
    """
    s = {x["vaka"]: x for x in dk.degerlendir(dk.korpus())}
    kup = next(v for k, v in s.items() if k.startswith("kup"))
    assert kup["gci_bandi"] is True
    assert kup["guard_sinif"] == "VALIDATED", (
        "GCI bandı olan hücre band-sertifikası almalı; TREND ise filtre tutmuyor")


def test_olculemez_etiket_BELIRSIZ_isaretlenir():
    """|E| ≤ u_val ise 'sessiz hata yok' etiketi kanıtla desteklenmez."""
    s = dk.degerlendir(dk.korpus())
    bel = [x for x in s if x["hucre"] == "BELİRSİZ"]
    assert bel, "belirsiz hücre yoksa kategori sınanmamış olur"
    for x in bel:
        assert x["hata_pct"] <= x["u_val_pct"]
        assert x["sessiz_hata"] is None, "etiket kurulamayan hücreye etiket konmuş"
        assert not x["puanlanir"] and "u_val" in x["puanlanmama_nedeni"]


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


def test_negatif_etiket_BANDIYLA_kuruluyor():
    """|E| küçük ama band geniş ise 'sessiz hata yok' denemez.

    Kural POZİTİF ve NEGATİF için ayrıdır: |E|−u > τ pozitif, |E|+u < τ negatif.
    İlk sürüm yalnız '|E| ≤ u_val → belirsiz' diyordu ve bu NEGATİF için yanlış
    testti: frekans çapası |E|=%0,087 < u_val=%0,112 olduğu hâlde ikisinin
    toplamı eşiğin çok altında, yani güvenle negatif.
    """
    s = {x["vaka"]: x for x in dk.degerlendir(dk.korpus())}
    frk = next(v for k, v in s.items() if k.startswith("kiris 1."))
    assert frk["hata_pct"] < frk["u_val_pct"], "vakanın kendisi değişmiş"
    assert frk["hucre"] == "TN" and frk["puanlanir"]


def test_ozgulluk_ARTIK_yayinlanabiliyor():
    """Yeni çapalar negatif havuzunu eşiğin üstüne çıkardı."""
    o = dk.ozet(dk.degerlendir(dk.korpus()))
    assert o["TN"] >= dk.EN_AZ_HUCRE
    assert o["spec"] is not None and not o["spec_notu"]


def test_yeni_capalar_BANDLARIYLA_geliyor():
    """u_num ölçülmemiş bir çapa negatif etiket kuramaz; hepsi 3 seviyeli."""
    for c in dk.korpus():
        if c["kaynak_dosya"] == "fea_capa_bagimsiz.json":
            assert c["u_val_pct"] is not None and c["u_val_pct"] > 0
            assert not c["besledigi_kapilar"]
