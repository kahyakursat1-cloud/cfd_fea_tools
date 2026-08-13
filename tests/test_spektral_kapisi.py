"""Frekans ölçümü TEK yönteme bırakılamaz — çok-frekanslı sinyalde medyan şaşar.

Ölçülen kusur: `salinim_olc` baskın frekansı yukarı-geçişlerin MEDYAN periyodundan
bulur ve çok-frekanslı sinyalde baskın modu ayıramadığını kendi docstring'inde
söyler. Söylemek yetmiyordu: silindir DES koşusunun %70'inde ölçüm "periyot
saçılması %98" uyarısını verdi ve St'yi 0,2545 raporladı; aynı pencerede güç
spektrumunun tepesi 0,2689 dedi. Yöntemler %5,5 ayrışıyordu ve hiçbir tüketici
bunu görmüyordu — kanıt dosyasına tek bir St yazılıyordu.

Bu testler iki şeyi bağlar: (1) spektral ölçüm cevabı BİLİNEN sinyallerde doğru
olmalı, (2) iki yöntem ayrıştığında çapraz kontrol bunu SÖYLEMELİ. Ayrışmayı
gizleyip tek sayı yazmak, ölçmediğimiz bir şeyi ölçmüş gibi göstermektir.
"""
import math
import random

from urans_kapisi import frekans_capraz_kontrol, salinim_olc, spektral_olc

N, T = 4000, 40.0
DUZGUN_T = [i * T / (N - 1) for i in range(N)]


def _sinus(t, f, genlik=1.0):
    return [genlik * math.sin(2 * math.pi * f * x) for x in t]


def test_spektral_tek_frekansta_dogru():
    """Cevabı bilinen sinyal: 0,25 Hz → %0,5'ten iyi."""
    o = spektral_olc(DUZGUN_T, _sinus(DUZGUN_T, 0.25), gecis_orani=0.0)
    assert o["olculdu"], o.get("neden")
    hata = 100 * abs(o["frekans_hz"] - 0.25) / 0.25
    assert hata < 0.5, f"tek frekansta %{hata:.2f} hata"


def test_ASIL_KUSUR_iki_frekansta_medyan_sasar_spektral_sasmaz():
    """Yöntem farkını ÖLÇER: ikincil mod medyanı kaydırır, spektrumu kaydırmaz."""
    y = [a + b for a, b in zip(_sinus(DUZGUN_T, 0.25),
                               _sinus(DUZGUN_T, 0.40, 0.45))]
    gecis = salinim_olc(DUZGUN_T, y, gecis_orani=0.0)
    spek = spektral_olc(DUZGUN_T, y, gecis_orani=0.0)
    assert gecis["olculdu"] and spek["olculdu"]

    h_gecis = 100 * abs(gecis["frekans_hz"] - 0.25) / 0.25
    h_spek = 100 * abs(spek["frekans_hz"] - 0.25) / 0.25
    assert h_gecis > 2.0, ("geçiş-medyanı bu sinyalde şaşmalıydı; şaşmıyorsa "
                           "testin kurgusu baskın modu yeterince kirletmiyor")
    assert h_spek < 2.0, f"spektral baskın modu ayıramadı (%{h_spek:.2f})"
    assert h_spek < h_gecis


def test_ayrisma_GIZLENMEZ_capraz_kontrol_soyler():
    """İki yöntem ayrıştığında verdikt bunu açıkça bildirmeli."""
    y = [a + b for a, b in zip(_sinus(DUZGUN_T, 0.25),
                               _sinus(DUZGUN_T, 0.40, 0.45))]
    ck = frekans_capraz_kontrol(salinim_olc(DUZGUN_T, y, gecis_orani=0.0),
                                spektral_olc(DUZGUN_T, y, gecis_orani=0.0))
    assert ck["karsilastirildi"]
    assert ck["uyumlu"] is False
    assert "AYRIŞTI" in ck["verdikt"]


def test_uyusma_da_soylenir():
    """Tek frekanslı sinyalde iki yöntem uyuşur ve verdikt bunu bildirir."""
    y = _sinus(DUZGUN_T, 0.25)
    ck = frekans_capraz_kontrol(salinim_olc(DUZGUN_T, y, gecis_orani=0.0),
                                spektral_olc(DUZGUN_T, y, gecis_orani=0.0))
    assert ck["uyumlu"] is True


def test_duzensiz_orneklemede_dogru():
    """adjustableTimeStep düzensiz aralık verir; yeniden örnekleme bozmamalı."""
    random.seed(11)
    t, x = [], 0.0
    while x < T:
        t.append(x)
        x += (T / N) * random.uniform(0.5, 1.5)
    o = spektral_olc(t, _sinus(t, 0.25), gecis_orani=0.0)
    assert o["olculdu"], o.get("neden")
    assert 100 * abs(o["frekans_hz"] - 0.25) / 0.25 < 1.0


def test_tek_tepeli_OLMAYAN_spektrum_isaretlenir():
    """İki eşit güçlü ton: 'baskın frekans' anlamsızdır, uyarı verilmeli."""
    y = [a + b for a, b in zip(_sinus(DUZGUN_T, 0.25),
                               _sinus(DUZGUN_T, 0.40, 0.98))]
    o = spektral_olc(DUZGUN_T, y, gecis_orani=0.0)
    assert o["olculdu"]
    assert o["belirginlik"] is not None and o["belirginlik"] < 3, o["belirginlik"]
    assert o["_uyari"] and "tek-tepeli DEĞİL" in o["_uyari"]


def test_sabit_sinyal_frekans_URETMEZ():
    """Salınım yoksa frekans uydurulmaz — gürültünün frekansı fizik değildir."""
    o = spektral_olc(DUZGUN_T, [1.0] * N, gecis_orani=0.0)
    assert o["olculdu"] is False


def test_yetersiz_ornek_reddedilir():
    o = spektral_olc([0.0, 1.0, 2.0], [0.0, 1.0, 0.0], gecis_orani=0.0)
    assert o["olculdu"] is False


# ── Kurulum kapısı: y⁺ ile İLAN EDİLEN bant karşılaştırılmalı ────────────────
# Ölçülen kusur: 10,5 saatlik DES koşusunun kanıt dosyası hem y⁺ ölçümünü
# (0,0091) hem `yplus_bandi`'nı ([30,300]) taşıyordu — 3299 kat ayrı — ama
# hiçbir tüketici ikisini karşılaştırmıyordu. Hüküm sapmayı "çözünürlük
# yetmedi" diye okuyordu; gerçek neden duvar fonksiyonlarının y⁺≈1 ağında
# kullanılmasıydı, yani teşhis tersine dönmüştü.

def _des_modulu():
    import importlib.util
    from pathlib import Path
    kok = Path(__file__).resolve().parent.parent
    s = importlib.util.spec_from_file_location(
        "des3b", kok / "experiments" / "silindir_des_3b.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _kanit(yplus_ort, band=(30.0, 300.0)):
    return {"olculen": {"yplus": {"ort": yplus_ort}},
            "kurulum": {"yplus_bandi": list(band)}}


def test_ASIL_KUSUR_yplus_bant_disindaysa_kapi_duser():
    """Test biçimlendirilmiş sayıya değil DAVRANIŞA bağlanır: kat sayısını
    dizgi olarak beklemek, eşiği değiştirmeden yuvarlama değişince kırılır."""
    m = _des_modulu()
    uyari = m._duvar_uyumu(_kanit(0.0091))
    assert uyari is not None
    assert "KAT DIŞINDA" in uyari and "SINANAMAZ" in uyari
    kat = int(uyari.split(" KAT DIŞINDA")[0].split()[-1])
    assert kat > 1000, kat


def test_bant_icinde_kapi_gecer():
    m = _des_modulu()
    assert m._duvar_uyumu(_kanit(120.0)) is None


def test_bandin_USTUNDE_de_yakalanir():
    m = _des_modulu()
    uyari = m._duvar_uyumu(_kanit(3000.0))
    assert uyari and "KAT DIŞINDA" in uyari


def test_olcum_yoksa_kapi_SESSIZ_gecer():
    """y⁺ ölçülmemişse uydurma hüküm verilmez."""
    m = _des_modulu()
    assert m._duvar_uyumu({"olculen": {}, "kurulum": {}}) is None


# ── Branch B kabul sınırı (dış hakem, 2026-08-13) ────────────────────────────
# Ölçülen açık: kapalı-form referans hatası yalnız RAPORLANIYOR, kapı görevi
# görmüyordu. Mevcut altı benchmark %0,0–4,8 olduğu için pratikte fark
# etmiyordu, ama %20 hatalı yeni bir benchmark da design-grade alabilirdi.

def _ve():
    # importlib ile IKINCI kez yuklemek dataclass olusturmayi bozuyor
    # ('NoneType' has no attribute __dict__); modul normal yoldan ice aktarilir.
    import validity_envelope
    return validity_envelope


def test_ASIL_KUSUR_buyuk_referans_hatasi_design_grade_ALAMAZ():
    ve = _ve()
    v = ve.classify_fea(referans_hata_pct=20.0, nicelik="gerilme")
    assert ve.overall_class(v) != ve.VALIDATED, [x.klass for x in v]
    assert "kabul sınırı" in v[0].message


def test_mevcut_ALTI_benchmark_hicbiri_yeniden_siniflanmaz():
    """%0,0–4,8 bandındaki altı vaka kapıdan geçmeli — kapı geçmişi bozmamalı."""
    ve = _ve()
    for e in (0.0, 0.2, 1.0, 1.3, 1.7, 4.8):
        v = ve.classify_fea(referans_hata_pct=e, nicelik="gerilme")
        assert ve.overall_class(v) == ve.VALIDATED, (e, [x.klass for x in v])


def test_yer_degistirme_daha_SIKI_sinira_tabi():
    """Birincil FE bilinmeyeni türev gerektirmez, %5'e tabi; gerilme %10."""
    ve = _ve()
    assert ve.overall_class(ve.classify_fea(referans_hata_pct=7.0,
                                            nicelik="yer_degistirme")) != ve.VALIDATED
    assert ve.overall_class(ve.classify_fea(referans_hata_pct=7.0,
                                            nicelik="gerilme")) == ve.VALIDATED


def test_referans_hatasi_VERILMEZSE_eski_davranis_korunur():
    """Geriye dönük uyum: hata bilinmiyorsa uydurma kapı kurulmaz."""
    ve = _ve()
    assert ve.overall_class(ve.classify_fea()) == ve.VALIDATED
