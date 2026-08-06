"""Girdi belirsizliği yayılımı — ASME V&V 20'nin eksik adımı.

NEDEN GEREKLİ: bugüne dek raporlanan belirsizlik AYRIKLAŞTIRMA (mesh/panel) ve
MODEL-FORM bileşenlerinden ibaretti. Oysa sonuç girdilere de bağlıdır: hız,
viskozite, hücum açısı, geometri ölçeği, malzeme modülü. Bu bileşen ölçülmeden
"toplam mühendislik belirsizliği" denemez — yalnız "ayrıklaştırma belirsizliği"
denebilir.

NE YAPILABİLİR, NE YAPILAMAZ — dürüst ayrım:

  UCUZ MODELLER (birleştirici, taşıyıcı-çizgi, düz-levha, kapalı-form FEA):
      fonksiyon saniyeler içinde çağrılabildiği için duyarlılık MERKEZİ SONLU
      FARKLA doğrudan ÖLÇÜLÜR. Burada yayılım gerçek bir ölçümdür.

  RANS: her nokta saatler sürer. Girdi başına iki koşu gerekir ve bu donanımda
      tractable değildir. Bu yolda girdi belirsizliği YAYILMAZ ve bu açıkça
      söylenir — kestirim uydurulmaz.

Yöntem (ASME V&V 20 §7, birinci mertebe): bağımsız girdiler için

    u_f² = Σ (∂f/∂x_i · u_{x_i})²

Türevler merkezi sonlu farkla alınır. İkinci mertebe etkiler ve girdiler arası
korelasyon İHMAL EDİLİR; bu kısıt kayda geçer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Varsayılan girdi belirsizlikleri — KAYNAĞIYLA. Bunlar ölçüm değil BEYANDIR;
# kullanıcı kendi ölçüm zincirini biliyorsa geçersiz kılmalıdır.
VARSAYILAN_KAYNAK = {
    "hiz": "pitot/anemometre tipik ±%2 (kalibrasyonsuz)",
    "nu": "sıcaklık ±5 °C → kinematik viskozite ±%3",
    "alfa": "montaj/ölçüm toleransı ±0.5°",
    "olcek": "STL/CAD ölçek ve imalat toleransı ±%1",
}


@dataclass
class GirdiBelirsizligi:
    """Bir girdinin nominal değeri ve standart belirsizliği.

    `bagil=True` ise `u` orandır (0.02 = %2); değilse mutlak birimdedir.
    """
    ad: str
    nominal: float
    u: float
    bagil: bool = True
    kaynak: str = ""

    @property
    def u_mutlak(self) -> float:
        return abs(self.nominal) * self.u if self.bagil else abs(self.u)


@dataclass
class YayilimSonucu:
    deger: float
    u_toplam: float
    paylar: dict = field(default_factory=dict)
    _kisit: str = ""

    @property
    def u_pct(self) -> float | None:
        return abs(self.u_toplam / self.deger) * 100 if self.deger else None

    @property
    def baskin(self) -> str | None:
        """Toplam belirsizliğe en çok katkı veren girdi."""
        return max(self.paylar, key=lambda k: self.paylar[k]) if self.paylar else None


# Türev adımı, girdinin KENDİ belirsizliğine göre seçilir: çok küçük adım
# yuvarlama gürültüsüne, çok büyük adım doğrusal-olmayan bölgeye taşar.
ADIM_ORANI = 0.5


def yay(fonksiyon, girdiler: list[GirdiBelirsizligi],
        adim_orani: float = ADIM_ORANI) -> YayilimSonucu:
    """Birinci mertebe yayılım — türevler MERKEZİ SONLU FARKLA ÖLÇÜLÜR.

    `fonksiyon(**{ad: deger})` sayı döndürmelidir. Fonksiyon herhangi bir
    noktada sayı döndüremezse (kapıya takılırsa) o girdinin payı ÖLÇÜLEMEDİ
    olarak işaretlenir; sıfır sayılmaz.
    """
    nominal = {g.ad: g.nominal for g in girdiler}
    f0 = fonksiyon(**nominal)
    if f0 is None or not math.isfinite(float(f0)):
        return YayilimSonucu(deger=float("nan"), u_toplam=float("nan"),
                             _kisit="nominal noktada fonksiyon sayı döndürmedi")

    paylar: dict[str, float | str] = {}
    kare_toplam = 0.0
    olculemeyen: list[str] = []
    for g in girdiler:
        h = g.u_mutlak * adim_orani
        if h == 0:
            paylar[g.ad] = 0.0
            continue
        arti = fonksiyon(**{**nominal, g.ad: g.nominal + h})
        eksi = fonksiyon(**{**nominal, g.ad: g.nominal - h})
        if (arti is None or eksi is None
                or not math.isfinite(float(arti)) or not math.isfinite(float(eksi))):
            paylar[g.ad] = "ÖLÇÜLEMEDİ"
            olculemeyen.append(g.ad)
            continue
        turev = (float(arti) - float(eksi)) / (2 * h)
        katki = abs(turev) * g.u_mutlak
        paylar[g.ad] = katki
        kare_toplam += katki ** 2

    kisit = ("Birinci mertebe (ASME V&V 20 §7); girdiler BAĞIMSIZ varsayıldı, "
             "korelasyon ve ikinci mertebe etkiler ihmal edildi. Türevler "
             "merkezi sonlu farkla ÖLÇÜLDÜ.")
    if olculemeyen:
        kisit += (f" EKSİK: {', '.join(olculemeyen)} girdisinin payı "
                  "ölçülemedi (fonksiyon o noktada sayı vermedi) — toplam "
                  "ALT SINIRDIR.")
    return YayilimSonucu(deger=float(f0), u_toplam=math.sqrt(kare_toplam),
                         paylar=paylar, _kisit=kisit)


def birlestir(bilesenler: dict[str, float | None]) -> dict:
    """Belirsizlik bileşenlerini birleştir — ÖLÇÜLMEYEN sıfır sayılmaz.

    `None` geçilen bileşen "ölçülmedi" demektir ve toplam ALT SINIR olur.
    Bu ayrım bu depoda bir kez kaybolmuş ve bir fark ±%0.1 ile "kesin"
    görünmüştü.
    """
    olculen = {k: v for k, v in bilesenler.items() if v is not None}
    eksik = [k for k, v in bilesenler.items() if v is None]
    toplam = math.sqrt(sum(v ** 2 for v in olculen.values())) if olculen else None
    return {
        "u_toplam_pct": round(toplam, 3) if toplam is not None else None,
        "olculen_bilesenler": {k: round(v, 3) for k, v in olculen.items()},
        "olculmeyen_bilesenler": eksik,
        "alt_sinir_mi": bool(eksik),
        "_anlam": ("ALT SINIR: ölçülmeyen bileşen(ler) var, gerçek belirsizlik "
                   "bundan BÜYÜKTÜR." if eksik else
                   "Tüm bileşenler ölçüldü."),
    }
