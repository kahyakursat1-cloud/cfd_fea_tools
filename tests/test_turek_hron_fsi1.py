"""FSI1: zincir bir DIŞ referansa karşı koştu ve iki KAPSAM boşluğu ölçüldü.

BU ÖLÇÜM BİR HATAYI DA KAYDA GEÇİRİR. İlk sürüm ham %85'lik düşey sapmayı
gördü ve REFERANSI suçlayan bir kapı yazdı: ``uy=0,8209 mm bir konsolda
0,0022 mm kısalma üretir, verilen ux 10 kat büyük, bu çift tutarsız''.
Kapının eksenel terimi BİZİM taşıdığımız kuvvetten kuruluyordu ve bu modül
yalnız BASINÇ taşır. Çözücünün kendi yüzey integrali alındığında bayraktaki
viskoz eksenel kuvvet basıncınkinin 9,6 katı çıktı --- referans tutarlıydı,
eksik olan bizim yükümüzdü. Kusurun yönü kritikti: dışarıya atılmıştı.

TESTLER SONUCU DEĞİL KURALI BAĞLAR. Ağ değişirse ya da akış yeniden
çözülürse düşmezler; düşmeleri için ya bir çapa kalkmalı ya kayıt kendi
içinde çelişmeli.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_fsi1.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_fsi1.json yok "
                    "(python experiments/turek_hron_fsi1.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_E_MALZEMEDEN_TURETILDI_yazilmadi(kanit):
    """E doğrudan yazılsaydı kaynağın verdiği büyüklüğün mu_s mu E mi
    olduğu kaydolmazdı."""
    k = kanit["kati"]
    assert k["E_Pa"] == pytest.approx(2 * k["mu_s_Pa"] * (1 + k["nu_s"]))
    assert "2 mu" in k["_E_turetildi"]


def test_YAPI_KIRIS_TEORISIYLE_BAGIMSIZ_DOGRULANDI(kanit):
    """``Yük mü yapı mı'' sorusu FEA çıktısına bakarak ayrılamaz. Aynı
    yükün kapalı-form konsol çözümü bu ayrımı yapar."""
    fea, kiris = kanit["fea"], kanit["kiris_capasi"]
    if not fea.get("kosdu"):
        pytest.skip("FEA koşmadı")
    fark = abs(100 * (fea["uy_mm"] - kiris["uy_mm"]) / kiris["uy_mm"])
    assert fark < 3.0, (
        f"FEA {fea['uy_mm']} mm, kiriş {kiris['uy_mm']} mm --- %{fark:.2f}. "
        "Bu bant kayma deformasyonu ve kök esnekliği içindir; aşılıyorsa "
        "yapısal model artık bağımsız çapalı DEĞİLDİR.")
    assert kiris["narinlik_L_h"] > 10, "kiriş teorisi narin olmayan kesitte geçerli değil"


def test_A_NOKTASI_gercekten_UC_ORTASI(kanit):
    """Yanlış düğüm okunursa sapma fizik sanılır."""
    fea = kanit["fea"]
    if not fea.get("kosdu"):
        pytest.skip("FEA koşmadı")
    assert fea["A_uzaklik_m"] < 1e-9, f"A düğümü {fea['A_uzaklik_m']} m uzakta"


def test_AKTARIM_COZUNURLUGU_YAKINSADI_ve_SONUCU_DEGISTIRMIYOR(kanit):
    """Sapmanın ilk şüphelisi aktarım çözünürlüğüydü ve ÖLÇÜLDÜ: 10 kat
    inceltmede sehim %1 içinde sabit. Bu test o elemeyi kilitler."""
    m = kanit.get("cozunurluk_merdiveni")
    if not m or len(m) < 3:
        pytest.skip("merdiven yok")
    uy = [r["uy_mm"] for r in m if r["uy_mm"] is not None]
    assert len(uy) >= 3
    yayilim = 100 * (max(uy) - min(uy)) / abs(uy[-1])
    assert yayilim < 2.0, f"merdiven yayılımı %{yayilim:.2f} --- artık yakınsak değil"
    kaba, ince = m[0]["x_adimi_m"], m[-1]["x_adimi_m"]
    assert kaba / ince >= 8, "merdiven yeterince geniş değil; eleme zayıflar"
    # Kuvvet cozunurlukten BAGIMSIZ olmali: sema korunumlu.
    Fy = {round(r["Fy_N"], 8) for r in m}
    assert len(Fy) == 1, f"korunumlu şemada Fy çözünürlükle değişemez: {Fy}"


def test_VISKOZ_BILESENIN_BASKIN_OLDUGU_hala_dogru(kanit):
    """Bu vakanın öğrettiği ders viskoz eksenel kuvvetin baskınlığıdır.
    Baskın değilse vaka artık bu dersi taşımıyordur ve kayıt yeniden
    yazılmalıdır --- sessizce geçerli sayılmamalı."""
    k = kanit.get("kayma_bedeli")
    if not k:
        pytest.skip("kayma_bedeli yok")
    assert k["viskoz_basinc_orani_x"] > 1.0


def test_KAYMA_KANALI_ACIK_ve_EKSENELI_KAPATTI(kanit):
    """Boşluk ölçüldükten sonra KAPATILDI. Bu test kapanmanın HESAPLA
    değil ÖLÇÜMLE olduğunu bağlar: kanal açık olmalı ve koşulan FEA'nın
    kendi ux'i referansa oturmalı."""
    k, fea, sapma = (kanit.get("kayma_bedeli"), kanit["fea"],
                     kanit.get("sapma"))
    if not k or not fea.get("kosdu"):
        pytest.skip("ölçüm yok")
    assert k["kayma_kanali_acik"] is True, (
        "kanal kapandıysa ux sapması geri gelir; kayıt bunu söylemeli")
    assert abs(sapma["ux_pct"]) < 10.0, (
        f"eksenel kanal açıkken ux sapması %{sapma['ux_pct']} --- "
        "kapanma iddiası bu veriyle desteklenmiyor")
    # Basinc-yalniz TAHMINI hala kayitta ve GERCEKTEN kotu olmali;
    # yoksa "kanal fark yaratti" iddiasi bos kalir.
    yalniz = abs(k["ux_referans_mm"] - k["ux_basinc_yalniz_mm"])
    olculen = abs(k["ux_referans_mm"] - fea["ux_mm"])
    assert olculen < yalniz / 3, (
        f"kanal açıldıktan sonraki hata ({olculen:.4f}) basınç-yalnız "
        f"hatadan ({yalniz:.4f}) belirgin küçük değil")


def test_AKTARIM_COZUCUNUN_KENDI_INTEGRALIYLE_CAPALI(kanit):
    """İç korunum metrikleri yapı gereği kesindir ve hiçbir şey söylemez.
    Bağımsız çapa çözücünün kendi yüzey integralidir."""
    k = kanit.get("kayma_bedeli")
    if not k:
        pytest.skip("kayma_bedeli yok")
    assert abs(k["aktarim_capasi_Fy_pct"]) < 1.0, (
        f"düşey aktarım çözücüden %{k['aktarim_capasi_Fy_pct']} sapıyor")
    # DOGRU PAYDA KANALA BAGLIDIR ve bu ayrim kayitta ACIK olmali:
    # kanal acikken basinc-yalniz yuzde yuzlerce cikar ve bir kusur DEGIL,
    # yanlis paydadir. Testin kendisi de dogru paydayi secmeli.
    if k["kayma_kanali_acik"]:
        assert abs(k["aktarim_capasi_TOPLAM_pct"]) < 5.0, (
            f"eksenel aktarım çözücünün basınç+viskoz toplamından "
            f"%{k['aktarim_capasi_TOPLAM_pct']} sapıyor")
    else:
        assert abs(k["aktarim_capasi_pct"]) < 10.0
    assert "payda" in k["_capa_notu"]


def test_TEK_YON_BEDELI_KAYNAKTAN_KURULDU_tahminden_degil(kanit):
    """Ölçek uydurulsaydı sapmayı istediğimiz yere getirebilirdik."""
    t = kanit.get("tek_yon_bedeli")
    if not t:
        pytest.skip("tek_yon_bedeli yok")
    assert t["olcek"] == pytest.approx(t["tasima_fsi1_Nm"] / t["tasima_cfd1_Nm"],
                                       rel=1e-3)
    assert 0.0 < t["olcek"] < 1.0, "geri besleme yükü artırıyorsa gerekçe değişir"
    assert abs(t["kalan_sapma_pct"]) < abs(kanit["sapma"]["uy_pct"]), (
        "ölçekleme sapmayı azaltmıyorsa tek-yönlülük açıklaması bu veriyle "
        "desteklenmiyor")


def test_HUKUM_IKI_KANALI_AYIRIYOR_hepsini_gecmis_saymiyor(kanit):
    """En tehlikeli okuma: bir kanal kapandı = doğrulandı. Düşey kanalın
    düzeltmesi HESAPLANDI, ölçülmedi ve hüküm bunu ayrı söylemeli."""
    v = kanit["verdikt"]
    acik = (kanit.get("kayma_bedeli") or {}).get("kayma_kanali_acik")
    if acik:
        assert "ux bir GEÇMEDİR, uy DEĞİLDİR" in v
        assert "HESAPLANMIŞTIR, ölçülmemiştir" in v
    else:
        assert "GEÇME DEĞİLDİR" in v


def test_KISIT_tek_yonlu_oldugunu_SOYLUYOR(kanit):
    k = kanit["_kisit"]
    assert "TEK YONLU" in k
    assert "LINEER" in k


def test_REFERANS_KAYNAGI_KAYITTA(kanit):
    """Referans daha önce HATIRLANMIŞTI ve o hal yanlış bir kapıya yol
    açtı. Kaynağın kayıtta olması o dersin taşıyıcısıdır."""
    r = kanit["referans"]
    assert r["_dogrulandi"] is True
    assert r.get("_kaynak"), "doğrulandı denip kaynak yazılmaması geriye adımdır"


def test_RAPOR_kanittan_sapmiyor(kanit):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "FSI1" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    k, fea = kanit["kayma_bedeli"], kanit["fea"]
    for deger in (round(fea["uy_mm"], 4), k["viskoz_basinc_orani_x"]):
        s = f"{deger}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"
    assert "viskoz" in t.lower()
