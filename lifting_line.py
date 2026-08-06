"""Prandtl taşıyıcı-çizgi — Glauert Fourier çözümü (kapalı form, çizelgesiz).

NEDEN BU MODÜL VAR: birleştirici indüklenen direnci VSPAERO'dan alıyordu ve o
sayı ÖLÇÜLDÜ ki yanlış. VSPAERO iki ayrı CDi veriyor ve İKİSİ DE teoriden
sapıyor (AR=5, `experiments/vlm_induklenen_capa.py`):

    taper   teori   yakın-alan      Trefftz
     1.00   0.963   0.807 (−16%)   1.032 (+7%)
     0.70   0.982   0.792 (−19%)   1.268 (+29%)
     0.50   0.991   0.785 (−21%)   1.601 (+62%)

Trefftz değeri e>1 ile Munk sınırını ihlal ediyor; yakın-alan değeri fiziksel
ama sistematik olarak yüksek CDi veriyor (panel yöntemlerinde bilinen ön-kenar
emme kaybı). Aralarından seçim yapmak yerine indüklenen direnç DOĞRULANMIŞ
kuramdan üretilir.

KENDİNİ DOĞRULAR: eliptik planformda e = 1.0 TAM olmalıdır (Munk) — çözücü
1.00000 veriyor. Bu, çizelgeye ya da ezbere dayanmayan bir kabul testidir.

GEÇERLİLİK: taşıyıcı-çizgi düz, orta/yüksek AR kanat içindir. Ok açısı ve
dihedral MODELLENMEZ; büyük ok açılı ya da AR<4 kanatta kullanılmaz —
`gecerli_mi` bunu söyler, çağıran kendi kararına bırakılmaz.
"""
from __future__ import annotations

import math

# Ok açısı bu değeri aşarsa taşıyıcı-çizgi geçerli değildir (süpürme
# yükleme dağılımını kaydırır, model bunu taşımaz).
OK_ACISI_MAX = 15.0
# Düşük AR'de taşıyıcı-çizgi bozulur; bu sınırın altında kullanılmaz.
AR_MIN = 4.0
KESIT_EGIMI = 2 * math.pi      # ince-profil kuramı, 1/rad


def gecerli_mi(ar: float, ok_acisi: float = 0.0) -> str | None:
    """Taşıyıcı-çizgi bu planformda kullanılamıyorsa GEREKÇE döndür."""
    if ar < AR_MIN:
        return (f"AR={ar:.2f} < {AR_MIN} — taşıyıcı-çizgi düşük en-boy oranında "
                "bozulur (kanat ucu akışı çizgi modeline sığmaz)")
    if abs(ok_acisi) > OK_ACISI_MAX:
        return (f"ok açısı {ok_acisi:g}° > {OK_ACISI_MAX}° — taşıyıcı-çizgi "
                "süpürmeyi modellemez")
    return None


def _cozum(ar: float, taper: float, n_terim: int, eliptik: bool):
    """Monoplan denklemini tek harmoniklerle çöz; Fourier katsayılarını döndür."""
    b = 1.0
    c_ort = b / ar
    kok = 2 * c_ort / (1 + taper)
    N = n_terim
    tetalar = [(i + 1) * math.pi / (2 * N + 1) for i in range(N)]
    nlar = [2 * i + 1 for i in range(N)]
    A = [[0.0] * N for _ in range(N)]
    rhs = [0.0] * N
    for i, th in enumerate(tetalar):
        eta = abs(math.cos(th))                       # |2y/b|
        c = ((c_ort * 4 / math.pi) * math.sqrt(max(0.0, 1 - eta ** 2)) if eliptik
             else kok * (1 - (1 - taper) * eta))
        mu = KESIT_EGIMI * c / (4 * b)
        for j, n in enumerate(nlar):
            A[i][j] = math.sin(n * th) * (n * mu + math.sin(th))
        rhs[i] = mu * math.sin(th)                    # (α − α_L0) = 1 rad
    for k in range(N):                                # kısmi pivotlu Gauss
        p = max(range(k, N), key=lambda r: abs(A[r][k]))
        A[k], A[p] = A[p], A[k]
        rhs[k], rhs[p] = rhs[p], rhs[k]
        for r in range(k + 1, N):
            f = A[r][k] / A[k][k]
            for c2 in range(k, N):
                A[r][c2] -= f * A[k][c2]
            rhs[r] -= f * rhs[k]
    x = [0.0] * N
    for k in range(N - 1, -1, -1):
        x[k] = (rhs[k] - sum(A[k][c] * x[c] for c in range(k + 1, N))) / A[k][k]
    return x, nlar


def span_verimi(ar: float, taper: float = 1.0, n_terim: int = 40,
                eliptik: bool = False) -> float:
    """e = A₁² / Σ n·Aₙ² = 1/(1+δ). Eliptik planformda TAM 1.0."""
    x, nlar = _cozum(ar, taper, n_terim, eliptik)
    delta = sum(n * (x[j] / x[0]) ** 2 for j, n in enumerate(nlar) if n > 1)
    return 1.0 / (1.0 + delta)


def tasima_egimi(ar: float, taper: float = 1.0, n_terim: int = 40,
                 eliptik: bool = False) -> float:
    """a_3B = π·AR·A₁ (1/rad), (α−α_L0)=1 rad için çözüldüğünden doğrudan eğim."""
    x, _ = _cozum(ar, taper, n_terim, eliptik)
    return math.pi * ar * x[0]


def induklenen_direnc(cl: float, ar: float, taper: float = 1.0) -> float:
    """CDi = Cl²/(π·AR·e) — e bu planform için kuramdan gelir, ölçülmez."""
    return cl ** 2 / (math.pi * ar * span_verimi(ar, taper))
