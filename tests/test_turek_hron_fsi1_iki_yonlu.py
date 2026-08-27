"""İki-yönlü FSI1: geri besleme KOŞULDU ve referansı ÜRETMEDİ.

Bu ölçümün değeri olumlu bir sonuç değil, bir ELEMEDİR. Tek-yönlü koşu
düşey sehimi %90 fazla vermişti ve gerekçe ``akış rijit bayrakla
çözülüyor'' diye HESAPLANMIŞTI. Koşulunca geri beslemenin gerçekten
çalıştığı görüldü --- ama fazla çalıştı: taşıma %56 düştü, kaynağın kendi
rijit/deforme çifti %32 diyor. Sapma %90'dan %77'ye indi, kapanmadı.

İKİ KUSUR YOL BOYUNCA DÜŞTÜ:

  1. Ağ hareketi 3B en-yakın-komşu kullanıyordu; ön ve arka düzlemdeki
     nokta çiftleri farklı FEA düğümlerine düşüyor, aradaki kenar z
     ekseninden sapıyordu. `checkMesh` bunu yakaladı (2349 kenar). Diğer
     bütün kalite ölçütleri TEMİZDİ --- yani kusur kalite değil, 2B
     varsayımının kırılmasıydı. Sorgu (x,y)'ye indirildi ve yer değiştirme
     z sütunu boyunca ortalandı.
  2. Kapı FİRE VERİYORDU AMA DÖNGÜ OKUMUYORDU: `checkMesh_hata` ikinci
     turdan itibaren True idi ve döngü aldırmadan yedi tur koştu. Bu
     deponun en sık kusuru. Kapı artık döngüyü durduruyor.

Düzeltmeden sonra sonuç 1,4498 -> 1,4496 mm oldu, yani hizalama kusuru
sonucu bozmuyordu. Bu da kayda geçer: fire veren bir kapının koruduğu
niceliğin önemsiz çıkması, kapıyı gereksiz YAPMAZ --- önemli olup
olmadığı ancak ölçülerek bilinir.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_fsi1_iki_yonlu.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_fsi1_iki_yonlu.json yok "
                    "(python experiments/turek_hron_fsi1_iki_yonlu.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_AG_KAPISI_HER_TURDA_TEMIZ(kanit):
    """En sert test bu: sonuç, kendi kapısını geçmiş bir ağdan gelmeli.
    İlk koşuda geçmiyordu ve döngü aldırmıyordu."""
    kotu = [t["tur"] for t in kanit["turlar"] if t["checkMesh_hata"]]
    assert not kotu, f"checkMesh şu turlarda hata bildirdi: {kotu}"


def test_KAPI_DONGUYU_GERCEKTEN_DURDURUYOR():
    """Kaydın temiz olması, kapının BAĞLI olduğunu göstermez --- hiç
    tetiklenmemiş de olabilir. Kod yolunu ayrıca denetle."""
    src = (KOK / "experiments" / "turek_hron_fsi1_iki_yonlu.py").read_text(
        encoding="utf-8")
    i = src.index('if cfd["checkMesh_hata"]:')
    assert "return _ozetle" in src[i:i + 400], (
        "checkMesh hatası okunuyor ama döngü durmuyor")


def test_DIS_SINIRLAR_KIMILDAMIYOR(kanit):
    """Sönüm yarıçapının uzak sınırlara ulaşmadığı HESAPLANMIŞ bir
    iddiaydı (exp(-9)); burada ölçülür. Sınır kayarsa problem sessizce
    başka bir problem olur."""
    for t in kanit["turlar"]:
        assert t["dis_sinir_nokta"] > 0, "sınır noktası bulunamadı; kapı âtıl"
        assert t["dis_sinir_max_mm"] < 1e-6, (
            f"tur {t['tur']}: dış sınır {t['dis_sinir_max_mm']} mm kaydı")


def test_AG_HAREKETI_UC_SEHIMIYLE_TUTARLI(kanit):
    """Ağdaki en büyük yer değiştirme, yapının uç sehimini AŞAMAZ ---
    aşıyorsa yayma ağırlığı 1'i geçiyordur ve ağ yapıyı takip etmiyordur."""
    for t in kanit["turlar"][1:]:
        assert t["max_yerdegistirme_mm"] <= abs(t["uy_mm"]) * 1.05 + 1e-9, (
            f"tur {t['tur']}: ağ {t['max_yerdegistirme_mm']} mm, yapı "
            f"{t['uy_mm']} mm")


def test_SABIT_NOKTAYA_ULASILDI(kanit):
    """Yakınsamamış bir turdan referans karşılaştırması yapılamaz."""
    from turek_hron_fsi1_iki_yonlu import MAX_TUR, TOL_MM
    son = kanit["turlar"][-1]
    assert len(kanit["turlar"]) < MAX_TUR, "tur tavanına dayanıldı"
    assert son["degisim_mm"] is not None and son["degisim_mm"] < TOL_MM


def test_GERI_BESLEME_GERCEKTEN_CALISTI(kanit):
    """Turların anlamı taşımanın DEĞİŞMESİDİR. Değişmiyorsa ağ hareketi
    akışa ulaşmıyordur ve 'iki-yönlü' adı boştur."""
    ilk, son = kanit["turlar"][0], kanit["turlar"][-1]
    assert ilk["tasima_N_m"] and son["tasima_N_m"]
    dusus = 100 * (son["tasima_N_m"] - ilk["tasima_N_m"]) / ilk["tasima_N_m"]
    assert dusus < -5.0, f"taşıma yalnız %{dusus:.1f} değişti; kuplaj âtıl"


def test_ILK_TUR_TEK_YONLU_KOSUYLA_AYNI(kanit):
    """İlk tur deforme edilmemiş ağda koşar, yani tek-yönlü sonucu
    yeniden üretmelidir. Üretmiyorsa iki betik ayrışmıştır."""
    tek = KOK / "turek_hron_fsi1.json"
    if not tek.exists():
        pytest.skip("tek-yönlü kanıt yok")
    t = json.loads(tek.read_text(encoding="utf-8"))
    if not t["fea"].get("kosdu"):
        pytest.skip("tek-yönlü FEA koşmadı")
    assert kanit["turlar"][0]["max_yerdegistirme_mm"] == 0.0
    assert kanit["turlar"][0]["uy_mm"] == pytest.approx(
        t["fea"]["uy_mm"], rel=1e-3), (
        "ilk tur tek-yönlü sonuçtan sapıyor --- iki betik aynı yükü "
        "taşımıyor demektir")


def test_HUKUM_YAPISAL_MODELI_GEREKCEYLE_ELIYOR(kanit):
    """Eleme yapılmasaydı 'kalan fark bilinmiyor' derdik. ux kanalı EA'ya
    bağlı olduğu için yapısal modeli eleyebiliyor ve hüküm bunu söylemeli."""
    v = kanit["verdikt"]
    if abs(kanit["sapma"]["uy_pct"]) < 10.0:
        pytest.skip("sapma kapanmış; eleme cümlesi gerekmiyor")
    assert "YAPISAL MODEL ELENİR" in v
    assert "ux" in v and "EA" in v


def test_HUKUM_KAPANDI_DEMIYOR(kanit):
    """En tehlikeli okuma: 'iki-yönlü koştu' = 'doğrulandı'."""
    v = kanit["verdikt"]
    if abs(kanit["sapma"]["uy_pct"]) >= 10.0:
        assert "AŞIRI" in v or "kapanmadı" in v or "sapma sürüyor" in v
        assert "bu betiğin cevabı DEĞİLDİR" in v


def test_KISIT_ag_bagimsizligi_ve_LINEER_yapiyi_soyluyor(kanit):
    k = kanit["_kisit"]
    assert "AG-BAGIMSIZLIGI SINANMADI" in k
    assert "LINEER" in k
    assert "KINEMATIK secimdir" in k


def test_RAPOR_kanittan_sapmiyor(kanit):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "iki-yönlü" not in t and "İKİ YÖNLÜ" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    son = kanit["turlar"][-1]
    for deger in (round(son["uy_mm"], 4), son["tasima_N_m"]):
        s = f"{deger}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"
    assert str(len(kanit["turlar"])) in t
