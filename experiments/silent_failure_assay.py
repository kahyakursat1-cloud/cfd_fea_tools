"""Silent-failure assay — guard katmanını koşu-geçerliliğinin İKİLİ DETEKTÖRÜ olarak
nicelleştir (Paper 1 özgünlük yükseltme, Path A). Detection-theory: her (vaka, knob)
hücresi {silent-failure var/yok} × {guard flag attı/atmadı} → TP/FP/TN/FN →
sensitivity / specificity / prevalence, ve τ taranarak mini-ROC.

PILOT: korpus, aracın ZATEN ürettiği gerçek V&V çıktılarından tohumlandı (fea_validation_*.json,
tmr_gci_verdict*.json, gci_airfoil, supersonic_validation + oturum sonuçları) — sıfır yeni compute.
Tam sistematik tarama (knob-uzayı + bırak-bir-vaka CV) sonraki faz (solver matrisi).

Kullanım: python experiments/silent_failure_assay.py [--tau 0.05]
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# (vaka, knob, nicelik, naive_out, truth, guard_flagged, guard_class, kaynak)
# guard_flagged = guard "design-grade" SERTİFİKASI VERMEDİ mi (trend/out-of-envelope/GCI-withheld)?
# truth = bilinen referans (closed-form / Ladson / TMR-CFL3D / Charters–Thomas / OpenRocket).
def _c(case, knob, q, naive, truth, flagged, gclass, src):
    return {"case": case, "knob": knob, "q": q, "naive": naive, "truth": truth,
            "flagged": flagged, "gclass": gclass, "src": src}


CORPUS = [
    # ── FEA closed-form (truth = analitik) ──
    _c("cantilever", "C3D8I, 24x4x4", "deflection", 9.051, 9.143, False, "design", "fea_validation.json"),
    _c("cantilever", "C3D8I", "stress", 49.8, 48.0, False, "design", "fea_validation.json"),
    _c("thick-cylinder", "C3D10 consistent-load (FIX)", "hoop", 21.31, 21.03, False, "design", "fea_validation_cyl.json"),
    _c("thick-cylinder", "corner-lumping (DEFECT)", "hoop", 22.55, 21.03, True, "verification-caught", "paper §3 / Lamé"),
    _c("plate-hole", "C3D10 gmsh", "Kt-stress", 159.7, 157.0, False, "design", "fea_validation_hole.json"),
    _c("buckling", "*BUCKLE C3D10", "P_cr", 9227.4, 9211.6, False, "design", "fea_validation_buckling.json"),
    _c("plate-hole-GCI", "3-mesh non-monotonic", "peak-vM", 159.4, 157.0, True, "trend(GCI-withheld)", "fea_stress_gci.json"),
    # ── CFD airfoil (truth = Ladson / TMR-CFL3D) ──
    _c("naca0012-drag", "bespoke O-grid (non-asymptotic)", "Cd", 0.0131, 0.00890, True, "trend(p~0.2)", "gci_airfoil.json"),
    _c("naca0012-drag", "TMR grids a=0 (asymptotic)", "Cd", 0.00837, 0.00809, False, "design(GCI1.71%)", "tmr_gci_verdict.json"),
    _c("naca0012-lift", "a=10 residual-stopped", "Cl", 1.031, 1.078, True, "trend(not-force-conv)", "oturum/tmr a=10"),
    _c("naca0012-lift", "a=10 force-plateau", "Cl", 1.0644, 1.078, True, "trend(GCI-withheld)", "tmr_gci_verdict_a10.json"),
    _c("naca0012-lift", "a=12 stall (2D RANS)", "Cl", 0.82, 1.49, True, "out-of-envelope", "transition_results / Ladson"),
    # ── Süpersonik (truth = Charters–Thomas / OpenRocket) ──
    _c("sphere-M2", "shockFluid inviscid", "Cd", 1.135, 1.00, True, "trend(inviscid~15%)", "supersonic_validation.json"),
    _c("rocket-finned", "blunt-box fins (geometry)", "Cd", 1.007, 0.617, False, "design(no-guard)", "oturum rocket-fin/OpenRocket"),
    # ── FEA element-order × mesh taraması (truth = Lamé 21.03; flagged = watchdog>2.5) ──
    # ── CFD mesh-density × AoA taraması (truth = Ladson; drag flagged=trend no-GCI-band,
    #    lift attached α≤8 → validity_envelope DESIGN, mesh-bağımsız) ──
    # a4 fine (force_gentle ile yakınsadı): O-grid NON-MONOTONIK — fine mid'den KÖTÜ.
    # Cd flagged (trend); Cl design(attached)→guard mesh-kontrol etmiyor → FN (kör-nokta).
]


# ── Tarama dosyalarindan URETILEN hucreler ────────────────────────────────────
# Degerler ELLE YAZILMAZ. Izgara genisledikce korpus kendiliginden buyur; aksi
# halde `src: ...jsonl` diyen bir hucre dosyayla ayrisir ve kimse fark etmez.
ALPHA_VALID_DEG = 8.0      # validity_envelope ile AYNI; bagli-akis zarfi
WATCHDOG_ESIGI = 2.5       # tek-ag gerilme bekcisi
MACH_SWEEP = 0.15          # taramanin kosuldugu ses-alti rejim (V=50 m/s)


def _jsonl(ad: str) -> list[dict]:
    f = ROOT / ad
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def _fea_hucreleri() -> list[dict]:
    """fea_knob_sweep.jsonl -> assay hucreleri (eleman-mertebesi x ag yogunlugu)."""
    out = []
    for d in _jsonl("fea_knob_sweep.jsonl"):
        wd = d.get("watchdog_ratio")
        flagged = wd is not None and wd > WATCHDOG_ESIGI
        out.append(_c("cyl-Lame", d["label"], "stress", d["peak_vM_MPa"],
                      d["truth_MPa"], flagged,
                      f"{'trend' if flagged else 'design'}(wd{wd})",
                      "fea_knob_sweep.jsonl"))
    return out


def _cfd_hucreleri() -> list[dict]:
    """cfd_mesh_sweep.jsonl -> assay hucreleri (Cl ve Cd ayri niceliklerdir).

    Cozucude DUSEN yapilandirmalar korpusa GIRMEZ: bir sessiz-hata dedektorunu
    hic sonuc uretmemis kosuyla sinamak anlamsizdir (sessiz hata, sayi UREtip
    uyarmamaktir). Dusen kosular ayrica sayilip raporlanir.
    """
    out = []
    for d in _jsonl("cfd_mesh_sweep.jsonl"):
        if d.get("error") or d.get("Cd_sim") is None:
            continue
        a, yog = d["alpha"], d["density"]
        bagli = abs(a) <= ALPHA_VALID_DEG
        for q, sim, ref in (("Cd", d.get("Cd_sim"), d.get("Cd_ref")),
                            ("Cl", d.get("Cl_sim"), d.get("Cl_ref"))):
            # SIFIR REFERANS: simetrik profilde alpha=0'da Cl_ref = 0 ve bu DOGRU
            # bir referanstir, eksik veri degil. Ama BAGIL hata sifira karsi
            # TANIMSIZDIR, dolayisiyla hucre assay'e giremez. Onceki surum bunu
            # `if d.get("Cl_ref")` ile SESSIZCE atiyordu (0.0 falsy) -- dislama
            # artik gerekceli ve SAYILIYOR (_sifir_referans_sayisi).
            if ref is None or sim is None or ref == 0:
                continue
            flagged = True if q == "Cd" else (not bagli)
            sinif = ("trend(no-GCI)" if q == "Cd"
                     else ("design(attached)" if bagli else "out-of-envelope"))
            h = _c("naca-Ladson", f"a{a} {q} {yog}", q, sim, ref,
                   flagged, sinif, "cfd_mesh_sweep.jsonl")
            # HAM cozucu ciktisi hucrede TASINIR: duzeltme-sonrasi katman, guard
            # mantigini burada YENIDEN YAZMAK yerine SEVK EDILEN `classify_cfd`i
            # cagirarak yeniden hukum verir. Parafraz olculseydi, olculen sey
            # uygulamanin davranisi degil bu dosyanin davranisi olurdu.
            h["_ham"] = {"alpha": a, "mach": MACH_SWEEP, "Cl": d.get("Cl_sim"),
                         "Cd": d.get("Cd_sim"), "ag_yeterli": None}
            out.append(h)
    return out


def _sifir_referans_sayisi() -> int:
    """Referansi TAM SIFIR oldugu icin bagil-hata tanimsiz kalan hucre sayisi."""
    return sum(1 for d in _jsonl("cfd_mesh_sweep.jsonl")
               if not d.get("error") and d.get("Cl_ref") == 0)


def _dusen_kosu_sayisi() -> int:
    """Cozucude DUSEN AYIRT EDILIR yapilandirma sayisi (satir sayisi DEGIL).

    NEDEN AYIRT EDILIR: tarama yeniden baslatilabilir ve `_done_tags` yalnizca
    BASARILI kosulari "tamamlandi" sayar, dolayisiyla dusmus bir yapilandirma
    resume'da yeniden denenir ve dosyaya YENIDEN EKLENIR. Satir saymak, ayni
    yapilandirmanin iki denemesini iki basarisizlik gibi gosterir; makale ise
    (dogru olarak) yapilandirma sayiyor. Olculdu: 6 satir, 5 yapilandirma
    (alpha=0/xfine iki kez kayitli).
    """
    return len({(d["alpha"], d["density"]) for d in _jsonl("cfd_mesh_sweep.jsonl")
                if d.get("error")})


def _sonucsuz_kosu_sayisi() -> int:
    """Hata BILDIRMEDEN katsayi da uretmeyen kosular (Cd_sim is None).

    Ucuncu bir dislama sinifi ve daha once HIC sayilmiyordu: `_cfd_hucreleri`
    bunlari sessizce atliyordu. Cozucu dusmedi, kosu tamamlandi, ama kuvvet
    katsayisi okunamadi; bir sessiz-hata dedektorunu bunlarla sinamak da
    anlamsizdir, ama dislama GEREKCELI ve SAYILI olmalidir.
    """
    return sum(1 for d in _jsonl("cfd_mesh_sweep.jsonl")
               if not d.get("error") and d.get("Cd_sim") is None)


# FIZIKSEL OLARAK IMKANSIZ deger ureten kosular. Bunlar korpustan CIKARILMAZ --
# cikarmak, dedektorun en carpici basarisizligini gizlemek olurdu. Ama ayrica
# SAYILIR, cunku farkli bir kusur sinifina isaret ederler: kosu iraksamis, cozucu
# sayi uretmis ve tarama harness'i onu HATASIZ kaydetmis. Ornek: a8_mid,
# Cl=4769 ve Cd=293 (bir kanat profilinde |Cl| ~1,5'i gecmez).
#
# Bu ayni zamanda EKSIK BIR GUARD'a isaret eder: kuvvet katsayilarina fiziksel
# akla-yatkinlik siniri. Sinir VERIYE BAKILARAK secilmedi -- |Cl|>3 herhangi bir
# aerodinamikcinin onceden soyleyecegi bir imkansizliktir. Yine de bu kosunun
# DONDURULMUS-esik sonucuna geriye donuk katilmaz; gelecek is olarak raporlanir.
CL_FIZIKSEL_UST = 3.0


def _fiziksel_olmayan_hucreler() -> list[dict]:
    return [h for h in CORPUS
            if h["q"] == "Cl" and abs(h["naive"]) > CL_FIZIKSEL_UST]


CORPUS = CORPUS + _fea_hucreleri() + _cfd_hucreleri()

# Per-nicelik τ. ILKE (sonuca bakmadan sabitlendi): tolerans, o nicelik sinifinin
# KABUL EDILEN muhendislik sacilimini yansitir.
#   * Turetilmis gerilme (yer degistirme alaninin TUREVI — bir mertebe daha kaba): %10
#   * Birincil FE bilinmeyeni (yer degistirme, ozdeger — turev yok, en hizli yakinsar): %5
#   * Drag: DPW kod-arasi sacilimi ~%10-15 · Lift: Ladson deney bandi ~%5
#
# ONEMLI — bu sozluk TAM olmalidir. Onceki surumde `.get(q, tau)` yedegi vardi ve
# sozlukte OLMAYAN 6 nicelik (hoop, deflection, Kt-stress, P_cr, peak-vM) sessizce
# GLOBAL tau'ya (CLI varsayilani %5) dusuyordu. Sonuc: "niceliğe-özel" oldugu
# soylenen mansetin kendisi --tau bayraginin fonksiyonuydu (%5 -> 0,82/0,78;
# %10 -> 0,80/0,74) ve makalenin bas bulgusu olan tutarli-yuk defekti yalnizca o
# belgelenmemis yedek sayesinde TP sayiliyordu. Yedek KALDIRILDI: bilinmeyen
# nicelik artik sessizce varsayilana dusmez, hata firlatir.
TAU_BY_Q = {
    "Cd": 0.10, "Cl": 0.05,
    "stress": 0.10, "hoop": 0.10, "Kt-stress": 0.10, "peak-vM": 0.10,
    "deflection": 0.05, "P_cr": 0.05,
}


class BilinmeyenNicelik(KeyError):
    """Korpusta TAU_BY_Q'da karsiligi olmayan bir nicelik etiketi var."""


def duzeltilmis_flag(cell, kapilar=("fizik", "ag")) -> bool:
    """DÜZELTME-SONRASI guard katmanının aynı hücreye verdiği bayrak.

    Hücre ham çözücü çıktısını taşıyorsa hüküm SEVK EDİLEN `classify_cfd`'den
    alınır — guard mantığı burada yeniden yazılmaz. Taşımayan hücreler (kürate
    edilmiş vakalar, FEA) değişmez: iki yeni kapı da aerodinamik kuvvet
    katsayılarına ilişkindir ve FEA hücrelerine dokunmaz.

    `kapilar` iki kapıyı AYIRIR. İkisini birlikte açıp tek sayı vermek, farkın
    hangisinden geldiğini söylememek olurdu: ağ-yeterliliği kapısı her taşıma
    hücresine bayrak taktığı için fiziksel akla-yatkınlık kapısının katkısını
    tamamen GÖLGELER. Ayrı ölçüldüğünde her kapının kendi payı görünür.

    Bu sayılar DONDURULMUŞ-EŞİK SONUCUNA GİRMEZ. Doğrulayıcı değerlendirme eksik
    kapıları ortaya çıkardı, kapılar sonradan uygulandı; onları geriye dönük
    olarak dondurulmuş performansa saymak, doğrulayıcı testin bütün anlamını
    yok ederdi.
    """
    ham = cell.get("_ham")
    if ham is None:
        return cell["flagged"]
    from validity_envelope import REFERANS_AG_AILELERI, VALIDATED, classify_cfd
    # Kapatilan kapi ETKISIZ hale getirilir: fizik kapisi katsayi verilmeyince,
    # ag kapisi yeterlilik BEYAN EDILINCE sessizlesir. Beyan BEYAZ LISTEDEN
    # gelmeli -- ciplak `True` artik reddediliyor ve bu, ablasyonun fizik kolunu
    # sessizce ag koluyla ayni sonuca goturmustu (3 yerine 8 yeniden-siniflama).
    _susturucu = next(iter(REFERANS_AG_AILELERI))
    v = classify_cfd("ucak", ham["alpha"], ham["mach"], has_gci_band=False,
                     Cl=(ham.get("Cl") if "fizik" in kapilar else None),
                     Cd=(ham.get("Cd") if "fizik" in kapilar else None),
                     ag_yeterli=(ham.get("ag_yeterli") if "ag" in kapilar else _susturucu))
    onek = "C_L" if cell["q"] == "Cl" else "C_D"
    hukum = next(x for x in v if x.quantity.startswith(onek))
    return hukum.klass != VALIDATED


def classify(cell, tau, per_q=False, duzeltilmis=False):
    """Bir hücreyi TP/FP/TN/FN'e ata. silent = |naive−truth|/|truth| > τ (yanlış-ama-uyarısız);
    caught = guard design-grade vermedi (flagged). per_q=True → niceliğe-özel τ (TAU_BY_Q)."""
    err = abs(cell["naive"] - cell["truth"]) / abs(cell["truth"])
    if per_q:
        q = cell.get("q")
        if q not in TAU_BY_Q:
            raise BilinmeyenNicelik(
                f"'{q}' için τ tanımlı değil. Sessizce global τ'ya DÜŞMEZ — "
                f"TAU_BY_Q'ya açıkça ekleyin. Tanımlı: {sorted(TAU_BY_Q)}")
        t = TAU_BY_Q[q]
    else:
        t = tau
    silent = err > t
    # `duzeltilmis` KAPI LISTESIDIR (bos/False = dokunma). Onceki surumde yalnizca
    # dogruluk-degeri olarak kullaniliyordu ve ablasyonun uc kolu da varsayilan
    # ikili kapiyla olculuyordu; uc kol ayni matrisi verip yeniden-siniflanan
    # sayilari AYRISINCA yakalandi.
    caught = duzeltilmis_flag(cell, tuple(duzeltilmis)) if duzeltilmis else cell["flagged"]
    if silent and caught:
        return "TP", err
    if silent and not caught:
        return "FN", err
    if not silent and caught:
        return "FP", err
    return "TN", err


def wilson(k, n, z=1.96):
    """Oran icin Wilson skor araligi. n~30'da yuzde-bootstrap ya da normal-yaklasim
    yaniltir (sinira yakin oranlarda aralik [0,1] disina tasar); Wilson tasmaz."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    orta = (p + z * z / (2 * n)) / d
    yari = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, orta - yari), 4), round(min(1.0, orta + yari), 4)]


def confusion(corpus, tau, per_q=False, duzeltilmis=False):
    c = {"TP": 0, "FP": 0, "TN": 0, "FN": 0}
    for cell in corpus:
        lab, _ = classify(cell, tau, per_q, duzeltilmis=duzeltilmis)
        c[lab] += 1
    tp, fp, tn, fn = c["TP"], c["FP"], c["TN"], c["FN"]
    sens = tp / (tp + fn) if (tp + fn) else None
    spec = tn / (tn + fp) if (tn + fp) else None
    prev = (tp + fn) / len(corpus)
    # Kesinlik (precision) ve NPV, duyarlilik/ozgulluk ile AYNI matristen cikar
    # ama farkli soruyu yanitlar: "bir bayrak ne siklikla haklidir" ve "bir
    # sertifika ne siklikla guvenilir". Dengeli dogruluk, yaygin-lik 0.5'ten
    # uzaklastikca ham dogrulugun yaniltmasini onler.
    prec = tp / (tp + fp) if (tp + fp) else None
    npv = tn / (tn + fn) if (tn + fn) else None
    bal = ((sens + spec) / 2) if (sens is not None and spec is not None) else None
    # n~30'da nokta-degeri CIPLAK vermek asiri-iddiadir; aralik ZORUNLU eslikci.
    return {**c, "sensitivity": sens, "specificity": spec, "prevalence": prev,
            "precision": prec, "NPV": npv, "balanced_accuracy": bal,
            "sensitivity_CI95": wilson(tp, tp + fn),
            "specificity_CI95": wilson(tn, tn + fp),
            "precision_CI95": wilson(tp, tp + fp),
            "NPV_CI95": wilson(tn, tn + fn),
            "prevalence_CI95": wilson(tp + fn, len(corpus))}


def main():
    tau = next((float(sys.argv[i + 1]) for i, a in enumerate(sys.argv) if a == "--tau"), 0.05)
    print(f"=== Silent-failure assay (PILOT, n={len(CORPUS)}) ===")
    # HEADLINE: niceliğe-özel τ (refined kriter)
    res = confusion(CORPUS, tau, per_q=True)
    print(f"  [per-nicelik τ {TAU_BY_Q}] TP={res['TP']} FP={res['FP']} TN={res['TN']} FN={res['FN']}")
    print(f"  sensitivity={res['sensitivity']:.2f}  specificity={res['specificity']:.2f}  "
          f"prevalence={res['prevalence']:.2f}")
    print("  --- hücreler ---")
    for cell in CORPUS:
        lab, err = classify(cell, tau, per_q=True)
        print(f"   [{lab}] {cell['case']:14s} {cell['knob']:32s} err={err:5.1%} "
              f"guard={cell['gclass']}")
    # mini-ROC: GLOBAL-τ tara (per-nicelik'i MOTİVE eden tek-τ tradeoff'u)
    roc = [{"tau": t, **{k: confusion(CORPUS, t)[k] for k in ("sensitivity", "specificity")}}
           for t in (0.02, 0.03, 0.05, 0.10, 0.15)]

    # ── DÜZELTME-SONRASI KATMAN (dondurulmuş sonuca DAHİL DEĞİL) ──────────────
    # Doğrulayıcı değerlendirme iki eksik kapıyı ortaya çıkardı; kapılar sonradan
    # uygulandı ve AYNI korpusta yeniden ölçüldü. Ayrı raporlanır: bir doğrulayıcı
    # testin anlamı, sonucunu gördükten sonra sistemi değiştirip o değişikliği
    # aynı teste yazmamaktır.
    ABLASYON = {"yalniz_fizik": ("fizik",), "yalniz_ag": ("ag",),
                "ikisi": ("fizik", "ag")}
    duzeltme = {}
    print(f"\n  === DÜZELTME-SONRASI (aynı n={len(CORPUS)}, dondurulmuş sonuca KATILMAZ) ===")
    for ad, kapilar in ABLASYON.items():
        d = confusion(CORPUS, tau, per_q=True, duzeltilmis=kapilar)
        degisen = [f"{c['case']}/{c['knob']}" for c in CORPUS
                   if duzeltilmis_flag(c, kapilar) != c["flagged"]]
        duzeltme[ad] = {"kapilar": list(kapilar), "confusion": d,
                        "yeniden_siniflanan": degisen}
        print(f"  [{ad:12s}] TP={d['TP']:2d} FP={d['FP']:2d} TN={d['TN']:2d} FN={d['FN']:2d} · "
              f"sens={d['sensitivity']:.2f} spec={d['specificity']:.2f} "
              f"prec={d['precision']:.2f} NPV={d['NPV']:.2f} · "
              f"yeniden-sınıflanan={len(degisen)}")
    duz = duzeltme["ikisi"]["confusion"]

    out = ROOT / "silent_failure_assay_pilot.json"
    out.write_text(json.dumps({"tau_by_q": TAU_BY_Q, "n": len(CORPUS), "confusion_per_q": res,
                               "roc_global_tau_sweep": roc,
                               "duzeltme_sonrasi": {
                                   "_ne": "Doğrulayıcı koşudan SONRA uygulanan iki kapı "
                                          "(fiziksel akla-yatkınlık + taşımada ağ yeterliliği) "
                                          "aynı korpusta yeniden ölçüldü; kapılar AYRI AYRI da "
                                          "ölçüldü çünkü ağ kapısı fizik kapısını gölgeler.",
                                   "_kredi": "Bu sayılar dondurulmuş-eşik sonucuna KATILMAZ; "
                                             "Şekil 10 dondurulmuş sonucu gösterir.",
                                   "ablasyon": duzeltme,
                                   "confusion": duz},
                               "corpus": CORPUS}, indent=2,
                              ensure_ascii=False), encoding="utf-8")
    print(f"\n  YAZILDI {out.name}")
    print("  NOT: PILOT — küratör korpus + FEA element-order taraması (gerçek V&V çıktıları); "
          "tam sistematik tarama sonraki faz.")
    print("  Dürüst bulgular: FN=rocket-fin (geometri-fidelity, otomatik guard YOK); "
          "FEA element-order MEMBRANE'de sessiz-hata DEĞİL (bending'de olur); per-nicelik τ gerekli.")
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
