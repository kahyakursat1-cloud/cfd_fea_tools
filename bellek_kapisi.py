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

# MESHLEME TEPESİ — ÖLÇÜLDÜ 2026-08-20, kapının kendi beyan ettiği boşluk.
# `experiments/snappy_katman_tepe_bellegi.py`: Ahmed gövdesi, n_layers=3, dört
# kademe (54.748 / 142.362 / 272.756 / 567.549 hücre), snappyHexMesh
# `/usr/bin/time -v` altında, tepe RSS okundu:
#     0,143 / 0,291 / 0,509 / 0,993 GB   →   1,656 kB/hücre + 0,055 GB, R²=0,99996
# Katman örgüsü TEYİTLİ (log tablosu: gövde yaması 202 yüz, 3/3 katman, %100
# kalınlık) — katmansız bir yolu katmanlı sanıp ölçme riski kapatıldı.
#
# GERİ-TAHMİN DOĞRULAMASI: AR6 çapası 6M hücrede koşmuştu; bu katsayı 9,99 GB
# öngörüyor, o an boş olan 7,9 GB'ın üstünde — yani OOM. Gözlenen tam buydu
# (snappyHexMesh, çıkış kodu 137, displacementMedialAxis). Katsayı 55k–568k
# aralığında oturtulup 10× ötelenerek doğru hüküm verdi.
#
# ÇÖZÜM katsayısının 2,13 KATI: meshleme ~0,25M hücreden sonra bağlayıcı olan
# aşamadır. Kapı bunu bilmediği için AR6'da "sığar" demişti.
#
# SINIR: tek geometri (Ahmed), n_layers=3. Katmansız meshlemede tepe daha
# düşüktür, yani bu değer o yol için ÜST SINIRDIR — muhafazakâr, uydurma değil.
MESH_KB_HUCRE = 1.656
MESH_SABIT_GB = 0.055
MESH_KAYNAK = ("ölçülen (4 kademe, Ahmed n_layers=3, R²=0,99996, "
               "snappy_katman_tepe_bellegi.json)")


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
    mesh_ham = cells * MESH_KB_HUCRE / 1e6 + MESH_SABIT_GB
    # BAGLAYICI ASAMA MAX'TIR, TOPLAM DEGIL: meshleme ve cozum ayni anda degil
    # ARDISIK calisir, yani tepe ikisinin buyugudur. Toplamak gereginden kati
    # olurdu; yalniz cozume bakmak ise AR6'da OOM'a goturdu.
    bagli = "meshleme" if mesh_ham > ham else "çözüm"
    ham_bagli = max(ham, mesh_ham)
    return {**k, "cells": cells, "ham_gb": ham,
            "mesh_ham_gb": mesh_ham, "mesh_kaynak": MESH_KAYNAK,
            "baglayici_asama": bagli,
            "gereken_gb": ham_bagli * GUVENLIK_PAYI,
            "cozum_gereken_gb": ham * GUVENLIK_PAYI,
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
        # ONERILEN TAVAN BAGLAYICI ASAMADAN turetilir. Cozum katsayisindan
        # turetmek, meshleme baglayiciyken YINE asilabilir bir tavan onerirdi.
        if t["baglayici_asama"] == "meshleme":
            onerilen = int(max(0.0, bos / GUVENLIK_PAYI - MESH_SABIT_GB)
                           * 1e6 / MESH_KB_HUCRE)
        else:
            onerilen = int(bos / GUVENLIK_PAYI * 1e6 / t["kb_hucre"])
        return {**out, "kosulabilir": False, "onerilen_max_cells": onerilen,
                "mesaj": (f"{cells:,} hücre için ~{t['gereken_gb']:.2f} GB gerekir "
                          f"(bağlayıcı aşama: {t['baglayici_asama']}; çözüm tek "
                          f"başına ~{t['cozum_gereken_gb']:.2f} GB), boş {bos:.1f} GB. "
                          f"Bütçeyi ~{onerilen:,} hücreye indirin ya da belleği "
                          f"boşaltın. Tahmin kaynağı: {t['kaynak']} + "
                          f"{t['mesh_kaynak']}")}
    # KAPSAM BEYAN EDILIR — "sigar" hukmu HANGI ASAMA icin gecerli?
    #
    # OLCULDU (2026-08-19, AR6 capasi 4. deneme): kapi "6.000.000 hucre
    # ~6,07 GB; bos 7,9 GB — sigar" dedi ve snappyHexMesh 1319 saniye sonra
    # SIGKILL ile olduruldu (cikis kodu 137), katman ekleme adiminda
    # (displacementMedialAxis). Yani hukum YANLISTI.
    #
    # KOK NEDEN ASAMA KORLUGU: katsayi `basarim/b60k_c*` gibi COZUM
    # kosularindan turetildi (kb_hucre 0,779 + 0,215 GB sabit, R^2=0,96) ve
    # cozucunun bellegini olcuyor. snappyHexMesh'in KATMAN adimi bambaska bir
    # tepe yapar: medial-axis hesabi tum yuzey noktalarinin mesafe alanini
    # tutar ve gecici veri yapilari son hucre sayisiyla orantili DEGILDIR.
    #
    # BOSLUK KAPANDI (2026-08-20): snappy katman tepesi OLCULDU (MESH_KB_HUCRE,
    # yukaridaki gerekce). Kapsam beyani artik "olcemedim" degil, olculen iki
    # asamadan HANGISININ bagladigini soyluyor. Beyan kaldirilmadi, GERCEGE
    # UYDURULDU — kapsamini soylemeyi birakmak, boslugu kapatmakla ayni sey
    # degildir.
    return {**out, "kosulabilir": True,
            "kapsam": "meshleme (snappy katman) + ÇÖZÜM — ikisi de ölçülü",
            "kapsanmayan": ("katmansız meshleme ve decomposePar/reconstructPar "
                            "tepe değerleri ayrıca ölçülmedi; katman katsayısı "
                            "tek geometride (Ahmed, n_layers=3) ölçüldü ve "
                            "katmansız yol için ÜST SINIRDIR"),
            "mesaj": (f"{cells:,} hücre ~{t['gereken_gb']:.2f} GB; boş {bos:.1f} GB "
                      f"— sığar. Bağlayıcı aşama: {t['baglayici_asama']} "
                      f"(meshleme tepesi ~{t['mesh_ham_gb']:.2f} GB, çözüm "
                      f"~{t['ham_gb']:.2f} GB; tepe ikisinin BÜYÜĞÜDÜR çünkü "
                      f"ardışık çalışırlar). Tahmin kaynağı: {t['kaynak']} + "
                      f"{t['mesh_kaynak']}.")}
