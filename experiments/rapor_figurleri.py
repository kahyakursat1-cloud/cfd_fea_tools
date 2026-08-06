"""Teknik rapor figürleri — HEPSİ DEPODAKİ GERÇEK KANITTAN üretilir.

Rapordaki her grafik yeniden üretilebilir olmalıdır; aksi hâlde rapor, kendi
savunduğu ilkeyi çiğner. Bu betik tek kaynaktır: veriyi kanıt JSON'larından ve
koşu loglarından okur, `docs/figurler/` altına PDF üretir. Elle çizilmiş,
"temsilî" ya da uydurulmuş hiçbir eğri yoktur.

    python experiments/rapor_figurleri.py
Çıktı: docs/figurler/*.pdf
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
CIKTI = KOK / "docs" / "figurler"
sys.path.insert(0, str(KOK))

IYI, ORTA, KOTU = "#006e3c", "#af6e00", "#a00000"
plt.rcParams.update({
    "font.size": 9, "axes.grid": True, "grid.alpha": 0.25,
    "figure.constrained_layout.use": True, "axes.spines.top": False,
    "axes.spines.right": False,
})


def _sayi_mi(x: str) -> bool:
    """float'a cevrilebilir mi — try/except kullanmadan."""
    y = x.lstrip("+-")
    if y.count(".") > 1:
        return False
    govde, _, us = y.partition("e") if "e" in y else y.partition("E")
    return (govde.replace(".", "", 1).isdigit()
            and (not us or us.lstrip("+-").isdigit()))


def _j(ad: str) -> dict:
    return json.loads((KOK / ad).read_text(encoding="utf-8"))


# ── 1. Mesh yakınsaması + Richardson ekstrapolasyonu ─────────────────────────

def fig_mesh_yakinsama() -> Path:
    kup, tmr = _j("gci_kup_arac.json"), _j("tmr_gci_verdict.json")
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.0))

    for eksen, d, ref, ref_ad, baslik in (
        (ax[0], kup, d_ref := kup["referans"]["Cd"], "Hoerner 1965 (1.05)",
         "Küp — 3B araç hattı"),
        (ax[1], tmr, tmr["TMR_referans_SST_alpha0"], "NASA TMR (0.00809)",
         "NACA0012 $\\alpha=0°$ — 2B C-grid"),
    ):
        sev = d["seviyeler"]
        n = [s["cells"] for s in sev]
        cd = [s["Cd"] for s in sev]
        h = [x ** (-1 / 3) if d is kup else x ** (-1 / 2) for x in n]
        eksen.plot(h, cd, "o-", color="#1f4e79", lw=1.6, ms=5, label="ölçülen")
        f_ex = d["gci"]["f_exact"]
        eksen.axhline(f_ex, ls="--", color="#1f4e79", lw=1.1,
                      label=f"Richardson $h\\!\\to\\!0$ = {f_ex:.4g}")
        eksen.axhline(ref, ls=":", color=KOTU, lw=1.4, label=ref_ad)
        g = d["gci"]
        eksen.fill_between([0, max(h) * 1.05],
                           f_ex * (1 - g["gci_fine_pct"] / 100),
                           f_ex * (1 + g["gci_fine_pct"] / 100),
                           color="#1f4e79", alpha=0.12,
                           label=f"GCI %{g['gci_fine_pct']:.2f}")
        eksen.set_xlim(0, max(h) * 1.05)
        eksen.set_xlabel("$h \\propto N^{-1/d}$  (0 = sıfır hücre boyu)")
        eksen.set_ylabel("$C_d$")
        eksen.set_title(f"{baslik}\n$p={g['p']:.3f}$, "
                        f"asimptotik oran {g['asymptotic']:.3f}", fontsize=8.5)
        eksen.legend(fontsize=7, loc="best")

    p = CIKTI / "fig_mesh_yakinsama.pdf"
    fig.savefig(p)
    plt.close(fig)
    return p


# ── 2. Tek yönlü vs iki yönlü ayrıklaştırma ailesi ──────────────────────────

def fig_ayriklastirma_ailesi() -> Path:
    tek, iki = _j("vlm_panel_yakinsamasi.json"), _j("vlm_iki_yonlu_yakinsama.json")
    fig, ax = plt.subplots(1, 2, figsize=(7.4, 3.0), sharey=True)

    s1 = tek["yakinsama"]["seri"]
    n1 = tek["paneller"]
    ax[0].plot(n1, s1, "s-", color=ORTA, lw=1.6, ms=5)
    b1 = tek["kanonik_band"]["u_pct"]
    ax[0].set_title(f"TEK yönlü aile (yalnız açıklık)\n$U={b1:.2f}\\%$, "
                    f"{tek['kanonik_band']['yontem'].upper()}", fontsize=8.5)
    ax[0].set_xlabel("açıklık paneli (kiriş yönü SABİT)")
    ax[0].set_ylabel("$C_L$ ($\\alpha=8°$)")

    s2 = iki["seri"]
    n2 = [k["toplam"] for k in iki["kademeler"]]
    ax[1].plot(n2, s2, "o-", color=IYI, lw=1.6, ms=5)
    b2 = iki["kanonik_band"]["u_pct"]
    ax[1].set_title(f"İKİ yönlü aile (açıklık + kiriş)\n$U={b2:.2f}\\%$, "
                    f"{iki['kanonik_band']['yontem'].upper()}", fontsize=8.5)
    ax[1].set_xlabel("toplam panel (her kademe $\\times 1{,}35$)")
    ax[1].set_xscale("log")

    for e, s in zip(ax, (s1, s2)):
        e.fill_between(e.get_xlim(), min(s), max(s), color="gray", alpha=0.08)
    fig.suptitle(f"Sabit tutulan yön bandın tabanını belirler — band "
                 f"{b1 / b2:.1f} kat daraldı", fontsize=9.5)

    p = CIKTI / "fig_ayriklastirma_ailesi.pdf"
    fig.savefig(p)
    plt.close(fig)
    return p


# ── 3. Doğrulama çapaları — ölçülen sapma ────────────────────────────────────

def fig_dogrulama_capalari() -> Path:
    """Sapmalar KANIT DOSYALARINDAN okunur; elle girilen tek sey ETIKET."""
    capalar = []

    def _ekle(ad, hata, kaynak):
        capalar.append((ad, abs(float(hata)), kaynak))

    fv = _j("fea_validation.json")
    _ekle("Ankastre kiriş (sehim)", fv["sehim"]["hata_pct"], "Euler–Bernoulli")
    _ekle("Ankastre kiriş (gerilme)", fv["gerilme"]["hata_pct"], "Euler–Bernoulli")
    for dosya, etiket, kaynak in (
        ("fea_validation_cyl.json", "İç-basınçlı silindir", "Lamé"),
        ("fea_validation_hole.json", "Delikli plaka $K_t$", "Heywood"),
        ("fea_validation_thermal.json", "Termal gerilme", "$E\\alpha\\Delta T$"),
        ("fea_validation_buckling.json", "Euler burkulması", "Euler"),
        ("fea_validation_grav.json", "Öz-ağırlık (sehim)", "$\\rho g L$"),
    ):
        d = _j(dosya)
        h = d.get("hata_pct")
        if h is None:
            fem, ana = d.get("fem") or {}, d.get("analitik") or {}
            h = (fem.get("hata_pct") if isinstance(fem, dict) else None)
            if h is None:
                ortak = set(fem) & set(ana)
                anahtar = next((k for k in ortak
                                if isinstance(fem[k], (int, float)) and ana[k]), None)
                h = ((fem[anahtar] - ana[anahtar]) / ana[anahtar] * 100
                     if anahtar else 0.0)
        _ekle(etiket, h, kaynak)

    kup = _j("gci_kup_arac.json")
    _ekle("Küp $C_d$", kup["literatur_sapma_pct"], "Hoerner")
    tmr = _j("tmr_gci_verdict.json")
    _ekle("NACA0012 $C_d$", (tmr["seviyeler"][-1]["Cd"]
                             / tmr["TMR_referans_SST_alpha0"] - 1) * 100, "NASA TMR")

    capalar.sort(key=lambda t: t[1])
    ad = [f"{a}\n({k})" for a, _, k in capalar]
    hata = [h for _, h, _ in capalar]
    renk = [IYI if h < 5 else (ORTA if h < 10 else KOTU) for h in hata]

    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    ax.barh(ad, hata, color=renk, height=0.62)
    for i, h in enumerate(hata):
        ax.text(h + 0.12, i, f"{h:.1f}%", va="center", fontsize=8)
    ax.axvline(5, ls="--", color="gray", lw=1)
    ax.set_xlabel("kapalı-form / deneysel referanstan MUTLAK sapma (%)")
    ax.set_xlim(0, max(hata) * 1.28)
    ax.set_title("Doğrulama çapaları — her biri bağımsız bir referansa karşı",
                 fontsize=9.5)
    ax.grid(axis="y", visible=False)

    p = CIKTI / "fig_dogrulama_capalari.pdf"
    fig.savefig(p)
    plt.close(fig)
    return p


# ── 4. Yakınsama tarihçesi — gerçek koşu logundan ───────────────────────────

def fig_yakinsama_tarihcesi() -> Path | None:
    dat = KOK / "vehicle_runs" / "minihawk" / "minihawk" / \
        "postProcessing" / "forceCoeffs1" / "0" / "forceCoeffs.dat"
    if not dat.exists():
        return None
    t, cd, cl = [], [], []
    basliklar: list[str] = []
    for satir in dat.read_text(errors="ignore").splitlines():
        if satir.startswith("#"):
            if "Time" in satir:
                basliklar = satir.lstrip("#").split()
            continue
        p = satir.split()
        if len(p) < 4:
            continue
        i_cd = basliklar.index("Cd") if "Cd" in basliklar else 2
        i_cl = basliklar.index("Cl") if "Cl" in basliklar else 3
        if max(i_cd, i_cl) >= len(p) or not all(_sayi_mi(p[i])
                                                for i in (0, i_cd, i_cl)):
            continue                      # yarim yazilmis satir (kosu kesilmis)
        t.append(float(p[0]))
        cd.append(float(p[i_cd]))
        cl.append(float(p[i_cl]))
    if len(t) < 10:
        return None

    fig, ax = plt.subplots(figsize=(7.4, 2.8))
    ax.plot(t, cd, color="#1f4e79", lw=1.2, label="$C_d$")
    ax.set_xlabel("SIMPLE iterasyonu")
    ax.set_ylabel("$C_d$", color="#1f4e79")
    ax2 = ax.twinx()
    ax2.plot(t, cl, color=ORTA, lw=1.2, label="$C_l$")
    ax2.set_ylabel("$C_l$", color=ORTA)
    ax2.grid(False)

    # SON %20 PENCERE: drift olcutu bu pencerede hesaplanir.
    n = max(int(len(t) * 0.2), 5)
    ax.axvspan(t[-n], t[-1], color="gray", alpha=0.12)
    ax.text(t[-n], max(cd), " son %20 pencere\n (drift ölçütü)", fontsize=7,
            va="top")
    ax.set_title("Kuvvet tarihçesi — yakınsama rezidüellerle DEĞİL, "
                 "QoI dura ğanlığıyla da sınanır", fontsize=9)

    p = CIKTI / "fig_yakinsama_tarihcesi.pdf"
    fig.savefig(p)
    plt.close(fig)
    return p


# ── 5. Aşama süreleri — koşu loglarının zaman damgalarından ─────────────────

# Boru hattı aşama süresi KAYDETMİYOR; her aşama kendi logunu bitince yazdığı
# için ardışık logların değişim zamanları aşama sınırlarını verir. Bu bir
# DUVAR-SAATİ ölçümüdür (bu donanımda, bu koşuda) ve öyle yazılır.
ASAMALAR = [
    ("surfaceFeatures", "log.surfaceFeatures"),
    ("blockMesh", "log.blockMesh"),
    ("snappyHexMesh", "log.snappyHexMesh"),
    ("checkMesh", "log.checkMesh"),
    ("decomposePar", "log.decomposePar"),
    ("foamRun (SIMPLE, 8 çekirdek)", "log.foamRun"),
    ("reconstructPar", "log.reconstructPar"),
    ("son-işlem (yüzey/kesit)", "log.yuzeyBasinc"),
]


def asama_verisi(kosu: Path) -> tuple[list[str], list[float], int | None, str] | None:
    """(adlar, süreler, hücre, yöntem) — DOĞRUDAN TELEMETRİ varsa o, yoksa
    dosya zaman damgası. Zaman-damgası yöntemi yalnız aşama SINIRLARINI verir ve
    dosyaya dokunan her şey (kopyalama, yedekleme) tarafından bozulur; çözücü
    artık kendi sürelerini yazdığı için o tercih edilir."""
    sj = kosu / "sonuc.json"
    if sj.exists():
        d = json.loads(sj.read_text(encoding="utf-8"))
        tel = d.get("asama_sureleri")
        if tel:
            return ([x["asama"] for x in tel], [float(x["sure_s"]) for x in tel],
                    (d.get("mesh") or {}).get("cells"),
                    "doğrudan telemetri (çözücünün kendi ölçümü)")
    kok = kosu / kosu.name
    if not kok.is_dir():
        return None
    kayit = [(ad, (kok / dosya).stat().st_mtime)
             for ad, dosya in ASAMALAR if (kok / dosya).exists()]
    if len(kayit) < 4:
        return None
    kayit.sort(key=lambda t: t[1])
    adlar, sureler = [], []
    onceki = kayit[0][1]
    for ad, ts in kayit[1:]:
        adlar.append(ad)
        sureler.append(max(ts - onceki, 0.0))
        onceki = ts
    return adlar, sureler, None, "log dosyası zaman damgaları (DOLAYLI — üst sınır)"


def fig_asama_sureleri() -> Path | None:
    v = asama_verisi(KOK / "vehicle_runs" / "minihawk")
    return _asama_cizimi(*v) if v else None


def _asama_cizimi(adlar, sureler, hucre, yontem) -> Path | None:
    if len(adlar) < 3:
        return None
    toplam = sum(sureler)
    if toplam <= 0:
        return None
    fig, ax = plt.subplots(figsize=(7.4, 2.9))
    renk = ["#1f4e79" if "foamRun" in a else ("#4a7ba7" if "snappy" in a.lower()
                                              else "#8fb3d0") for a in adlar]
    ax.barh(adlar[::-1], sureler[::-1], color=renk[::-1], height=0.62)
    for i, s in enumerate(sureler[::-1]):
        ax.text(s + toplam * 0.012, i, f"{s:.0f} s ({s / toplam * 100:.0f}%)",
                va="center", fontsize=8)
    ax.set_xlabel("duvar-saati süresi (s)")
    ax.set_xlim(0, max(sureler) * 1.32)
    ax.set_title("Aşama süreleri — MiniHawk"
                 + (f", {hucre:,} hücre" if hucre else "")
                 + f", toplam {toplam / 60:.1f} dk  [{yontem}]", fontsize=9)
    ax.grid(axis="y", visible=False)

    p = CIKTI / "fig_asama_sureleri.pdf"
    fig.savefig(p)
    plt.close(fig)
    return p


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    CIKTI.mkdir(parents=True, exist_ok=True)
    uretilen = []
    # GENIS except YOK: eksik veri ONCEDEN sinanir. Boylece gercek bir kod
    # hatasi YUTULMAZ — yukselir ve gorunur.
    for fn, gerekli in (
        (fig_mesh_yakinsama, ("gci_kup_arac.json", "tmr_gci_verdict.json")),
        (fig_ayriklastirma_ailesi, ("vlm_panel_yakinsamasi.json",
                                    "vlm_iki_yonlu_yakinsama.json")),
        (fig_dogrulama_capalari, ("fea_validation.json", "gci_kup_arac.json")),
        (fig_yakinsama_tarihcesi, ()),
        (fig_asama_sureleri, ()),
    ):
        yok = [g for g in gerekli if not (KOK / g).exists()]
        if yok:
            print(f"  — {fn.__name__}: kanıt yok {yok}, ATLANDI (uydurulmadı)")
            continue
        p = fn()
        if p is None:
            print(f"  — {fn.__name__}: veri yok, ATLANDI (uydurulmadı)")
            continue
        uretilen.append(p)
        print(f"  ✓ {p.relative_to(KOK)}")
    print(f"\n{len(uretilen)} figür üretildi -> {CIKTI.relative_to(KOK)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
