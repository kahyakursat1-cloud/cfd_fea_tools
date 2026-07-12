"""Klasik Laminasyon Teorisi (CLT) — kompozit serimden EŞDEĞER düzlem-içi sabitler.

Amaç: kabuk FEA'sında kompozit deriyi (ör. [0/±45/90]s karbon) tek ortotropik
eşdeğer malzemeyle temsil etmek (calculix_writer ENGINEERING CONSTANTS yolu).
DÜRÜSTLÜK: eşdeğerleme yalnız DÜZLEM-İÇİ rijitlik içindir (A-matrisi); eğilme
(D-matrisi) farklı sıralamada farklıdır ve katman-bazlı hasar/delaminasyon
analizi bu yaklaşımın DIŞINDADIR — ön-tasarım rijitlik/frekans aracı.

Kaynak: Jones, Mechanics of Composite Materials; Kollár & Springer.
"""
from __future__ import annotations

import math

import numpy as np


def q_matrisi(e1: float, e2: float, g12: float, nu12: float) -> np.ndarray:
    """Tek katmanın (lamina) indirgenmiş rijitlik matrisi Q (malzeme ekseninde)."""
    nu21 = nu12 * e2 / e1
    d = 1.0 - nu12 * nu21
    return np.array([[e1 / d, nu12 * e2 / d, 0.0],
                     [nu12 * e2 / d, e2 / d, 0.0],
                     [0.0, 0.0, g12]])


def qbar(q: np.ndarray, aci_derece: float) -> np.ndarray:
    """Q'nun laminat eksenine döndürülmüşü (Qbar)."""
    c, s = math.cos(math.radians(aci_derece)), math.sin(math.radians(aci_derece))
    T = np.array([[c * c, s * s, 2 * c * s],
                  [s * s, c * c, -2 * c * s],
                  [-c * s, c * s, c * c - s * s]])
    R = np.diag([1.0, 1.0, 2.0])
    return np.linalg.inv(T) @ q @ R @ T @ np.linalg.inv(R)


def esdeger_sabitler(e1: float, e2: float, g12: float, nu12: float,
                     serim: list[float], t_katman: float) -> dict:
    """Serimden (açı listesi, ör. [0, 45, -45, 90, 90, -45, 45, 0]) düzlem-içi
    eşdeğer mühendislik sabitleri. Birimler girdiyle aynı (Pa önerilir).
    Döner: {Ex, Ey, Gxy, nuxy, kalinlik, simetrik_mi}."""
    if not serim:
        raise ValueError("serim boş")
    q = q_matrisi(e1, e2, g12, nu12)
    A = np.zeros((3, 3))
    for aci in serim:
        A += qbar(q, aci) * t_katman
    h = t_katman * len(serim)
    a = np.linalg.inv(A)
    simetrik = serim == serim[::-1]
    return {"Ex": float(1.0 / (h * a[0, 0])),
            "Ey": float(1.0 / (h * a[1, 1])),
            "Gxy": float(1.0 / (h * a[2, 2])),
            "nuxy": float(-a[0, 1] / a[0, 0]),
            "kalinlik": h, "simetrik_mi": simetrik,
            "_not": ("Düzlem-içi eşdeğer (A-matrisi); eğilme/D ve katman-hasarı "
                     "kapsam dışı — ön-tasarım rijitlik aracı."
                     + ("" if simetrik else " UYARI: serim SİMETRİK DEĞİL — "
                        "gerçek laminatta çekme-eğilme kuplajı (B≠0) oluşur."))}


def engineering_constants_9(es: dict, ez_orani: float = 0.5,
                            nu_z: float = 0.3) -> tuple:
    """CLT düzlem-içi eşdeğerlerinden CalculiX *ELASTIC,TYPE=ENGINEERING CONSTANTS
    için 9'lu takım (E1,E2,E3,nu12,nu13,nu23,G12,G13,G23). Kalınlık-yönü (3)
    sabitleri kabuk davranışında İKİNCİLDİR; E3≈ez_orani·E2 (reçine-baskın)
    pragmatik kabulü belgelidir — kabuk (S3/B31) elemanlarında sonuç düzlem-içi
    sabitlerce belirlenir."""
    e3 = ez_orani * es["Ey"]
    g_z = e3 / (2 * (1 + nu_z))
    return (es["Ex"], es["Ey"], e3, es["nuxy"], nu_z, nu_z,
            es["Gxy"], g_z, g_z)
