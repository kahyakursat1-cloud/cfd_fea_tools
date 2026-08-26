"""Korunumlu yük aktarımı — kuvveti TAŞI, basıncı yeniden integre ETME.

ÖLÇÜLEN KUSUR (20 vaka, fsi_korunum.json): CFD→FEA aktarım hatası %0,07--%56,30.
Sebep şemadadır, uygulamada değil.

MEVCUT ŞEMA (``tutarlı'' / field-preserving): her FEA yüzüne en yakın CFD
yüzünün BASINCI atanır, sonra kuvvet FEA ağı üzerinde YENİDEN İNTEGRE edilir:

    F_FEA = Σ_FEA_yüzleri  (−p_interp · n_FEA · A_FEA)

İki yüzeyin alanı farklıysa toplam kuvvet de farklı çıkar --- ve ölçüm bunu
doğruluyor: alan farkı %49,83 olan `gripen_AB_Right` %56,30 aktarım hatası
verirken, alan farkı ~0 olan beş vakada hata ≤%3,88 kalıyor.

BU ŞEMA (``korunumlu'' / load-preserving): CFD yüzünün KUVVETİ hesaplanır ve
toplamı 1 olan ağırlıklarla FEA düğümlerine dağıtılır:

    F_FEA = Σ_CFD_yüzleri  dF_CFD ,   Σ_i w_i = 1

Toplam kuvvet YAPI GEREĞİ korunur --- alanlar farklı olsa bile. Bu bir
yaklaşım değil, kimliktir.

NE KORUNUR, NE KORUNMAZ --- DÜRÜST AYRIM:
  * KUVVET: tam korunur (ağırlıklar 1'e toplandığı için).
  * MOMENT: baryentrik ağırlıklarla, kuvvetin FEA yüzeyi üzerindeki İZDÜŞÜM
    noktasına uygulanmış olmasına kadar korunur. İki yüzey arasındaki boşluk
    kadar bir artık kalır ve bu artık ÖLÇÜLÜR (`arayuz_isi_hatasi`), gizlenmez.
  * YEREL BASINÇ ALANI: korunumlu şema yerel dağılımı tutarlı şemadan DAHA
    KÖTÜ verebilir. Literatürdeki klasik takas budur; bu yüzden şema
    değiştirilmeden önce İKİSİ DE ölçülür.

BU DOSYA ŞEMAYI DEĞİŞTİRMEZ, EKLER. Hangisinin üretime gireceği ölçümle
karara bağlanır --- ölçmeden değiştirmek, bu çalışmanın reddettiği şey.
"""
from __future__ import annotations

import numpy as np


def baryentrik(p: np.ndarray, a: np.ndarray, b: np.ndarray,
               c: np.ndarray) -> np.ndarray:
    """`p`nin `abc` üçgenindeki baryentrik ağırlıkları --- kırpılmış.

    Ağırlıklar 1'e toplanır ve negatif olmaz: izdüşüm üçgenin dışına
    düştüğünde (yüzeyler tam örtüşmediğinde olur) kırpma yapılır ve yeniden
    normalleştirilir. Kırpmadan bırakmak, bir düğüme NEGATİF kuvvet
    bindirirdi --- toplam yine korunurdu ama yerel dağılım fiziksel olmazdı.
    """
    v0, v1, v2 = b - a, c - a, p - a
    d00 = np.einsum("ij,ij->i", v0, v0)
    d01 = np.einsum("ij,ij->i", v0, v1)
    d11 = np.einsum("ij,ij->i", v1, v1)
    d20 = np.einsum("ij,ij->i", v2, v0)
    d21 = np.einsum("ij,ij->i", v2, v1)
    payda = d00 * d11 - d01 * d01
    # Dejenere ucgen: esit-ucte-bir. Sifira bolmek yerine ACIK varsayilan.
    iyi = np.abs(payda) > 1e-30
    v = np.where(iyi, (d11 * d20 - d01 * d21) / np.where(iyi, payda, 1.0), 1 / 3)
    w = np.where(iyi, (d00 * d21 - d01 * d20) / np.where(iyi, payda, 1.0), 1 / 3)
    u = 1.0 - v - w
    agirlik = np.clip(np.stack([u, v, w], axis=1), 0.0, None)
    toplam = agirlik.sum(axis=1, keepdims=True)
    return agirlik / np.where(toplam > 1e-30, toplam, 1.0)


def korunumlu_dagit(dF_cfd: np.ndarray, cfd_merkez: np.ndarray,
                    fea_nodes: np.ndarray, faces: np.ndarray,
                    f_centers: np.ndarray) -> tuple[np.ndarray, dict]:
    """CFD yüz kuvvetlerini FEA düğümlerine KORUNUMLU dağıt.

    Her CFD yüzü, merkezine en yakın FEA üçgenine taşınır ve o üçgenin üç
    düğümüne baryentrik ağırlıklarla bölünür. Ağırlıklar 1'e toplandığı için

        Σ F_düğüm  ==  Σ dF_CFD

    makine hassasiyetinde sağlanır. Bu bir yaklaşım değil kimliktir; alanlar
    farklı olsa da geçerlidir ve mevcut şemanın %56'ya varan hatasının
    sebebini ortadan kaldırır.
    """
    from scipy.spatial import cKDTree

    _, hedef = cKDTree(f_centers).query(cfd_merkez, k=1)
    ucgen = faces[hedef]                                  # (C,3) dugum indisi
    a, b, c = (fea_nodes[ucgen[:, 0]], fea_nodes[ucgen[:, 1]],
               fea_nodes[ucgen[:, 2]])
    w = baryentrik(cfd_merkez, a, b, c)                   # (C,3)

    node_forces = np.zeros_like(fea_nodes)
    for k in range(3):
        np.add.at(node_forces, ucgen[:, k], w[:, k:k + 1] * dF_cfd)

    # UYGULAMA NOKTASI: agirlikli dugum konumu. Moment artigi bu nokta ile
    # CFD yuz merkezi arasindaki farktan gelir ve OLCULUR.
    uygulama = (w[:, 0:1] * a + w[:, 1:2] * b + w[:, 2:3] * c)
    kayma = np.linalg.norm(uygulama - cfd_merkez, axis=1)
    olcek = float(np.linalg.norm(fea_nodes.max(0) - fea_nodes.min(0)) + 1e-30)
    return node_forces, {
        "n_cfd_yuz": int(len(dF_cfd)),
        "kayma_ort_m": float(kayma.mean()),
        "kayma_max_m": float(kayma.max()),
        "kayma_ort_govde_orani": float(kayma.mean() / olcek),
        "kirpilan_izdusum_orani_pct": float(
            100.0 * np.mean(np.min(w, axis=1) <= 0.0)),
        "_not": ("Kuvvet YAPI GEREGI korunur (agirliklar 1'e toplanir). "
                 "Moment, kuvvetin izdusum noktasina uygulanmasina kadar "
                 "korunur; artik `kayma`dan gelir ve olculur."),
    }
