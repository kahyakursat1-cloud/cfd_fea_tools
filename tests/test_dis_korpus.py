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


def test_bulasik_vaka_SINANAN_KAPIDA_puanlanmaz():
    """Bulaşma KAPI-BAZLIDIR: hücre yalnız SINANAN kapıyı beslediyse dışlanır.

    İlk sürüm "kapı beslemiş her hücre puanlanmaz" diyordu; bu fazla katıydı
    ve basamak hücreleri ortaya çıkardı: basamak YAKINSAMA kapısını besliyor
    ama sınanan kapı band-sertifikası, dolayısıyla geçerli bir kanıt.
    """
    s = dk.degerlendir(dk.korpus())
    ayni = [x for x in s if x["sinanan_kapi"] in x["besledigi_kapilar"]]
    farkli = [x for x in s if x["besledigi_kapilar"]
              and x["sinanan_kapi"] not in x["besledigi_kapilar"]]
    assert ayni, "bulaşık vaka hiç yoksa dışlama mekanizması sınanmamış olur"
    for x in ayni:
        assert not x["puanlanir"]
        assert x["puanlanmama_nedeni"], "dışlama GEREKÇESİZ olamaz"
        assert x in s          # dışlananı silmek, dışlandığını da gizlerdi
    for x in farkli:
        # Başka bir kapıyı beslemiş olmak, bu kapı için kanıt olmayı bozmaz.
        assert x["puanlanir"] or x["hucre"] == "BELİRSİZ"


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


def test_CFD_ve_FEA_referans_kapilari_ARTIK_simetrik():
    """Ölçülen ayrışma (2026-08-19) kapatıldı.

    `classify_fea` referans hatasını kapı olarak kullanıyordu, `classify_cfd`
    ise C_D hükmünü YALNIZ banda bakarak veriyordu: GCI bandı olan bir koşu
    referanstan ne kadar uzak olursa olsun DOĞRULANMIŞ alıyordu. Doğrudan
    sınandı — Cd=0,30 ile Cd=1,20 aynı hükmü aldı. Aynı açık FEA tarafında
    bilinçli kapatılmıştı; CFD tarafında açıktı.
    """
    from validity_envelope import (
        CD_REFERANS_KABUL_PCT,
        classify_cfd,
        classify_fea,
    )

    def _cd(**kw):
        v = classify_cfd("kup", 0.0, 0.12, has_gci_band=True, Cl=0.0, Cd=1.0, **kw)
        return next(x for x in v if x.quantity.startswith("C_D"))

    # Referans BEYAN EDİLMEDİYSE davranış birebir eski: hiçbir koşu yeniden
    # sınıflanmaz. Kapının yönü bilinçli olarak böyle.
    assert _cd().klass == "VALIDATED"
    assert _cd(referans_hata_pct=CD_REFERANS_KABUL_PCT - 1).klass == "VALIDATED"

    kotu = _cd(referans_hata_pct=CD_REFERANS_KABUL_PCT + 1)
    assert kotu.klass == "TREND" and not kotu.design_safe
    assert kotu.kod == "CD_REFERANS_HATASI"

    # FEA tarafı AYNI yapıda: iki yol artık ayrışmıyor.
    assert any(x.design_safe for x in classify_fea(referans_hata_pct=1.0,
                                                   nicelik="gerilme"))
    assert not any(x.design_safe for x in classify_fea(referans_hata_pct=25.0,
                                                       nicelik="gerilme"))


def test_korpus_guard_a_REFERANSI_vermiyor_dairesellik():
    """Dedektöre cevabı söyleyip 'buldun mu?' diye sormak ölçüm değildir.

    `classify_cfd` artık `referans_hata_pct` kapısı taşıyor. Korpustaki hata
    değeri referansın TA KENDİSİ olduğu için onu guard'a geçirmek duyarlılığı
    yapay olarak 1'e çıkarırdı. Bu test o daireselliği kapalı tutar.
    """
    kaynak = (KOK / "experiments" / "dis_korpus.py").read_text(encoding="utf-8")
    i = kaynak.index("v = classify_cfd(")
    cagri = kaynak[i:kaynak.index(")", kaynak.index("ag_yeterli", i))]
    assert "referans_hata_pct" not in cagri, (
        "korpus guard'a referans hatasını geçiriyor — ölçüm dairesel olur")


def test_referans_kapisi_yalniz_BEYAN_EDILINCE_isirir():
    """Kapı varsayılan yolu değiştirmez; yalnız referans beyan edilince çalışır.

    `hizmet` referansı BİLİNÇLİ olarak geçirir (kullanıcı `referans_cd`
    dediyse ölçülmek istiyordur). Rapor ve GUI yolları geçirmez: onların elinde
    beyan edilmiş bir referans yok, uydurmak yanlış olurdu.
    """
    from validity_envelope import classify_cfd

    def _cd(**kw):
        v = classify_cfd("ucak", 4.0, 0.12, has_gci_band=True, Cl=0.4, Cd=0.05, **kw)
        return next(x for x in v if x.quantity.startswith("C_D"))

    assert _cd().kod == "CD_GCI_BANDI_VAR"      # referanssız → eski davranış

    src = (KOK / "hizmet.py").read_text(encoding="utf-8")
    assert "referans_hata_pct=ref_hata" in src, "hizmet referansı hükme sokmuyor"
    # Beyan yoksa kapı hiç kurulmamalı: `if referans_cd and ...` koşulu şart.
    assert "if referans_cd and" in src

    for yol in ("vehicle_report.py", "app_analyzer.py"):
        s = (KOK / yol).read_text(encoding="utf-8")
        j = s.find("classify_cfd(")
        assert j > 0, yol
        assert "referans_hata_pct" not in s[j:j + 400], (
            f"{yol} artık referans geçiriyor — beyan edilmiş referansı yok, "
            "bu bir ÜRETİM DAVRANIŞ DEĞİŞİKLİĞİDİR")


def test_BEYAN_EDILEN_referans_hukme_giriyor():
    """Referans beyan etmek, ölçülmeyi istemektir.

    `referans_cd` hizmet katmanında vardı ama YALNIZ düzelticiye gidiyordu:
    kullanıcı referansını söylediğinde araç onu düzeltme için kullanıp hüküm
    verirken görmezden geliyordu. %40 sapan bir koşu yine DOĞRULANMIŞ
    alabiliyordu.
    """
    import types

    import hizmet

    class _R:
        status, vehicle_type, alpha_deg, velocity = "ok", "ucak", 4.0, 30.0
        cd, cl, ld, aref_m2, drag_N = 0.50, 0.40, 0.8, 1.0, 10.0
        belirsizlik = mesh = convergence = None
        case_dir, report, error = "", "", None
        mesh_duyarlilik = {"gci": True, "verdikt": "✅ ok"}

    def _kur(monkey_mod):
        mod = types.ModuleType("vehicle_pipeline")
        mod.run_vehicle_analysis = lambda stl, **kw: _R()
        sys.modules["vehicle_pipeline"] = mod

    _kur(None)
    try:
        # Referans YOK → davranış eskisi gibi
        o = hizmet.analiz_et("x.stl")
        assert o["referans"] is None

        # Referans BEYAN EDİLDİ ve sapma büyük → C_D tasarımda kullanılmaz
        o = hizmet.analiz_et("x.stl", referans_cd=0.30)      # %66,7 sapma
        assert o["referans"]["hata_pct"] > 10
        cd_h = next(x for x in o["gecerlilik"]["nicelikler"]
                    if x["nicelik"].startswith("C_D"))
        assert cd_h["kod"] == "CD_REFERANS_HATASI"
        assert not cd_h["tasarimda_kullanilir"]

        # Referans YAKIN → kapı ısırmaz
        o = hizmet.analiz_et("x.stl", referans_cd=0.49)      # %2 sapma
        cd_h = next(x for x in o["gecerlilik"]["nicelikler"]
                    if x["nicelik"].startswith("C_D"))
        assert cd_h["kod"] == "CD_GCI_BANDI_VAR"
    finally:
        sys.modules.pop("vehicle_pipeline", None)


def test_kapi_BEYAN_EDILEN_butceye_karsi_sinar_duz_yuzdeye_degil():
    """Sabit eşik, model biasını DOĞRU ölçen bir koşuyu cezalandırıyordu.

    Geriye-basamak (Driver & Seegmiller) %10,46 sapıyor ama o sapma ölçülmüş
    `separated.wall_resolved` model-form bandının (%12,0) İÇİNDE: u_val =
    √(2,39² + 1,60² + 12,0²) = %12,34, yani R_E = 0,85. Koşu kötü değil, model
    biasını doğru ölçmüş. Düz %10 eşiği bunu göremiyordu.
    """
    from validity_envelope import CD_REFERANS_KABUL_PCT, classify_cfd

    def _cd(**kw):
        v = classify_cfd("kup", 0.0, 0.12, has_gci_band=True, Cl=0.0, Cd=1.0, **kw)
        return next(x for x in v if x.quantity.startswith("C_D"))

    # Bütçenin İÇİNDE → düşürülmez (düz eşik olsa düşerdi: 10,46 > 10)
    assert _cd(referans_hata_pct=10.464, u_val_pct=12.34).klass == "VALIDATED"
    assert CD_REFERANS_KABUL_PCT < 10.464, "vaka artık düz eşiği aşmıyor"

    # Bütçenin DIŞINDA → düşer. Kapı gevşemedi, kanıta bağlandı.
    assert _cd(referans_hata_pct=40.0, u_val_pct=12.34).kod == "CD_REFERANS_HATASI"

    # Bütçe BEYAN EDİLMEMİŞSE muhafazakâr düz eşiğe düşülür.
    assert _cd(referans_hata_pct=12.0).kod == "CD_REFERANS_HATASI"
    assert _cd(referans_hata_pct=8.0).klass == "VALIDATED"
