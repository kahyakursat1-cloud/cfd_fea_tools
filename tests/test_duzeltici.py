"""Düzeltici katman — tespit et, kurulumu onar, ama SONUCU ASLA DEĞİŞTİRME.

Bu testler kütüğün dört kuralını ve —asıl önemlisi— düzelticinin kendi
sınırını bağlar. 2026-08-13'te beş düzeltme elle uygulandı ve İKİSİ gerçek bir
kusuru giderdiği hâlde sonucu düzeltmedi (silindir DES'te y⁺ 0,009→0,78 ama
Cd %0,7 değişti; NACA0012 α=8°'de y⁺ 357→2,5 ama hata %18,2→%16,6). Kusuru
gidermek nedeni bulmak değildir; düzeltici bunu gizlerse tam da makalenin
karşı çıktığı şeyi yapar.
"""
import duzeltici as D


def _kanit(**kw):
    t = {"olculen": {}, "kurulum": {}, "sinif": D.TREND}
    t["olculen"].update(kw.pop("olculen", {}))
    t["kurulum"].update(kw.pop("kurulum", {}))
    t.update(kw)
    return t


# ── Tetikleyiciler ────────────────────────────────────────────────────────────
def test_duvar_fonksiyonu_dusuk_yplusta_tetiklenir():
    k = _kanit(olculen={"yplus": {"ort": 0.009}},
               kurulum={"duvar_islemi": "nutkWallFunction"})
    assert [d.ad for d in D.uygulanabilir(k)] == ["duvar_islemini_aga_uydur"]


def test_dusuk_Re_islemi_KABA_agda_da_tetiklenir():
    """Ters yön: düşük-Re işlemi y⁺≫5 ağda da uyumsuzdur."""
    k = _kanit(olculen={"yplus": {"ort": 47.0}},
               kurulum={"duvar_islemi": "nutLowReWallFunction"})
    assert "duvar_islemini_aga_uydur" in [d.ad for d in D.uygulanabilir(k)]


def test_uyumlu_kurulum_TETIKLEMEZ():
    k = _kanit(olculen={"yplus": {"ort": 47.0}},
               kurulum={"duvar_islemi": "nutkWallFunction"})
    assert D.uygulanabilir(k) == []


def test_sigFpe_rampali_baslangici_tetikler():
    k = _kanit(olculen={"sigFpe": True})
    assert "rampali_baslangic" in [d.ad for d in D.uygulanabilir(k)]


def test_fiziksel_olmayan_katsayi_reddedilir():
    assert "fiziksel_olmayani_reddet" in [
        d.ad for d in D.uygulanabilir(_kanit(olculen={"Cl": 4769.0}))]
    assert "fiziksel_olmayani_reddet" in [
        d.ad for d in D.uygulanabilir(_kanit(olculen={"Cd": -0.019}))]


def test_asimptotik_olmayan_mertebe_ag_ailesini_tetikler():
    k = _kanit(olculen={"gozlenen_mertebe": 0.2})
    assert "referans_ag_ailesine_gec" in [d.ad for d in D.uygulanabilir(k)]


# ── ASIL KURAL: düzeltici sonucu değiştirmez ─────────────────────────────────
def test_ASIL_KURAL_hicbir_duzeltme_sonuca_dokunmaz():
    """Her `uygula` çıktısı YALNIZ kurulum anahtarı içermeli — Cl/Cd/sonuç asla."""
    yasak = {"Cl", "Cd", "sonuc", "deger", "olculen", "duzeltme_faktoru"}
    k = _kanit(olculen={"yplus": {"ort": 0.009}, "sigFpe": True,
                        "gozlenen_mertebe": 0.2, "Cl": 4769.0},
               kurulum={"duvar_islemi": "nutkWallFunction"})
    for d in D.KUTUK:
        for anahtar in d.uygula(k):
            assert anahtar not in yasak, f"{d.ad} sonuca dokunuyor: {anahtar}"


def test_her_duzeltmenin_on_kosul_ve_yan_etkisi_YAZILI():
    """Yan etki alanı ölçümden doğdu: kapanış değişikliği Tu'yu geçersiz kıldı."""
    for d in D.KUTUK:
        assert d.on_kosul.strip(), d.ad
        assert d.yan_etki.strip(), d.ad
        assert d.kaynak.strip(), d.ad


# ── Döngü politikası ──────────────────────────────────────────────────────────
def test_ETKISIZ_duzeltme_dongüyü_DURDURUR_ve_raporlanir():
    """Silindir DES vakası: kusur giderildi, sapma sürdü."""
    k = _kanit(olculen={"yplus": {"ort": 0.009}},
               kurulum={"duvar_islemi": "nutkWallFunction"})

    def yeniden_kos(kanit, degisiklik):
        return _kanit(olculen={"yplus": {"ort": 0.78}},
                      kurulum={"duvar_islemi": "nutLowReWallFunction"})

    # hata %39,6 -> %39,2: kusur giderildi ama sapma sürüyor
    hatalar = iter([39.6, 39.2])
    s = D.duzelt(k, yeniden_kos, lambda _: next(hatalar))
    assert len(s.mudahaleler) == 1
    assert s.mudahaleler[0].ise_yaradi is False
    assert s.etkisiz_sayisi == 1
    assert s.kalan_aday and "sapma sürüyor" in s.kalan_aday
    assert "design-grade DEĞİL" in s.verdikt


def test_ISE_YARAYAN_duzeltme_design_grade_e_ulasir():
    k = _kanit(olculen={"sigFpe": True})

    def yeniden_kos(kanit, degisiklik):
        return _kanit(sinif=D.VALIDATED)

    hatalar = iter([18.2, 2.0])
    s = D.duzelt(k, yeniden_kos, lambda _: next(hatalar))
    assert s.sinif == D.VALIDATED
    assert s.mudahaleler[0].ise_yaradi is True
    assert "design-grade'e ulaştı" in s.verdikt


def test_tetiklenen_duzeltme_yoksa_sonuc_OLDUGU_GIBI_kalir():
    s = D.duzelt(_kanit(), lambda k, d: k, lambda _: 5.0)
    assert s.mudahaleler == []
    assert "olduğu gibi bırakıldı" in s.verdikt


def test_sonsuz_dongu_KORUMASI():
    """Aynı düzeltme iki kez denenmez; maks deneme aşılmaz."""
    k = _kanit(olculen={"yplus": {"ort": 0.009}},
               kurulum={"duvar_islemi": "nutkWallFunction"})
    s = D.duzelt(k, lambda kn, d: kn, lambda _: 10.0, maks=3)
    assert len(s.mudahaleler) <= 3
    assert len({m.duzeltme for m in s.mudahaleler}) == len(s.mudahaleler)


def test_her_mudahale_DENETLENEBILIR_kayit_birakir():
    k = _kanit(olculen={"sigFpe": True})
    hatalar = iter([20.0, 1.0])
    s = D.duzelt(k, lambda kn, d: _kanit(sinif=D.VALIDATED),
                 lambda _: next(hatalar))
    m = s.mudahaleler[0]
    assert m.duzeltme and m.degisiklik and m.yan_etki
    assert "→" in m.ozet()
