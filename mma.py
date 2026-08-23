"""MMA (Method of Moving Asymptotes, Svanberg 1987) — tek kısıtlı alt-problem.

NEDEN GEREKLİ: topoloji optimizasyonu OC (optimality criteria) ile
güncelleniyor ve OC adımı şu satıra dayanıyor:

    be = np.maximum(-dx, 0) / lmid

Bu, duyarlılığı POZİTİF olan elemanları sıfırlar --- yani "bu elemanın
yoğunluğunu artırmak amacı KÖTÜLEŞTİRİR" bilgisini ATAR. Kompliyans
minimizasyonunda duyarlılık her zaman negatiftir ve kayıp yoktur; P-norm
gerilme minimizasyonunda DEĞİLDİR.

ÖLÇÜLDÜ (2026-08-23, L-braket 3B, 12×12×3): aktif elemanların %12,8--65,7'si
her adımda pozitif duyarlılık taşıyor ve GRADYAN BÜYÜKLÜĞÜNÜN atılan payı
3. iterasyonda %96,9'a çıkıyor. Amaç tam o adımda 12,95 → 97,54 sıçrıyor.
Kodun kendi yorumu zaten "OC stress'te tek-başına kararsız/salınımlı, iyi
topoloji başlangıcı şart" diyordu; bu ölçüm o cümlenin SEBEBİNİ verir.

MMA pozitif duyarlılığı ATMAZ: her değişken için iki asimptot (L_j, U_j)
tutar ve amacı bunların arasında dışbükey ayrılabilir bir fonksiyonla
yaklaşıklar. Pozitif gradyan, alt asimptota doğru bir itki olarak temsil
edilir --- bilgi korunur.

KAPSAM: tek kısıt (hacim). Svanberg'in genel m-kısıtlı biçimi burada YOK;
gerekmediği için yazılmadı. Tek kısıtta ikil problem SKALERDİR ve
bisection'la çözülür.

Referans: K. Svanberg, "The Method of Moving Asymptotes — a new method for
structural optimization", IJNME 24 (1987) 359-373.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Svanberg'in onerdigi degerler; asimptot uyarlamasinin katsayilari.
S_INIT = 0.5        # ilk iki iterasyonda asimptot mesafesi (aralik carpani)
S_YAVAS = 0.7       # salinim varsa asimptotlari YAKLASTIR (adimi kucult)
S_HIZLI = 1.2       # tekduze ilerliyorsa UZAKLASTIR (adimi buyut)
ALBEFA = 0.1        # hareket sinirlarinin asimptota uzakligi
RAA0 = 1e-5         # dogrusal-olmayan terimin taban katkisi


@dataclass
class MMADurum:
    """İki önceki iterasyonun x'i ve asimptotlar — MMA'nın belleği.

    OC belleksizdir; MMA'nın kararlılığı tam olarak bu bellekten gelir
    (salınım görülürse asimptotlar yaklaştırılır, adım kendiliğinden küçülür).
    """
    xold1: np.ndarray | None = None
    xold2: np.ndarray | None = None
    low: np.ndarray | None = None
    upp: np.ndarray | None = None
    iterasyon: int = 0
    gecmis: list = field(default_factory=list)


def _asimptotlar(x, xmin, xmax, d: MMADurum):
    """Asimptotları güncelle (Svanberg §3). İlk iki adım sabit mesafe."""
    aralik = xmax - xmin
    if d.iterasyon <= 2 or d.xold1 is None or d.xold2 is None:
        low = x - S_INIT * aralik
        upp = x + S_INIT * aralik
        return low, upp
    # Salinim testi: ardisik iki adimin YONU ters ise carpani kucult.
    isaret = (x - d.xold1) * (d.xold1 - d.xold2)
    gama = np.where(isaret < 0, S_YAVAS, np.where(isaret > 0, S_HIZLI, 1.0))
    low = x - gama * (d.xold1 - d.low)
    upp = x + gama * (d.upp - d.xold1)
    # Asimptotlar ne cok yakin ne cok uzak olmali (sayisal koruma).
    low = np.clip(low, x - 10.0 * aralik, x - 0.01 * aralik)
    upp = np.clip(upp, x + 0.01 * aralik, x + 10.0 * aralik)
    return low, upp


def _pq(df, x, low, upp, aralik):
    """MMA yaklaşıklığının p ve q katsayıları.

    POZİTİF ve NEGATİF gradyan AYRI AYRI taşınır --- OC'nin attığı bilgi
    burada `p` terimine girer.
    """
    dfp = np.maximum(df, 0.0)
    dfn = np.maximum(-df, 0.0)
    taban = RAA0 / np.maximum(aralik, 1e-12)
    p = (upp - x) ** 2 * (1.001 * dfp + 0.001 * dfn + taban)
    q = (x - low) ** 2 * (0.001 * dfp + 1.001 * dfn + taban)
    return p, q


def mma_adim(x, df0, df1, kisit_degeri, xmin, xmax, durum: MMADurum,
             move: float = 0.2) -> np.ndarray:
    """Bir MMA adımı: min f0, s.t. f1 <= 0, xmin <= x <= xmax.

    df0, df1 : amacın ve kısıtın x'e göre gradyanları (eleman başına)
    kisit_degeri : f1(x) --- pozitifse kısıt İHLAL edilmiş demektir

    Dönen: yeni x. `durum` yerinde güncellenir (bellek MMA'nın kendisidir).
    """
    x = np.asarray(x, float)
    durum.iterasyon += 1
    aralik = xmax - xmin
    low, upp = _asimptotlar(x, xmin, xmax, durum)

    # HAREKET SINIRLARI: asimptotlarin icinde kalinmali (tekillik korumasi)
    alfa = np.maximum(np.maximum(xmin, low + ALBEFA * (x - low)), x - move * aralik)
    beta = np.minimum(np.minimum(xmax, upp - ALBEFA * (upp - x)), x + move * aralik)

    p0, q0 = _pq(df0, x, low, upp, aralik)
    p1, q1 = _pq(df1, x, low, upp, aralik)
    # Kisitin sabit terimi: f1(x) - Σ [p1/(U-x) + q1/(x-L)]
    r1 = kisit_degeri - float((p1 / (upp - x) + q1 / (x - low)).sum())

    def x_lam(lam):
        pl = np.sqrt(p0 + lam * p1)
        ql = np.sqrt(q0 + lam * q1)
        xx = (pl * low + ql * upp) / (pl + ql)
        return np.clip(xx, alfa, beta)

    def g(lam):
        xx = x_lam(lam)
        return r1 + float((p1 / (upp - xx) + q1 / (xx - low)).sum())

    # IKIL PROBLEM TEK KISITTA SKALERDIR: g(lam) azalan; kok bisection ile.
    lo, hi = 0.0, 1.0
    for _ in range(60):
        if g(hi) <= 0:
            break
        hi *= 2.0
    else:
        return x_lam(hi)
    if g(lo) <= 0:
        lam = 0.0                      # kisit zaten saglaniyor
    else:
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if g(mid) > 0:
                lo = mid
            else:
                hi = mid
        lam = 0.5 * (lo + hi)

    xnew = x_lam(lam)
    durum.xold2 = durum.xold1
    durum.xold1 = x.copy()
    durum.low, durum.upp = low, upp
    durum.gecmis.append({"iter": durum.iterasyon, "lambda": float(lam),
                         "asimptot_genislik": float(np.mean(upp - low))})
    return xnew
