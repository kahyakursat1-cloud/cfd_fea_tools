"""URANS eskalasyonu — "kesin çözüm URANS'tır" cümlesi UYGULANABİLİR mi?

Hüküm salınan koşuyu doğru tespit ediyor ve doğru olanı söylüyordu: akış
zaman-bağımlıdır. Ama orada duruyordu. Kullanıcının elinde ne zaman adımı
vardı, ne kaç adım koşacağı, ne de maliyeti. Aynı kusur `propeller_params`'ta
da yaşandı: "sınırı aştın" demek yetmiyordu, o hız ve çapta ne kadar mümkün
olduğu da yazılmalıydı.

Bu testler REÇETENİN KURALINI bağlar, sayısını değil: Strouhal öncülü
değişirse sayılar değişir ama zaman adımı hâlâ periyodun yüzde biri olmalı ve
öncül olduğu HÂLÂ yazmalı.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from urans_kapisi import (  # noqa: E402
    ADIM_PER_PERIYOT,
    GECIS_PERIYODU,
    ISTATISTIK_PERIYODU,
    recete_metni,
    urans_recetesi,
)

SALINIYOR = {"osilasyon": True, "genlik_pct": 4.2, "gecis": 11}


def test_salinim_yoksa_recete_YOK():
    r = urans_recetesi({"osilasyon": False}, 0.5, 20.0, "bluff")
    assert r["gerekli"] is False
    assert recete_metni(r) == []


def test_zaman_adimi_PERIYODUN_yuzde_biri():
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    assert r["zaman_adimi_s"] == pytest.approx(r["periyot_s"] / ADIM_PER_PERIYOT,
                                               rel=1e-2)


def test_frekans_STROUHAL_tanimindan():
    """f = St·U/L. Hız iki katına çıkarsa frekans da iki katına çıkar,
    zaman adımı yarıya iner."""
    yavas = urans_recetesi(SALINIYOR, 0.5, 10.0, "bluff")
    hizli = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    assert hizli["frekans_hz"] == pytest.approx(2 * yavas["frekans_hz"], rel=1e-6)
    assert hizli["zaman_adimi_s"] < yavas["zaman_adimi_s"]


def test_buyuk_cisim_DAHA_UZUN_periyot():
    kucuk = urans_recetesi(SALINIYOR, 0.2, 20.0, "bluff")
    buyuk = urans_recetesi(SALINIYOR, 2.0, 20.0, "bluff")
    assert buyuk["periyot_s"] > kucuk["periyot_s"]


def test_adim_sayisi_GECIS_ARTI_ISTATISTIK():
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    assert r["adim_sayisi"] == (GECIS_PERIYODU + ISTATISTIK_PERIYODU) * ADIM_PER_PERIYOT


def test_ONCUL_oldugu_her_ciktida_yaziyor():
    """En tehlikeli hâl: türetilmiş sayıların ölçüm sanılması. Kararlı
    çözücüde iterasyon zaman değildir; frekans literatür öncülünden gelir."""
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    metin = " ".join(recete_metni(r))
    assert "ÖNCÜL" in metin.upper()
    assert "Courant" in metin, "Δt yalnız periyottan geliyor; Co kısıtı söylenmeli"


def test_maliyet_OLCULEN_iterasyon_maliyetinden():
    """Tahmin uydurma bir katsayıdan değil, aynı ağda aynı makinede ölçülen
    iterasyon maliyetinden gelmeli."""
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff",
                       rans_sure_s=1200.0, rans_iterasyon=600)
    assert r["tahmini_sure_s"] > 0
    iki_kat = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff",
                             rans_sure_s=2400.0, rans_iterasyon=600)
    assert iki_kat["tahmini_sure_s"] == pytest.approx(2 * r["tahmini_sure_s"], rel=1e-6)


def test_maliyet_bilinmiyorsa_SURE_UYDURULMUYOR():
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    assert "tahmini_sure_s" not in r
    assert "tahmini" not in recete_metni(r)[0]


def test_uzunluk_yoksa_HESAPLANAMADI_deniyor():
    """Sessizce atlamak yerine niçin hesaplanamadığı söylenmeli."""
    r = urans_recetesi(SALINIYOR, None, 20.0, "bluff")
    assert r["gerekli"] is True and r["hesaplanabilir"] is False
    assert "hesaplanamaz" in r["gerekce"]
    assert recete_metni(r) == [r["gerekce"]]


# ── Hükme gerçekten bağlı mı ────────────────────────────────────────────────

def _kapi(kosu):
    from validity_envelope import sonuc_kapisi
    conv = {"drift_ok": True, "rezidual_ok": False, "cd_drift_son20pct": 1.2,
            "salinim": SALINIYOR}
    return sonuc_kapisi({"verdict": "ok"}, conv, None, kosu=kosu)


def test_salinan_kosunun_HUKMUNDE_recete_var():
    k = _kapi({"lref_m": 0.5, "velocity": 20.0, "rejim": "bluff",
               "sure_s": 1800.0, "iterasyon": 600})
    assert k["seviye"] == "uyari"
    assert any("URANS reçetesi" in g for g in k["gerekce"])


def test_kosu_baglami_verilmezse_hukum_COKMEZ():
    """Eski çağıranlar `kosu` geçmiyor; reçete olmaz ama hüküm çalışmalı."""
    k = _kapi(None)
    assert k["seviye"] == "uyari"
    assert any("SALINIYOR" in g for g in k["gerekce"])


def test_KABUL_edilen_salinimli_kosuya_recete_EKLENMIYOR():
    """Genliği bantta olan salınım kabul ediliyor; orada reçete gereksiz
    gürültüdür — kullanıcı zaten devam ediyor."""
    from validity_envelope import sonuc_kapisi
    conv = {"drift_ok": True, "rezidual_ok": True, "cd_drift_son20pct": 0.4,
            "salinim": {"osilasyon": True, "genlik_pct": 1.0, "gecis": 6}}
    k = sonuc_kapisi({"verdict": "ok"}, conv,
                     {"u_sayisal_pct": 2.0, "u_model_pct": 12.0},
                     kosu={"lref_m": 0.5, "velocity": 20.0, "rejim": "bluff"})
    assert k["seviye"] == "ok"
    assert not any("URANS reçetesi" in g for g in k["gerekce"])


# ── KOŞUM: öncülü ölçümle değiştirme ────────────────────────────────────────

def _sinus(f0: float, sure: float = 3.0, n: int = 2000,
           ort: float = 0.5, genlik: float = 0.02):
    t = [i * sure / n for i in range(n)]
    return t, [ort + genlik * math.sin(2 * math.pi * f0 * x) for x in t]


@pytest.mark.parametrize("f0", [3.5, 8.0, 25.0])
def test_frekans_SENTETIK_sinyalde_dogru(f0):
    """İlk sürüm işaret değişimlerini SAYIYORDU ve 8 Hz'de %11 şaşıyordu:
    pencere tam periyoda oturmadığında kısmi periyotlar sayımı bozuyor.
    Ölçülen frekans doğrudan Δt'ye girdiği için o hata reçeteyi o kadar
    kaydırırdı."""
    from urans_kapisi import salinim_olc
    o = salinim_olc(*_sinus(f0))
    assert o["olculdu"]
    assert abs(o["frekans_hz"] - f0) / f0 < 0.01


def test_genlik_ve_ortalama_dogru():
    from urans_kapisi import salinim_olc
    o = salinim_olc(*_sinus(8.0, ort=0.5, genlik=0.02))
    assert o["ortalama"] == pytest.approx(0.5, abs=1e-3)
    assert o["genlik"] == pytest.approx(0.02, rel=0.02)


def test_OTURMUS_cozumde_salinim_yok_deniyor():
    """Salınmayan seride uydurma bir frekans üretilmemeli."""
    from urans_kapisi import salinim_olc
    t = [i * 0.001 for i in range(2000)]
    o = salinim_olc(t, [0.5 + 1e-6 * i for i in range(2000)])   # düz sürüklenme
    assert o["olculdu"] is False
    assert "salınım görünmüyor" in o["neden"]


def test_GECIS_penceresi_atiliyor():
    """Başlangıç geçicisi ortalamayı ve genliği kirletir; ilk %25 atılır."""
    from urans_kapisi import salinim_olc
    t, y = _sinus(8.0)
    kirli = [v + 5.0 * math.exp(-x * 20) for v, x in zip(y, t)]   # sönen geçici
    o = salinim_olc(t, kirli)
    assert o["olculdu"]
    assert abs(o["frekans_hz"] - 8.0) / 8.0 < 0.02


def test_az_periyotta_UYARI_veriyor():
    from urans_kapisi import salinim_olc
    o = salinim_olc(*_sinus(2.0, sure=2.0))     # ~3 periyot
    assert o["olculdu"] and o["periyot_sayisi"] < 10
    assert "istatistik" in (o["_uyari"] or "")


def test_cok_frekansli_sinyalde_SACILMA_soyleniyor():
    """Medyan baskın modu verir ama tek frekanslı olmadığını gizlememeli."""
    from urans_kapisi import salinim_olc
    t, y = _sinus(8.0)
    _, y2 = _sinus(3.0, genlik=0.03)
    o = salinim_olc(t, [a + b - 0.5 for a, b in zip(y, y2)])
    if o["olculdu"] and o["periyot_sacilmasi_pct"] > 30:
        assert "tek frekanslı değil" in (o["_uyari"] or "")


def test_recete_OLCUMLE_guncelleniyor():
    """Koşudan sonra öncüle sarılmak, elde ölçüm varken tahmini tercih
    etmektir."""
    from urans_kapisi import recete_guncelle, salinim_olc, urans_recetesi
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    g = recete_guncelle(r, salinim_olc(*_sinus(4.0)))
    assert g["kaynak"].startswith("ÖLÇÜM")
    assert g["frekans_hz"] == pytest.approx(4.0, rel=0.01)
    assert g["oncul_frekans_hz"] == r["frekans_hz"]
    assert g["oncul_sapmasi_pct"] > 0
    assert g["zaman_adimi_s"] == pytest.approx(1 / 4.0 / 100, rel=0.02)


def test_olculemezse_ONCUL_korunuyor():
    from urans_kapisi import recete_guncelle, urans_recetesi
    r = urans_recetesi(SALINIYOR, 0.5, 20.0, "bluff")
    g = recete_guncelle(r, {"olculdu": False, "neden": "pencere boş"})
    assert g["frekans_hz"] == r["frekans_hz"]
    assert "öncül korundu" in g["_olcum_notu"]


# ── Case yazıcı: zaman-çözünür sözlükler ────────────────────────────────────

def _yaz(tmp_path, transient: bool):
    from analysis.openfoam_runner import _write_fv_schemes, _write_fv_solution
    (tmp_path / "system").mkdir(exist_ok=True)
    _write_fv_solution(tmp_path, False, transient, 3)
    _write_fv_schemes(tmp_path, transient)
    return ((tmp_path / "system" / "fvSolution").read_text(encoding="utf-8"),
            (tmp_path / "system" / "fvSchemes").read_text(encoding="utf-8"))


def test_transient_PIMPLE_ve_residualControl_YOK(tmp_path):
    """Kararlı-halde residualControl 'çözüm oturdu' demektir; zaman-çözünürde
    koşuyu ZAMANIN ORTASINDA durdururdu."""
    sol, _ = _yaz(tmp_path, True)
    assert "PIMPLE" in sol and "nOuterCorrectors 3" in sol
    assert "residualControl" not in sol


def test_transient_semasi_IKINCI_mertebe_ve_boundedsiz(tmp_path):
    """`bounded` yalnız SIMPLE içindir ve zaman doğruluğunu bozar."""
    _, sc = _yaz(tmp_path, True)
    assert "backward" in sc and "steadyState" not in sc
    assert "bounded" not in sc


def test_transient_relaxation_BIR(tmp_path):
    """Alt-gevşetme zaman doğruluğunu bozar: çözüm her adımda tam yakınsamaz."""
    sol, _ = _yaz(tmp_path, True)
    assert "fields { p 1; }" in sol


def test_kararli_hal_DAVRANISI_degismedi(tmp_path):
    """Varsayılan kapalı: transient=False iken her sözlük eskisi gibi."""
    sol, sc = _yaz(tmp_path, False)
    assert "SIMPLE" in sol and "residualControl" in sol and "PIMPLE" not in sol
    assert "steadyState" in sc and "bounded Gauss" in sc
    assert "fields { p 0.3; }" in sol


def test_controlDict_transient_ADJUSTABLE_yaziyor(tmp_path, monkeypatch):
    from analysis.openfoam_runner import CFDCase, _write_control_dict
    (tmp_path / "system").mkdir(exist_ok=True)
    c = CFDCase(name="t", stl_path="x.stl", transient=True,
                delta_t=1.25e-3, end_time_s=2.5)
    monkeypatch.setattr(type(c), "lref", property(lambda self: 1.0))
    _write_control_dict(tmp_path, c, "yuzey", 1.0)
    txt = (tmp_path / "system" / "controlDict").read_text(encoding="utf-8")
    assert "deltaT          0.00125" in txt
    assert "endTime         2.5" in txt
    assert "adjustableRunTime" in txt and "adjustableTimeStep yes" in txt
    assert "maxCo" in txt


def test_transient_PIMPLE_FINAL_girdilerini_yaziyor(tmp_path):
    """PIMPLE son dış iterasyonda `<alan>Final` arar ve bulamazsa koşuyu FATAL
    IO ERROR ile düşürür. Sentetik test bunu göremezdi; gerçek silindir koşusu
    ilk zaman adımında yakaladı.

    Final girdisi DAHA SIKI olmalı (relTol 0): dış döngü bittiğinde o adımın
    çözümü artık düzeltilmeyecektir, gevşek bırakılan hata zamanda birikir.
    """
    sol, _ = _yaz(tmp_path, True)
    assert "pFinal" in sol and "Final\"" in sol
    son = sol[sol.index("pFinal"):]
    assert "relTol          0;" in son
    # U ailesi GAMG'ye kaymamali: simetrik olmayan momentum matrisinde uygun degil
    ublok = sol[sol.index('"(U|k|omega|nuTilda|e|h)Final"'):][:220]
    assert "smoothSolver" in ublok and "GAMG" not in ublok


def test_kararli_halde_FINAL_girdisi_YOK(tmp_path):
    """SIMPLE'da Final yoktur; yazmak sözlüğü şişirir ve yanlış izlenim verir."""
    sol, _ = _yaz(tmp_path, False)
    assert "Final" not in sol


def test_GURULTU_salinim_sayilmiyor():
    """Ölçüldü: tümüyle simetrik kalmış silindir koşusunda girdap dökülmesi
    hiç başlamadı ve Cl genliği 1e-22 idi — ama işaret geçişleri yine sayılıp
    'f=2,87 Hz ölçüldü' denmişti. Yuvarlama gürültüsünün frekansı bir fizik
    değildir."""
    from urans_kapisi import salinim_olc
    t, y = _sinus(3.0, ort=0.5, genlik=1e-22)
    o = salinim_olc(t, y)
    assert o["olculdu"] is False
    assert "GÜRÜLTÜ" in o["neden"]


def test_gercek_salinim_ESIKTEN_geciyor():
    """Kapı gerçek salınımı elemesin: %4 genlik açık ara geçmeli."""
    from urans_kapisi import salinim_olc
    o = salinim_olc(*_sinus(3.0, ort=0.5, genlik=0.02))
    assert o["olculdu"] is True


def test_ortalama_SIFIRA_yakinken_mutlak_taban():
    """Cl gibi ortalaması ~0 olan büyüklükte göreli eşik anlamsızdır; mutlak
    taban devreye girer."""
    from urans_kapisi import GENLIK_ESIGI_MUTLAK, salinim_olc
    kucuk = salinim_olc(*_sinus(3.0, ort=0.0, genlik=GENLIK_ESIGI_MUTLAK / 10))
    buyuk = salinim_olc(*_sinus(3.0, ort=0.0, genlik=1e-3))
    assert kucuk["olculdu"] is False and buyuk["olculdu"] is True


# ── Grading çözücü: ilk hücre seviyeler arasında SABİT ──────────────────────

def test_grading_ilk_hucreyi_HEDEFE_oturtuyor():
    """Ağ inceldikçe hücre sayısı artar; grading sabit kalırsa ilk hücre
    incelir ve üç seviye ÜÇ FARKLI duvar işlemine düşer — GCI ailesi anlamını
    yitirir. Grading her seviyede hedefe göre çözülür."""
    sys.path.insert(0, str(KOK / "experiments"))
    import basamak_ayrilma as ba
    from basamak_duvar_fonksiyonu import grading_coz
    hedef = 850e-6
    for n in (40, 56, 80):
        g = grading_coz(ba.H_STEP, n, hedef)
        assert ba.ilk_hucre_m(ba.H_STEP, n, g) == pytest.approx(hedef, rel=1e-3)


def test_grading_TEK_TIPTEN_kalinsa_birden_kucuk():
    """Hedef ilk hücre tek-tip dağılımdan kalınsa grading<1 olmalı (duvarda
    seyrek, uzakta sık); ince ise >1."""
    sys.path.insert(0, str(KOK / "experiments"))
    import basamak_ayrilma as ba
    from basamak_duvar_fonksiyonu import grading_coz
    tek_tip = ba.H_STEP / 40
    assert grading_coz(ba.H_STEP, 40, tek_tip * 3) < 1.0
    assert grading_coz(ba.H_STEP, 40, tek_tip / 3) > 1.0


def test_deneysel_u_ref_XR_belirsizliginden():
    """u_D uydurulmuyor: Driver & Seegmiller Xr/H = 6,26 ± 0,10."""
    sys.path.insert(0, str(KOK / "experiments"))
    import basamak_ayrilma as ba
    from basamak_duvar_fonksiyonu import U_REF_PCT
    assert pytest.approx(ba.XR_BELIRSIZLIK / ba.XR_DENEY * 100, rel=1e-6) == U_REF_PCT


def test_QoI_duraganligi_rezidualin_YERINE_gecebiliyor():
    """`residualControl tetiklenmedi` ile `Xr hâlâ hareket ediyor` AYNI ŞEY
    DEĞİLDİR. Ayrım `validity_envelope`'ta kuruluydu ama çapa betiklerine hiç
    uygulanmamıştı ve somut zarar verdi: duvar-fonksiyonu L1 koşusunda
    rezidüeller 20.000 iterasyon platoda kaldı, ama Xr son dört anlık
    görüntüde %0,15 içinde oturmuştu. O koşu 'yakınsamadı' diye atılacaktı.

    KAPI GEVŞEMİYOR: saçılma ölçülüp eşiğe vuruluyor ve rezidüel durumu
    çıktıda açıkça yazılıyor.
    """
    sys.path.insert(0, str(KOK / "experiments"))
    from basamak_duvar_fonksiyonu import QOI_SACILMA_ESIGI_PCT
    assert 0 < QOI_SACILMA_ESIGI_PCT <= 2.0, "eşik anlamlı bir bantta olmalı"


def test_duraganlik_notu_rezidueli_GIZLEMIYOR():
    """Kabul ediliyorsa bile rezidüelin tetiklenmediği yazılmalı: birini yazıp
    diğerini gizlemek ya bulguyu bastırır ya güveni şişirir."""
    kanit = KOK / "basamak_duvar_fonksiyonu.json"
    if not kanit.exists():
        pytest.skip("kanıt yok (python experiments/basamak_duvar_fonksiyonu.py)")
    d = json.loads(kanit.read_text(encoding="utf-8"))
    for s in d.get("seviyeler", []):
        if s.get("durum") == "ok" and s.get("residualControl_gecti") is False:
            assert s.get("_yakinsama_notu"), f"{s['ad']}: rezidüel durumu gizli"
            assert "TETIKLENMEDI" in s["_yakinsama_notu"]
