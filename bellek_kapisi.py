"""Bellek kapısı — hücre bütçesi makinenin belleğinden habersizdi.

NEDEN: `max_cells` sabit bir sayıdır (hassas: 2,5 M). 32 GB'lık bir makinede
rahat, 8 GB'lık bir makinede takas-çilesi ya da OOM demektir; ikisi de aynı
preset'i kullanır. Disk için bekçi vardı (kuyruk, 8 GB), bellek için yoktu.

KATSAYI ÖLÇÜLÜR, UYDURULMAZ. Hücre başına bellek çözücüye, model sayısına ve
katman sayısına bağlıdır; tek doğru sayı yoktur. Bu modül katsayıyı KOŞU
ARŞİVİNDEN türetir. Ölçüm yoksa bir ÖNCÜL kullanılır ve bunun ölçüm OLMADIĞI
her çıktıda yazılır — bu depoda "ölçemedim" ile "iyi" karıştırılmaz.

ÖLÇÜLDÜ (2026-08-11): 0,779 kB/hücre + 0,215 GB sabit yük, R²=0,96 — üç
büyük koşudan DOĞRUSAL uyumla (`experiments/bellek_katsayisi.py --olc`).
Eğim kritikti: oran (artış/hücre) modeli WSL2 VM'inin ve decomposePar
kopyalarının sabit yükünü hücreye dağıtıyor ve küçük koşularda katsayıyı
şişiriyordu (18k hücrede 9,75 kB/hücre çıkmıştı). Ölçüm öncülden (%1,0)
%22 düşük — kapı gereğinden katı davranıyormuş.

Öncül (ölçüm yokken): simpleFoam/incompressibleFluid için ~1,0 kB/hücre
mertebesi. Mertebe doğrudur, kesinlik iddiası YOKTUR.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
KANIT = HERE / "bellek_katsayisi.json"

ONCUL_KB_HUCRE = 1.0        # ölçüm yokken kullanılan mertebe (ölçüm DEĞİL)
GUVENLIK_PAYI = 1.3         # işletim sistemi + diğer süreçler + parçalanma
EN_AZ_BOS_GB = 2.0          # bunun altında hiçbir koşu başlatılmaz


def bos_bellek_gb() -> float | None:
    """Kullanılabilir bellek (GB). psutil yoksa None — 'ölçülemedi'."""
    if importlib.util.find_spec("psutil") is None:
        return None
    import psutil
    return psutil.virtual_memory().available / 1e9


def katsayi() -> dict:
    """(kB/hücre, kaynak). Koşu arşivinden ölçülmüşse o, yoksa öncül."""
    if KANIT.exists():
        d = json.loads(KANIT.read_text(encoding="utf-8"))
        v = d.get("kb_hucre")
        if isinstance(v, (int, float)) and v > 0:
            return {"kb_hucre": float(v), "olculdu": True,
                    "kaynak": f"ölçülen ({d.get('n_kosu', '?')} koşu, "
                              f"{KANIT.name})"}
    return {"kb_hucre": ONCUL_KB_HUCRE, "olculdu": False,
            "kaynak": "ÖNCÜL — bu bir ölçüm DEĞİLDİR; mertebe tahminidir "
                      "(experiments/bellek_katsayisi.py ile ölçülebilir)"}


def tahmini_gb(cells: int) -> dict:
    # HESAP YUVARLAMAZ. Onceki surum `gereken_gb`'yi yuvarlanmamis ham degerden
    # hesapliyor ama `ham_gb`'yi yuvarlayarak veriyordu; iki sayi arasindaki
    # oran GUVENLIK_PAYI'na esit cikmiyordu (0.78 x 1.3 = 1.014, raporlanan
    # 1.01). Ondalik onculde (1.0 kB) carpisma gorunmuyordu — kusur vardi ama
    # OLCULEN katsayi (0.7786) gelene kadar ortaya cikmadi. Sabit ondalikta
    # yuvarlamak kucuk butcelerde goreli hatayi buyutur (50k hucrede %0.6);
    # dogrusu yuvarlamayi SUNUM katmanina birakmaktir — `hukum` mesaji zaten
    # kendi bicimini uyguluyor.
    k = katsayi()
    ham = cells * k["kb_hucre"] / 1e6                # kB -> GB
    return {**k, "cells": cells, "ham_gb": ham,
            "gereken_gb": ham * GUVENLIK_PAYI,
            "guvenlik_payi": GUVENLIK_PAYI}


def hukum(cells: int, bos_gb: float | None = None) -> dict:
    """Bu hücre bütçesi bu makinede koşar mı?

    Döner: {"koşulabilir": bool|None, ...}. None = ölçülemedi (psutil yok) —
    kapı o zaman ENGEL OLMAZ ama sessiz de kalmaz.
    """
    t = tahmini_gb(cells)
    bos = bos_bellek_gb() if bos_gb is None else bos_gb
    if bos is None:
        return {**t, "bos_gb": None, "kosulabilir": None,
                "mesaj": "Bellek OKUNAMADI (psutil yok) — bütçe denetlenmedi."}
    out = {**t, "bos_gb": round(bos, 2)}
    if bos < EN_AZ_BOS_GB:
        return {**out, "kosulabilir": False,
                "mesaj": f"Boş bellek {bos:.1f} GB < mutlak taban "
                         f"{EN_AZ_BOS_GB} GB — hiçbir koşu başlatılmaz."}
    if t["gereken_gb"] > bos:
        onerilen = int(bos / GUVENLIK_PAYI * 1e6 / t["kb_hucre"])
        return {**out, "kosulabilir": False, "onerilen_max_cells": onerilen,
                "mesaj": (f"{cells:,} hücre için ~{t['gereken_gb']:.2f} GB gerekir, "
                          f"boş {bos:.1f} GB. Bütçeyi ~{onerilen:,} hücreye "
                          f"indirin ya da belleği boşaltın. Tahmin kaynağı: "
                          f"{t['kaynak']}")}
    return {**out, "kosulabilir": True,
            "mesaj": (f"{cells:,} hücre ~{t['gereken_gb']:.2f} GB; boş {bos:.1f} GB "
                      f"— sığar. Tahmin kaynağı: {t['kaynak']}")}
