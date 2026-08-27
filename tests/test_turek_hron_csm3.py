"""CSM3: zaman-çözünür yapısal yol yayımlanmış bir değere karşı doğrulandı.

    uy  -64,0089 +/- 65,5361 mm  [1,0932 Hz]
    yay -63,607  +/- 65,160      [1,0995]      -> %-0,63 / %0,58 / %-0,57
    ux  -14,5714 +/- 14,5717 mm                -> %-1,86 / %1,86

Depo `*DYNAMIC` yeteneğini kazanmıştı ama yayımlanmış bir değere karşı hiç
koşmamıştı; doğrulaması iç tutarlılıktı. Bu, FSI2/FSI3'ün yapısal ÖN
KOŞULUDUR --- o vakalar kendini uyaran bir salınımdır ve yapısal taraf
zamanda yanlışsa kuplaj turu da yanlış olur.

ÜÇ KANAL AYRI SINANIR ve bu kasıtlıdır: ortalama ve genlik rijitlik/yük
tarafını, frekans kütle/entegratör tarafını gösterir. Üçü birden tutmak,
birini tutturmaktan çok daha zordur --- yanlış bir kütleyle doğru bir
genlik elde edilebilir ama frekans kayar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_csm3.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_csm3.json yok "
                    "(python experiments/turek_hron_csm3.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_UC_KANAL_da_BANDINDA(kanit):
    """Asıl iddia. Genlik tek başına tutturulabilir; üçü birden zordur."""
    s = kanit["sapma_uy"]
    assert abs(s["ortalama_pct"]) < 5.0, f"ortalama %{s['ortalama_pct']}"
    assert abs(s["genlik_pct"]) < 5.0, f"genlik %{s['genlik_pct']}"
    assert s.get("frekans_pct") is not None, "frekans ölçülemedi"
    assert abs(s["frekans_pct"]) < 3.0, f"frekans %{s['frekans_pct']}"


def test_UX_KANALI_da_BANDINDA(kanit):
    sx = kanit["sapma_ux"]
    assert abs(sx["ortalama_pct"]) < 10.0
    assert abs(sx["genlik_pct"]) < 10.0


def test_SALINIM_GERCEKTEN_OLCULDU(kanit):
    """Frekans iki geçişten de hesaplanabilir ve o hâlde tek periyottan
    okunmuş olur. Kuyrukta birkaç tam salınım İSTENİR."""
    assert kanit["uy"]["gecis_sayisi"] >= 4, (
        f"kuyrukta yalnız {kanit['uy']['gecis_sayisi']} geçiş var --- "
        "frekans tek periyottan okunuyor")
    k = kanit["kosu"]
    assert k["adim"] >= 500, f"yalnız {k['adim']} adım"


def test_ZAMAN_ADIMI_PERIYODU_COZUYOR(kanit):
    """dt periyodun yanında büyükse frekans ölçümü adım-çözünürlüğünden
    sınırlanır ve 'tutturdu' demek anlamsızlaşır."""
    periyot = 1.0 / kanit["referans"]["frekans_hz"]
    adim_basina = periyot / kanit["kosu"]["dt_s"]
    assert adim_basina > 50, (
        f"periyot başına yalnız {adim_basina:.0f} adım")


def test_SAYISAL_SONUMUN_BEDELI_OLCULDU(kanit):
    """Bu vakada FİZİKSEL sönüm YOK. HHT alfa sıfırdan farklı seçildi ve
    genliği zamanla söndürür; bedel ölçülmezse 'genlik tuttu' iddiası
    hangi ana ait olduğu belirsiz bir sayıdır."""
    s = kanit["uy"]["genlik_sonumu_pct"]
    assert s is not None, "sönüm ölçüsü yok"
    assert abs(s) < 5.0, (
        f"genlik ilk yarıdan son yarıya %{s} değişti --- sayısal sönüm "
        "sonucu taşıyor demektir")


def test_CSM1_CAPRAZI_TUTUYOR(kanit):
    """İki AYRI koşu birbirini denetler: sönümsüz serbest salınım statik
    dengenin iki katına gider. Tutmuyorsa ikisinden biri başka bir yapı
    çözüyordur."""
    c = kanit["csm1_caprazi"]
    assert c is not None
    assert 0.90 < c["oran"] < 1.02, (
        f"salınım ucu {c['csm3_uc_mm']} mm, statiğin iki katı "
        f"{c['iki_kat_mm']} mm --- oran {c['oran']}")


def test_REFERANS_CIFTI_SIFIRDAN_BASLAMAYI_SOYLUYOR(kanit):
    """Yayımlanan çiftte ortalama ~= genlik olması, hareketin sıfırdan
    başladığının imzasıdır. Bu tutmuyorsa referansı yanlış okumuşuzdur ve
    kıyaslama başka bir kuruluma aittir."""
    r = kanit["referans"]
    oran = r["uy_genlik_mm"] / abs(r["uy_ort_mm"])
    assert 0.9 < oran < 1.15, f"genlik/ortalama = {oran:.3f}"


def test_NLGEOM_ve_DYNAMIC_BIRLIKTE(kanit):
    """Vakanın değeri ikisinin BİRLİKTE koşmasıdır; biri düşerse bu
    ölçüm FSI2/FSI3 için ön koşul olmaktan çıkar."""
    src = (KOK / "experiments" / "turek_hron_csm3.py").read_text(
        encoding="utf-8")
    assert 'analysis_type="DYNAMIC"' in src
    assert "nlgeom=True" in src
    assert kanit["kosu"]["alpha"] is not None


def test_KISIT_dt_AGI_ve_ALFAYI_dogru_konumluyor(kanit):
    k = kanit["_kisit"]
    assert "IKI SEVIYEDE" in k, "zaman adımı iki seviyede koşuldu; kısıt bunu söylemeli"
    assert "GCI DEGIL" in k, "iki seviye bir GCI değildir ve kısıt bunu ayırmalı"
    assert "TEK AG" in k
    assert "KIYASLANMADI" in k


def test_ZAMAN_ADIMI_SONUCU_TASIMIYOR(kanit):
    """`_kisit` bir turdur ``adım-bağımsızlığı SINANMADI'' diyordu. Yarım
    adımla ikinci koşu onu ölçüme çevirir.

    ÖLÇÜT REFERANS SAPMASIYLA KIYASLANIR: iki adım arasındaki fark
    sapmadan küçükse zaman adımı sonucu taşımıyordur."""
    d = kanit.get("dt_duyarliligi")
    if not d:
        pytest.skip("dt süpürmesi koşulmamış")
    assert d.get("kosdu"), f"ince adım koşusu düştü: {d.get('neden')}"
    assert d["dt_ince_s"] < d["dt_kaba_s"]
    sapma = abs(kanit["sapma_uy"]["genlik_pct"])
    assert abs(d["genlik_fark_pct"]) < max(sapma, 1.0), (
        f"genlik dt ile %{d['genlik_fark_pct']} değişiyor, referans "
        f"sapması %{sapma} --- zaman adımı sonucu taşıyor demektir")
    if d.get("frekans_fark_pct") is not None:
        assert abs(d["frekans_fark_pct"]) < 2.0


def test_HUKUM_KUPLAJIN_YAZILMADIGINI_soyluyor(kanit):
    """En tehlikeli okuma: 'CSM3 tuttu' = 'FSI2/FSI3 hazır'."""
    v = kanit["verdikt"]
    if abs(kanit["sapma_uy"]["genlik_pct"]) < 10.0:
        assert "kuplaj hâlâ" in v or "kuplaj hala" in v
        assert "bant bir GCI değil" in v


def test_RAPOR_kanittan_sapmiyor(kanit):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "CSM3" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    for deger in (kanit["uy"]["ortalama_mm"], kanit["uy"]["genlik_mm"],
                  kanit["uy"]["frekans_hz"]):
        s = f"{abs(deger)}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"


def test_RAPOR_dt_BULGUSUNU_da_TASIYOR(kanit):
    """Zaman adımı genliği referans sapmasıyla aynı mertebede oynatıyor.
    Bu, bandın GENİŞLİĞİNE dair bir beyandır ve prozadan düşerse okur
    genliği olduğundan keskin okur."""
    tex = KOK / "docs" / "teknik_rapor.tex"
    d = kanit.get("dt_duyarliligi")
    if not tex.exists() or not d or not d.get("kosdu"):
        pytest.skip("rapor ya da dt ölçümü yok")
    t = tex.read_text(encoding="utf-8")
    if "CSM3" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    for deger in (abs(d["genlik_fark_pct"]), abs(d["frekans_fark_pct"])):
        s = f"{deger}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"
