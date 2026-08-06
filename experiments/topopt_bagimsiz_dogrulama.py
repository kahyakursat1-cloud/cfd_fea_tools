"""Topoloji optimizasyonu — SONRASINDA BAĞIMSIZ YENİDEN-ANALİZ.

NEDEN: TO'nun raporladığı tepe gerilme, optimizasyonun KENDİ gridinde, KENDİ gri
(ara-yoğunluklu) alanı üzerinde hesaplanır. İmal edilecek parça ise ikilidir
(katı/boş) ve analiz edilecek ağ başka olur. Optimizasyonun ürettiği sayıyı
optimizasyonun kendi ağıyla doğrulamak dairesel bir iddiadır; bu depoda CFD
tarafında mesh-bağımsızlığı zorunluyken TO tarafında hiç sorulmamıştı.

BU DOSYA ÜÇ AYRI HATAYI AYRIŞTIRIR:
  1. EŞİKLEME (gri → ikili): aynı gridde, aynı hacimde. SIMP'in ara yoğunlukları
     atıldığında tepe gerilme ve kompliyans ne kadar değişir?
  2. AYRIKLAŞTIRMA: aynı ikili tasarım, 2× ve 3× ince bağımsız gridde. Kompliyans
     yakınsar; reentrant köşedeki TEPE GERİLME yakınsamaz (gerilme tekilliği) —
     ölçülür ve söylenir.
  3. OPTİMUMUN AĞ-BAĞIMLILIĞI: iki farklı TO gridinde (fiziksel filtre yarıçapı
     SABİT) üretilen tasarımlar ORTAK ince gridde karşılaştırılır.

ÖLÇEK: motor birim-küp eleman kullanır (a=1). Fiziksel kenar L=1 sabit tutulup
a=L/N alındığında  c_fiz = (N/L)·c_birim  ve  σ_fiz = (N/L)²·σ_birim. Bu dönüşüm
VARSAYILMAZ: betik önce tam-dolu ankastre kirişte üç çözünürlükte ölçer; yanlış
olsaydı ölçekli kompliyans N ile ıraksardı.

    python experiments/topopt_bagimsiz_dogrulama.py
Çıktı: topopt_bagimsiz_dogrulama.json (+ .png)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
from stress_topopt3d import StressTopo3D  # noqa: E402

L = 1.0                 # fiziksel kenar (x ve y), z kalınlığı = L·NZ/N
VF = 0.40
RMIN_FIZ = 2.0 / 24     # filtre yarıçapı FİZİKSEL — grid değişince eleman cinsinden ölçeklenir
TO_GRIDLERI = ((16, 2), (24, 3))
ORTAK = (48, 6)         # her iki TO gridinin tam katı → tasarımlar KAYIPSIZ eşlenir
INCELTME = (1, 2, 3)


def _c_olcek(n: int) -> float:
    return n / L


def _s_olcek(n: int) -> float:
    return (n / L) ** 2


# ── ölçek dönüşümünün kendisi ölçülür (varsayılmaz) ─────────────────────────

def olcek_dogrulama() -> dict:
    """Tam-dolu ankastre kiriş: ölçekli kompliyans N ile YAKINSAMALI."""
    kayit = []
    for n in (6, 9, 12):
        nx, ny, nz = 2 * n, n, n
        fixed = []
        for k in range(nz + 1):
            for j in range(ny + 1):
                nid = k * (nx + 1) * (ny + 1) + j * (nx + 1)
                fixed += [3 * nid, 3 * nid + 1, 3 * nid + 2]
        yuk_d, yuk_v = [], []
        uc = [(j, k) for k in range(nz + 1) for j in range(ny + 1)]
        for j, k in uc:
            nid = k * (nx + 1) * (ny + 1) + j * (nx + 1) + nx
            yuk_d.append(3 * nid + 1)
            yuk_v.append(-1.0 / len(uc))
        t = StressTopo3D(nx, ny, nz, fixed, yuk_d, yuk_v, rmin=1.1)
        rho = np.ones(t.ne)
        u, _ = t.solve(rho)
        c, _ = t.compliance(rho, u)
        kayit.append({"n": n, "ndof": t.ndof, "c_birim": float(c),
                      "c_fiz": float(c) * _c_olcek(n)})
    sapma = abs(kayit[-1]["c_fiz"] - kayit[-2]["c_fiz"]) / kayit[-2]["c_fiz"] * 100
    ilk_son = abs(kayit[-1]["c_fiz"] - kayit[0]["c_fiz"]) / kayit[0]["c_fiz"] * 100
    return {"seviyeler": kayit, "son_iki_sapma_pct": round(sapma, 2),
            "ilk_son_sapma_pct": round(ilk_son, 2),
            "gecti": sapma < 8.0,
            "_anlam": ("Ölçekli kompliyans ağ inceldikçe sabitleniyorsa c_fiz=(N/L)·c_birim "
                       "dönüşümü doğrudur; yanlış olsaydı N ile monoton ıraksardı.")}


# ── L-braket: fiziksel konumlarla, herhangi bir çözünürlükte ────────────────

def braket(n: int, nz: int, rmin_el: float | None = None) -> tuple[StressTopo3D, np.ndarray]:
    h = n // 2

    def nid(i, j, k):
        return k * (n + 1) * (n + 1) + j * (n + 1) + i

    def eid(i, j, k):
        return k * n * n + j * n + i

    pasif = np.zeros(n * n * nz, bool)
    for k in range(nz):
        for j in range(h, n):
            for i in range(h, n):
                pasif[eid(i, j, k)] = True

    fixed = []
    for k in range(nz + 1):
        for i in range(h + 1):
            d = nid(i, n, k)
            fixed += [3 * d, 3 * d + 1, 3 * d + 2]

    # Yük TEK DÜĞÜMDE DEĞİL: nokta-yük kendi başına gerilme tekilliği üretir ve
    # ağ inceldikçe patlar; o zaman ölçülen "tekillik" hangi kaynaktan geldiği
    # ayrışmazdı. Yük, sağ kol ucunda SABİT FİZİKSEL bir şeride yayılır.
    serit = max(1, round(n * 0.125))
    dugumler = [(j, k) for k in range(nz + 1) for j in range(h - serit, h + 1)]
    yuk_d = [3 * nid(n, j, k) + 1 for j, k in dugumler]
    yuk_v = [-1.0 / len(dugumler)] * len(dugumler)

    t = StressTopo3D(n, n, nz, fixed, yuk_d, yuk_v, rmin=rmin_el or RMIN_FIZ * n,
                     pnorm=12.0, passive_void=pasif)
    return t, pasif


def buyut(rho: np.ndarray, n: int, nz: int, r: int) -> np.ndarray:
    """Tasarımı r kat ince gride KAYIPSIZ taşı (eleman bölünmesi — geometri aynı)."""
    a = rho.reshape(nz, n, n)
    return np.repeat(np.repeat(np.repeat(a, r, 0), r, 1), r, 2).ravel()


def esikle(rho: np.ndarray, pasif: np.ndarray, emin: float) -> np.ndarray:
    """HACİM-KORUYAN eşik: ikili tasarımın hacmi gri tasarımınkiyle aynı."""
    aktif = ~pasif
    hedef = float(rho[aktif].sum())
    sirali = np.sort(rho[aktif])[::-1]
    k = int(round(hedef))
    esik = sirali[min(k, len(sirali) - 1)]
    ikili = np.where(rho > esik, 1.0, emin)
    ikili[pasif] = emin
    return ikili


def olc(t: StressTopo3D, rho: np.ndarray, n: int) -> dict:
    u, _ = t.solve(rho)
    c, _ = t.compliance(rho, u)
    _, vm = t.elem_stress(u)
    kati = rho > 0.5
    # TEPE GERILME YALNIZ KATI ELEMANLARDA anlamlidir: bos elemanin (emin)
    # gerilmesi fiziksel degildir, sayisal artiktir.
    tepe = float(vm[kati].max()) if kati.any() else float("nan")
    return {"c_fiz": float(c) * _c_olcek(n),
            "sigma_tepe_fiz": tepe * _s_olcek(n),
            "hacim_fraksiyonu": float(kati.mean()), "ndof": t.ndof, "ne": t.ne}


def calistir() -> dict:
    t0 = time.time()
    olcek = olcek_dogrulama()
    print(f"Ölçek doğrulaması: son-iki sapma %{olcek['son_iki_sapma_pct']} "
          f"→ {'GEÇTİ' if olcek['gecti'] else 'KALDI'}", flush=True)

    tasarimlar = {}
    for n, nz in TO_GRIDLERI:
        t, pasif = braket(n, nz)
        rho_c, _ = t.optimize(VF, "compliance", max_iter=50)
        rho_s, _ = t.optimize(VF, "stress", max_iter=60, move=0.15, x0=rho_c)
        ikili = esikle(rho_s, pasif, t.emin)
        tasarimlar[(n, nz)] = {"t": t, "pasif": pasif, "gri": rho_s, "ikili": ikili}
        print(f"TO {n}x{n}x{nz} bitti (ndof={t.ndof}, {time.time() - t0:.0f}s)", flush=True)

    # 1. ESIKLEME HATASI — ayni grid, ayni hacim, gri vs ikili
    esik_hatasi = {}
    for (n, nz), d in tasarimlar.items():
        g = olc(d["t"], d["gri"], n)
        b = olc(d["t"], d["ikili"], n)
        esik_hatasi[f"{n}x{n}x{nz}"] = {
            "gri": g, "ikili": b,
            "sigma_degisim_pct": round((b["sigma_tepe_fiz"] / g["sigma_tepe_fiz"] - 1) * 100, 2),
            "c_degisim_pct": round((b["c_fiz"] / g["c_fiz"] - 1) * 100, 2)}

    # 2. AYRIKLASTIRMA — AYNI ikili tasarim, giderek incelen BAGIMSIZ grid
    n0, nz0 = TO_GRIDLERI[-1]
    ikili0 = tasarimlar[(n0, nz0)]["ikili"]
    seviyeler = []
    for r in INCELTME:
        tf, _ = braket(n0 * r, nz0 * r, rmin_el=1.1)
        m = olc(tf, buyut(ikili0, n0, nz0, r), n0 * r)
        m["r"] = r
        m["grid"] = f"{n0 * r}x{n0 * r}x{nz0 * r}"
        seviyeler.append(m)
        print(f"  yeniden-analiz r={r} ({m['grid']}): c={m['c_fiz']:.4g}, "
              f"σ={m['sigma_tepe_fiz']:.4g} ({time.time() - t0:.0f}s)", flush=True)

    c_sap = abs(seviyeler[-1]["c_fiz"] / seviyeler[-2]["c_fiz"] - 1) * 100
    s_sap = abs(seviyeler[-1]["sigma_tepe_fiz"] / seviyeler[-2]["sigma_tepe_fiz"] - 1) * 100
    s_toplam = (seviyeler[-1]["sigma_tepe_fiz"] / seviyeler[0]["sigma_tepe_fiz"] - 1) * 100

    # 3. OPTIMUMUN AG-BAGIMLILIGI — iki tasarim ORTAK ince gridde
    no, nzo = ORTAK
    tort, _ = braket(no, nzo, rmin_el=1.1)
    ortak = {}
    for (n, nz), d in tasarimlar.items():
        r = no // n
        ortak[f"{n}x{n}x{nz}"] = olc(tort, buyut(d["ikili"], n, nz, r), no)
        print(f"  ortak grid değerlendirme {n}→{no}: "
              f"c={ortak[f'{n}x{n}x{nz}']['c_fiz']:.4g}", flush=True)
    adlar = list(ortak)
    c1, c2 = (ortak[a]["c_fiz"] for a in adlar)
    s1, s2 = (ortak[a]["sigma_tepe_fiz"] for a in adlar)

    rec = {
        "vaka": "Topoloji optimizasyonu — optimizasyon sonrası BAĞIMSIZ yeniden-analiz",
        "_neden": ("TO'nun raporladigi tepe gerilme, optimizasyonun KENDI gridinde ve "
                   "KENDI gri alani uzerinde hesaplanir. Imal edilecek parca ikilidir ve "
                   "analiz agi baskadir. Ayni agla dogrulamak DAIRESELDIR."),
        "olcek_dogrulamasi": olcek,
        "kurulum": {"vaka": "3B L-braket", "volfrac": VF,
                    "rmin_fiziksel": RMIN_FIZ,
                    "to_gridleri": [f"{n}x{n}x{nz}" for n, nz in TO_GRIDLERI],
                    "ortak_degerlendirme_gridi": f"{no}x{no}x{nzo}",
                    "esik": "HACİM-KORUYAN (gri ile ikili aynı hacim)"},
        "1_esikleme_hatasi": esik_hatasi,
        "2_ayriklastirma": {
            "tasarim": f"{n0}x{n0}x{nz0} gerilme-min, ikili",
            "seviyeler": seviyeler,
            "kompliyans_son_iki_sapma_pct": round(c_sap, 2),
            "sigma_son_iki_sapma_pct": round(s_sap, 2),
            "sigma_r1_r3_degisim_pct": round(s_toplam, 1),
        },
        "3_optimum_ag_bagimliligi": {
            "ortak_gridde": ortak,
            "kompliyans_farki_pct": round((c2 / c1 - 1) * 100, 2),
            "sigma_tepe_farki_pct": round((s2 / s1 - 1) * 100, 2),
        },
        "_uretim": "Üretim: python experiments/topopt_bagimsiz_dogrulama.py",
    }

    tekil = s_sap > 3 * max(c_sap, 0.1) and abs(s_toplam) > 10
    rec["verdikt"] = (
        f"Eşikleme (gri→ikili, {n0} grid): σ_tepe %"
        f"{esik_hatasi[f'{n0}x{n0}x{nz0}']['sigma_degisim_pct']:+.1f}, "
        f"c %{esik_hatasi[f'{n0}x{n0}x{nz0}']['c_degisim_pct']:+.1f}. "
        f"Bağımsız yeniden-analiz (r=1→3): kompliyans son-iki sapma %{c_sap:.1f} "
        f"(YAKINSIYOR), tepe gerilme %{s_toplam:+.0f} ve son-iki sapma %{s_sap:.1f} — "
        + ("YAKINSAMIYOR (reentrant köşe gerilme tekilliği; tepe σ ağ-bağımlıdır ve "
           "mutlak bir kabul ölçütü olarak KULLANILAMAZ)."
           if tekil else
           "sınırlı değişim (bu kurulumda tekillik baskın çıkmadı).")
        + f" Optimumun ağ-bağımlılığı: {adlar[0]} vs {adlar[1]} tasarımları ortak "
          f"{no} gridinde kompliyansta %{(c2 / c1 - 1) * 100:+.1f} ayrışıyor.")
    rec["_kisit"] = (
        "Bu bir DOGRULAMA (verification) olcumudur, validasyon degil: deneysel "
        "referans yok. Ikili tasarim eleman-bolunmesiyle tasindigi icin geometri "
        "KAYIPSIZ korunur; yani olculen fark yalnizca ayriklastirmadandir "
        "(yeniden-mesh'in geometri yaklasimi karismaz). Merdiven-basamakli sinir "
        "gercek imalattaki yuvarlatmayi temsil etmez — gercek parcada tepe gerilme "
        "filet yaricapina baglidir ve bu betik onu OLCMEZ.")
    return rec, tasarimlar


def _figur(rec: dict, tasarimlar: dict) -> Path:
    fig, ax = plt.subplots(1, 3, figsize=(11, 3.4))
    (n0, nz0) = TO_GRIDLERI[-1]
    d = tasarimlar[(n0, nz0)]
    kmid = nz0 // 2
    pv = d["pasif"].reshape(nz0, n0, n0)[kmid]
    for a, alan, ttl in ((ax[0], d["gri"], "TO çıktısı (gri, SIMP)"),
                         (ax[1], d["ikili"], "eşiklenmiş (ikili, imal edilebilir)")):
        a.imshow(np.ma.masked_where(pv, alan.reshape(nz0, n0, n0)[kmid]),
                 cmap="gray_r", origin="lower", vmin=0, vmax=1)
        a.set_title(ttl, fontsize=9)
        a.axis("off")

    s = rec["2_ayriklastirma"]["seviyeler"]
    r = [x["r"] for x in s]
    ax[2].plot(r, [x["c_fiz"] / s[0]["c_fiz"] for x in s], "o-",
               color="#1f4e79", label="kompliyans")
    ax[2].plot(r, [x["sigma_tepe_fiz"] / s[0]["sigma_tepe_fiz"] for x in s], "s-",
               color="#a00000", label="tepe von Mises")
    ax[2].axhline(1.0, ls=":", color="gray", lw=1)
    ax[2].set_xticks(r)
    ax[2].set_xlabel("bağımsız analiz gridi inceltme katı")
    ax[2].set_ylabel("r=1'e göre oran")
    ax[2].set_title("Aynı ikili tasarım, incelen ağ", fontsize=9)
    ax[2].legend(fontsize=8)
    ax[2].grid(alpha=0.3)
    fig.suptitle("TO sonrası bağımsız yeniden-analiz — kompliyans yakınsar, "
                 "tepe gerilme tekilliğe koşar", fontsize=10)
    fig.tight_layout()
    p = KOK / "topopt_bagimsiz_dogrulama.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec, tasarimlar = calistir()
    _figur(rec, tasarimlar)
    (KOK / "topopt_bagimsiz_dogrulama.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + rec["verdikt"])
    print("-> topopt_bagimsiz_dogrulama.json, .png")
    return 0 if rec["olcek_dogrulamasi"]["gecti"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
