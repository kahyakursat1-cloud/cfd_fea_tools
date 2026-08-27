"""İki-yönlü FSI1: yayımlanan DÖRT nicelik de %2,4 bandında üretildi.

    uy  0,8401 mm   yayimlanan 0,8209   %2,34
    ux  0,0230 mm   yayimlanan 0,0227   %1,32
    surukleme       14,2835 / 14,295    %-0,08
    tasima          0,7498  / 0,7638    %-1,83

Bu, deponun FSI tarafında tam bir kıyaslama vakasını uçtan uca ürettiği
ilk sonuçtur.

BU SONUCA İKİNCİ DENEMEDE ULAŞILDI VE BİRİNCİSİ SESSİZCE YANLIŞTI. İlk
koşu 7 turda ``sabit noktaya'' ulaşıp uy=1,4496 mm veriyordu, yani %77
sapma. Sebep döngünün kendisiydi: zaman dizinleri turlar arasında
birikiyordu ve OpenFOAM'ın `-latestTime`'ı sayıca en büyüğü seçtiği için
her tur 1. TURUN (rijit) alanını okuyordu. Yük sabit olduğu için ``sabit
nokta'' da oluşuyordu.

Yakalanması zordu çünkü İKİ KANAL AYRIŞMIŞTI ve ayrışma bir FİZİK BULGUSU
gibi okunabiliyordu: çözücünün forces.dat'ı aynı dosyaya eklendiği ve son
satırı okunduğu için TAZEYDİ. Taşıma her tur düşüyor, aktarılan bayrak
yükü sabit kalıyordu. Bunu ``taşıma silindir ile bayrak arasında yeniden
dağılıyor'' diye okudum ve üç eleme koşusu yazdım (ağ ailesi, CSM1,
dağılım ölçümü); üçü de doğru sonuç verdi, üçü de kusuru bulamadı ---
çünkü kusur onların hiçbirinde değildi.

ÜÇ KUSUR YOL BOYUNCA DÜŞTÜ:

  1. Ağ hareketi 3B en-yakın-komşu kullanıyordu; ön ve arka düzlemdeki
     nokta çiftleri farklı FEA düğümlerine düşüyor, aradaki kenar z
     ekseninden sapıyordu. `checkMesh` bunu yakaladı (2349 kenar). Diğer
     bütün kalite ölçütleri TEMİZDİ --- yani kusur kalite değil, 2B
     varsayımının kırılmasıydı. Sorgu (x,y)'ye indirildi ve yer değiştirme
     z sütunu boyunca ortalandı.
  2. Kapı FİRE VERİYORDU AMA DÖNGÜ OKUMUYORDU: `checkMesh_hata` ikinci
     turdan itibaren True idi ve döngü aldırmadan yedi tur koştu. Bu
     deponun en sık kusuru. Kapı artık döngüyü durduruyor.
  3. BAYAT VERİ: yukarıda anlatılan `-latestTime` kusuru. Artık her tur
     başında artıklar siliniyor, VTK seçimi SAYICA yapılıyor ve aday
     sayısı 1 değilse döngü duruyor.

Birinci ve ikinci kusur düzeltildiğinde sonuç 1,4498 -> 1,4496 mm oldu,
yani hizalama kusuru cevabı bozmuyordu; sonucu değiştiren üçüncüsüydü.
Bu da kayda geçer: fire veren bir kapının koruduğu niceliğin önemsiz
çıkması, kapıyı gereksiz YAPMAZ --- önemli olup olmadığı ancak ölçülerek
bilinir.
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
    # OLCUT DONUS BICIMINE DEGIL "DONGU DURUYOR MU"YA baglanir: ilk surum
    # `return _ozetle` ariyordu ve dongu kendi kayitlarini dondurmeye
    # cevrilince testin kendisi dustu --- kapi yerindeydi.
    for kapi in ('if cfd["checkMesh_hata"]:', 'if cfd["vtk_aday"] != 1:'):
        i = src.index(kapi)
        assert "return " in src[i:i + 500], f"{kapi} okunuyor ama dongu durmuyor"


def test_DIS_SINIRLAR_KIMILDAMIYOR(kanit):
    """Sönüm yarıçapının uzak sınırlara ulaşmadığı HESAPLANMIŞ bir
    iddiaydı (exp(-9)); burada ölçülür. Sınır kayarsa problem sessizce
    başka bir problem olur."""
    for t in kanit["turlar"]:
        assert t["dis_sinir_nokta"] > 0, "sınır noktası bulunamadı; kapı âtıl"
        assert t["dis_sinir_max_mm"] < 1e-6, (
            f"tur {t['tur']}: dış sınır {t['dis_sinir_max_mm']} mm kaydı")


def test_AG_HAREKETI_YAPIYI_ASMIYOR(kanit):
    """Ağ, yapının GÖRDÜĞÜ en büyük sehimden fazla hareket edemez ---
    aşıyorsa yayma ağırlığı 1'i geçiyordur.

    ÖLÇÜT BİR KEZ YANLIŞ KURULDU: ağ hareketini AYNI turun sehimiyle
    kıyaslıyordum. Oysa k. tur ağı, k-1. turun (gevşetilmiş) sehimiyle
    deforme edilir; 2. turda ağ 0,94 mm hareket ederken yapı 0,75 mm
    veriyordu ve test bunu ihlal sandı. Doğru üst sınır ÖNCEKİ turlardır.
    """
    for i, t in enumerate(kanit["turlar"][1:], start=1):
        tavan = max(abs(o["uy_mm"]) for o in kanit["turlar"][:i])
        assert t["max_yerdegistirme_mm"] <= tavan * 1.05 + 1e-9, (
            f"tur {t['tur']}: ağ {t['max_yerdegistirme_mm']} mm, önceki "
            f"turların tavanı {tavan} mm")


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


def test_AKTARILAN_YUK_de_DEGISIYOR(kanit):
    """BAYAT-VERİ KAPISI. İlk koşuyu geçersiz kılan kusurun imzası tam
    buydu: çözücünün taşıması düşüyor ama AKTARILAN yük sabit kalıyordu,
    çünkü her tur aynı (rijit) VTK okunuyordu. İki kanal birlikte
    hareket etmiyorsa yük bayattır."""
    ilk, son = kanit["turlar"][0], kanit["turlar"][-1]
    d_yuk = abs(100 * (son["aktarilan_Fy_N"] - ilk["aktarilan_Fy_N"])
                / ilk["aktarilan_Fy_N"])
    assert d_yuk > 5.0, (
        f"aktarılan yük yalnız %{d_yuk:.2f} değişti; çözücünün taşıması "
        "düşerken bu sabit kalıyorsa okunan VTK bayattır")


def test_HER_TURDA_TEK_VTK_ADAYI(kanit):
    """Temizlik çalışıyorsa tur başına tek aday olur. Birden çoksa
    `-latestTime` hangi turu seçtiği BİLİNMEZ."""
    kotu = [t["tur"] for t in kanit["turlar"] if t.get("vtk_aday") != 1]
    assert not kotu, f"birden çok VTK adayı olan turlar: {kotu}"


def test_YAYIMLANAN_DORT_NICELIK_de_URETILDI(kanit):
    """Asıl iddia. uy tek başına tutturulabilir (yanlış bir yükle yanlış
    bir yapıdan da çıkabilir); dördü birden tutturmak zordur."""
    s = kanit["sapma"]
    assert abs(s["uy_pct"]) < 5.0, f"uy %{s['uy_pct']}"
    assert abs(s["ux_pct"]) < 5.0, f"ux %{s['ux_pct']}"
    assert abs(kanit["surukleme_sapma_pct"]) < 2.0
    assert abs(kanit["tasima_sapma_pct"]) < 5.0


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


def test_HUKUM_BANDIN_GCI_OLMADIGINI_SOYLUYOR(kanit):
    """En tehlikeli okuma: 'dört nicelik de tuttu' = 'GCI bandı var'.
    Tek ağ, tek yapı ağı, lineer yapı, kinematik ağ hareketi."""
    v = kanit["verdikt"]
    if abs(kanit["sapma"]["uy_pct"]) < 10.0:
        assert "BANT BİR GCI DEĞİLDİR" in v
        assert "İKİNCİ denemede" in v, (
            "ilk koşunun sessizce yanlış olduğu hükümden düşerse ders "
            "kaybolur")


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


def test_SONUM_YARICAPI_SONUCU_TASIMIYOR(kanit):
    """Ağ hareketi bir Laplace çözümü değil, KİNEMATİK bir seçim --- ve
    kayıtta ``sonuç bundan ne kadar etkileniyor SINANMADI'' diye
    duruyordu. Yarıçap dört kat değiştirilerek ölçüldü.

    ÖLÇÜT REFERANS SAPMASIYLA KIYASLANIR, mutlak bir eşikle değil: seçimin
    yayılımı sapmadan küçükse sonucu taşımıyordur. Büyük olsaydı ``%2,3
    sapma'' bir fizik sonucu değil bir AYAR sonucu olurdu ve öyle
    raporlanması gerekirdi."""
    d = kanit.get("sonum_duyarliligi")
    if not d:
        pytest.skip("süpürme koşulmamış")
    kosan = [k for k in d["kosular"] if k["uy_mm"] is not None]
    assert len(kosan) >= 3, f"süpürme eksik: {d['kosular']}"
    r = [k["sonum_r_m"] for k in kosan]
    assert max(r) / min(r) >= 4.0, (
        f"yarıçap yalnız {max(r) / min(r):.1f} kat tarandı --- duyarsızlık "
        "iddiası bu kadar dar bir bantla kurulamaz")
    assert d["uy_yayilim_pct"] < abs(kanit["sapma"]["uy_pct"]), (
        f"ağ-hareketi yayılımı %{d['uy_yayilim_pct']}, referans sapması "
        f"%{kanit['sapma']['uy_pct']} --- seçim sonucu taşıyor demektir")


def test_URETIM_YARICAPI_SUPURMENIN_ICINDE(kanit):
    """Süpürme üretim değerini içermezse, yayımlanan sayının bandın
    neresinde durduğu bilinmez."""
    from turek_hron_fsi1_iki_yonlu import SONUM_R
    d = kanit.get("sonum_duyarliligi")
    if not d:
        pytest.skip("süpürme koşulmamış")
    assert SONUM_R in [k["sonum_r_m"] for k in d["kosular"]]
    uretim = next(k for k in d["kosular"] if k["sonum_r_m"] == SONUM_R)
    assert uretim["uy_mm"] == pytest.approx(
        kanit["turlar"][-1]["uy_mm"], rel=1e-9), (
        "süpürmedeki üretim koşusu ana kayıtla ayrışıyor")
