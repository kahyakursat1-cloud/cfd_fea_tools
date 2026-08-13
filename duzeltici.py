"""Düzeltici katman — guard bir kusur bulunca kurulumu onarıp analizi tamamlar.

TASARIM KURALI (ihlal edilirse bu katman zararlıdır):
    Düzeltici bir SONUCU asla değiştirmez. Yalnız KURULUMU değiştirip yeniden
    koşar. Sayı her zaman çözücüden gelir; düzeltici yalnız çözücüye doğru
    soruyu sordurur. Bir düzeltmenin çıktıyı referansa yaklaştırmak için değeri
    oynadığı an, araç kendi tespit ettiği "sessiz hata"yı imal etmeye başlar:
    sayı doğru görünür, altındaki fizik yanlış kalır, ve guard artık onu
    yakalayamaz çünkü referansla uyuşur.

KÜTÜĞÜN KAYNAĞI: 2026-08-13'te elle yürütülen ölçümler. Her düzeltme gerçek bir
koşuda tetiklendi ve sonucu ölçüldü — hiçbiri varsayım değil.

BEŞ DÜZELTMENİN İKİSİ SONUCU DÜZELTMEDİ ve bu tasarımı belirledi. Silindir
DES'inde duvar işlemi gerçekten bozuktu (y⁺ 0,009), düzeltildi (y⁺ 0,78), sonuç
%1'den az değişti. NACA0012 α=8°'de aynısı oldu (y⁺ 357 → 2,5, hata %18,2 →
%16,6). Yani KUSURU GİDERMEK NEDENİ BULMAK DEĞİLDİR. Düzeltici bunu bilmek
zorundadır: uyguladığı düzeltmenin işe yarayıp yaramadığını ÖLÇER ve
yaramadıysa söyler, gizlemez.

YAN ETKİ ALANI da ölçümden doğdu: `kOmegaSST → kOmegaSSTLM` geçişi tek bir
değişiklik değildi — model adı + iki taşıma alanı (gammaInt, ReThetat) + iki
diverjans şeması + iki lineer çözücü, ve ayrıca Tu seçimini geçersiz kılıyor.
Yalnız model adını çeviren bir düzeltici çalışan kurulumu bozar.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Sınıf adları validity_envelope ile AYNI olmalı; iki yerde ayrı tutmak ayrışma demek.
VALIDATED = "VALIDATED"
TREND = "TREND"
OUT = "OUT_OF_ENVELOPE"

MAKS_DENEME = 4          # sonsuz döngü koruması
IYILESME_ESIGI = 0.10    # bağıl hatada en az %10 iyileşme "işe yaradı" sayılır


@dataclass(frozen=True)
class Duzeltme:
    """Bir tespit-düzeltme kuralı.

    tetikleyici : kanıt sözlüğü → bu kusur var mı?
    uygula      : kanıt → kurulum değişiklikleri (dict). SONUCA DOKUNMAZ.
    on_kosul    : düzeltmenin geçerli olması için gereken şart (insan okur)
    yan_etki    : bu düzeltmenin GEÇERSİZ KILDIĞI başka ayarlar
    kaynak      : hangi ölçüm bu kuralı doğurdu
    """

    ad: str
    tetikleyici: Callable[[dict], bool]
    uygula: Callable[[dict], dict]
    aciklama: str
    on_kosul: str
    yan_etki: str
    kaynak: str


# ── Tetikleyiciler ────────────────────────────────────────────────────────────
def _yplus_uyumsuz(k: dict) -> bool:
    """Duvar işlemi ile ölçülen y⁺ birbirini tutmuyor."""
    yp = (k.get("olculen") or {}).get("yplus") or {}
    islem = (k.get("kurulum") or {}).get("duvar_islemi") or ""
    ort = yp.get("ort")
    if ort is None or not islem:
        return False
    dusuk_re = "LowRe" in islem or "Spalding" in islem
    return (ort < 30.0) if not dusuk_re else (ort > 5.0)


def _sayisal_patlama(k: dict) -> bool:
    return bool((k.get("olculen") or {}).get("sigFpe")) or \
        "sigFpe" in str((k.get("olculen") or {}).get("hata") or "")


def _asimptotik_degil(k: dict) -> bool:
    p = (k.get("olculen") or {}).get("gozlenen_mertebe")
    return p is not None and not (0.5 <= p <= 3.0)


def _fiziksel_olmayan(k: dict) -> bool:
    """Iraksama sonuç sanılmış: katsayı fiziksel sınırın dışında."""
    o = k.get("olculen") or {}
    cl, cd = o.get("Cl"), o.get("Cd")
    return (cl is not None and abs(cl) > 3.0) or (cd is not None and cd < 0)


# ── Düzeltmeler ───────────────────────────────────────────────────────────────
KUTUK: list[Duzeltme] = [
    Duzeltme(
        ad="duvar_islemini_aga_uydur",
        tetikleyici=_yplus_uyumsuz,
        uygula=lambda k: {"nut_wall": "nutLowReWallFunction",
                          "k_wall": "kLowReWallFunction",
                          "_hedef_yplus": (0.0, 5.0)},
        aciklama="Duvar fonksiyonu, geçerli y⁺ bandı dışında bir ağda kullanılıyor; "
                 "düşük-Re duvar işlemine geçilir.",
        on_kosul="Ağ ilk hücresi y⁺≲5 verecek kadar ince OLMALI; değilse önce "
                 "duvar-normal gradasyon artırılır.",
        yan_etki="Ağ gradasyonunu geçersiz kılar (ilk hücre yüksekliği yeniden "
                 "seçilmeli) ve başlangıç alanı düz akışsa kararsızlık doğurabilir.",
        kaynak="Silindir DES y⁺=0,009 · NACA0012 α=8° y⁺=16–357 (2026-08-13)"),
    Duzeltme(
        ad="rampali_baslangic",
        tetikleyici=_sayisal_patlama,
        uygula=lambda k: {"_baslangic": "mapFields", "force_gentle": True,
                          "_kaynak_cozum": (k.get("kurulum") or {}).get("kaba_cozum")},
        aciklama="Çözüm sigFpe ile patlıyor; kaba (yakınsamış) bir çözümden "
                 "mapFields ile fizikselleştirilmiş başlangıç alanı kurulur.",
        on_kosul="Aynı geometride yakınsamış bir kaba çözüm BULUNMALI.",
        yan_etki="Yok — sınır koşulları hedeften gelir, taşınan yalnız iç alandır.",
        kaynak="NACA0012 α=8° duvar-çözümlü: 27/6000 → 6000/6000 (2026-08-13)"),
    Duzeltme(
        ad="referans_ag_ailesine_gec",
        tetikleyici=_asimptotik_degil,
        uygula=lambda k: {"_ag_ailesi": "referans", "_neden": "gozlenen_mertebe"},
        aciklama="Gözlenen mertebe asimptotik aralıkta değil; kendi ağ ailesi "
                 "yerine referans ağ ailesine geçilir.",
        on_kosul="Vaka için yayımlanmış bir referans ağ ailesi VAR OLMALI "
                 "(ör. NASA TMR). Yoksa düzeltme uygulanamaz.",
        yan_etki="Ağ ailesi değişince topoloji, alan boyu ve iz çözünürlüğü "
                 "birlikte değişir; farkın tek bir nedene atfedilmesi ARTIK GEÇERSİZ.",
        kaynak="Airfoil O-grid p≈0,2 → TMR ağları, GCI %1,71"),
    Duzeltme(
        ad="fiziksel_olmayani_reddet",
        tetikleyici=_fiziksel_olmayan,
        uygula=lambda k: {"_kosu_durumu": "BASARISIZ",
                          "_neden": "fiziksel olarak imkânsız katsayı"},
        aciklama="Katsayı fiziksel sınırın dışında (|Cl|>3 ya da Cd<0): koşu "
                 "ıraksamış ama sonuç diye kaydedilmiş. Başarısız işaretlenir.",
        on_kosul="Yok — sınır veri kümesinden değil fizikten gelir.",
        yan_etki="Yok; yalnız koşu durumu değişir, hiçbir ayar değişmez.",
        kaynak="Korpus a8_mid: Cl=4769, Cd=293 'başarılı' kaydedilmişti"),
]


@dataclass
class Mudahale:
    """Tek bir düzeltme girişiminin denetlenebilir kaydı."""

    duzeltme: str
    tetikleyen: str
    degisiklik: dict
    onceki_hata_pct: float | None = None
    sonraki_hata_pct: float | None = None
    ise_yaradi: bool | None = None
    yan_etki: str = ""

    def ozet(self) -> str:
        if self.ise_yaradi is None:
            return f"{self.duzeltme}: uygulandı, etkisi ölçülemedi"
        yon = "İŞE YARADI" if self.ise_yaradi else "ETKİSİZ"
        return (f"{self.duzeltme}: {yon} "
                f"(%{self.onceki_hata_pct:.1f} → %{self.sonraki_hata_pct:.1f})")


@dataclass
class DuzelticiSonuc:
    sinif: str
    mudahaleler: list[Mudahale] = field(default_factory=list)
    kalan_aday: str | None = None
    verdikt: str = ""

    @property
    def etkisiz_sayisi(self) -> int:
        return sum(1 for m in self.mudahaleler if m.ise_yaradi is False)


def uygulanabilir(kanit: dict) -> list[Duzeltme]:
    """Bu kanıtta tetiklenen düzeltmeler — sıra kütükteki sırayla."""
    return [d for d in KUTUK if d.tetikleyici(kanit)]


def duzelt(kanit: dict, yeniden_kos: Callable[[dict, dict], dict],
           hata_al: Callable[[dict], float | None],
           maks: int = MAKS_DENEME) -> DuzelticiSonuc:
    """Tespit → düzelt → yeniden koş → yeniden sınıflandır döngüsü.

    yeniden_kos(kanit, degisiklik) -> yeni kanıt.  Çağıran sağlar; bu katman
    çözücü bilmez. hata_al(kanit) -> bağıl hata [%] ya da None.

    DÖNGÜ ŞU ÜÇ DURUMDA DURUR:
      1. Tetiklenen düzeltme kalmadı,
      2. maks denemeye ulaşıldı,
      3. Uygulanan düzeltme hatayı iyileştirmedi — ki bu, kusurun giderildiği
         ama SAPMANIN AÇIKLANMADIĞI anlamına gelir ve raporlanır.
    """
    s = DuzelticiSonuc(sinif=kanit.get("sinif", TREND))
    denenen: set[str] = set()
    for _ in range(maks):
        aday = [d for d in uygulanabilir(kanit) if d.ad not in denenen]
        if not aday:
            break
        d = aday[0]
        denenen.add(d.ad)
        onceki = hata_al(kanit)
        degisiklik = d.uygula(kanit)
        yeni = yeniden_kos(kanit, degisiklik)
        sonraki = hata_al(yeni)
        yaradi = None
        if onceki is not None and sonraki is not None and onceki > 0:
            yaradi = (onceki - sonraki) / onceki >= IYILESME_ESIGI
        s.mudahaleler.append(Mudahale(d.ad, d.aciklama, degisiklik, onceki,
                                      sonraki, yaradi, d.yan_etki))
        kanit = yeni
        s.sinif = kanit.get("sinif", s.sinif)
        if yaradi is False:
            s.kalan_aday = ("Kusur giderildi ama sapma sürüyor — kaynak bu "
                            "düzeltmenin hedefi DEĞİL.")
            break
        if s.sinif == VALIDATED:
            break

    if not s.mudahaleler:
        s.verdikt = "Tetiklenen düzeltme yok; sonuç olduğu gibi bırakıldı."
    elif s.sinif == VALIDATED:
        s.verdikt = (f"{len(s.mudahaleler)} düzeltme uygulandı, sonuç "
                     "design-grade'e ulaştı. Her müdahale kayıtlıdır.")
    else:
        s.verdikt = (f"{len(s.mudahaleler)} düzeltme uygulandı "
                     f"({s.etkisiz_sayisi} etkisiz); sonuç hâlâ design-grade "
                     "DEĞİL ve öyle raporlanır. " + (s.kalan_aday or ""))
    return s
