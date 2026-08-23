"""Girdi-UQ taraması NE ölçtü — dört hipotez sınandı, üçü çürüdü.

LHS taraması Cd için %0,95 (2σ) band verdi ve ikinci bağımsız tarama %0,89.
Sayı yinelenebilir. Ama "u_girdi = %0,95" diye yayımlamak YANLIŞ olurdu:
bandın girdilerden geldiği GÖSTERİLEMEDİ.

NULL DEĞİŞKEN YÖNTEMİ. Taramaya, etkisi OLAMAYACAĞI ÖNCEDEN BİLİNEN iki girdi
kondu ve çalışma kendi kontrolüne dönüştü:

  * ρ  — Cd boyutsuz, çözücü SABİT kinematik viskoziteyle koşuyor (ν=1,5e-5).
         Re = V·L/ν, ρ'ya bağlı değil; Cd = F/(½ρV²A) ifadesinde ρ pay ve
         paydada birlikte gider. Cd, ρ'dan MATEMATİKSEL olarak bağımsızdır.
  * α  — taban vaka bir KÜREdir (eksenel simetrik). Hücum açısı bir simetri
         işlemidir; Cd değişemez.

Ölçülen Pearson r'ler: V −0,315, α −0,207, ρ −0,310 (n=30). İki null, gerçek
değişkenle AYNI mertebede. İkinci taramada (n=12) r(V) işaret değiştirdi
(+0,451) --- korelasyonlar kararlı bir fiziksel özellik değil.

DÖRT HİPOTEZ SINANDI:
  1. Erken-durdurma toleransı  → tol 10 kat sıkıldı, band DEĞİŞMEDİ (0,95→0,89)
  2. Ağın girdiye bağlı değişmesi → n_layers=0, ilk katman yok; ağ SABİT
                                    (30/30 koşu 316.514 hücre)
  3. Koşu tekrarsızlığı        → aynı girdiyle 6 tekrar: %0,069, bandın 1/14'ü
  4. Eşik altı salınımın atılması → arşivde eşik altı genlikler %0,00–0,09;
                                    büyük olanlar zaten sayılıyor. ÇÜRÜDÜ.

GERİYE KALAN VE VERİYLE DESTEKLENEN: koşular durduklarında hâlâ yakınsamamış.
Düzgün bir V taramasında (5 koşu) ölçüldü: son %20 driftı %0,07--0,54,
salınım genliği %0,06--0,55. Gözlenen band (%0,96) TAM BU BÜYÜKLÜKTE.

SONUÇ: ölçülen band iteratif yakınsama hatasıyla AYNI mertebede ve ondan
ayrılamıyor. u_girdi bir ÜST SINIRDIR; girdi duyarlılığı DEĞİLDİR.

    python experiments/girdi_uq_teshis.py
Çıktı: girdi_uq_teshis.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "girdi_uq_teshis.json"

# V duzgun tarandiginda olculen yakinsamamislik (5 kosu, iter_izle).
# Kaynak: kosu kayitlarindaki convergence.cd_drift_son20pct ve
# convergence.salinim.genlik_pct.
DUZGUN_TARAMA = [
    {"V": 19.50, "cd": 0.142530, "iter": 374, "drift_pct": 0.539, "genlik_pct": 0.55},
    {"V": 19.75, "cd": 0.141300, "iter": 376, "drift_pct": 0.068, "genlik_pct": 0.06},
    {"V": 20.00, "cd": 0.142660, "iter": 361, "drift_pct": 0.127, "genlik_pct": 0.40},
    {"V": 20.25, "cd": 0.142600, "iter": 357, "drift_pct": 0.118, "genlik_pct": 0.35},
    {"V": 20.50, "cd": 0.142550, "iter": 374, "drift_pct": 0.119, "genlik_pct": 0.33},
]

# ILK (GEVSEK) TARAMANIN SONUCU — dosyadan okunamiyor cunku ikinci tarama
# AYNI dosyaya yazdi. Bu bir prosedur kusuruydu ve burada ADIYLA duruyor:
# `girdi_uq_kos.py` ciktiyi sabit `girdi_uq_sonuc.json`'a yaziyor, dolayisiyla
# farkli toleransla kosulan iki calisma birbirini eziyor. Asagidaki degerler
# ilk kosunun kendi ciktisindan alindi.
GEVSEK_TARAMA = {"n": 30, "cd_tol": 0.003, "u_girdi_pct": 0.95,
                 "duyarlilik_pearson": {"velocity": -0.315, "alpha_deg": -0.207,
                                        "rho": -0.310}}


def kritik_r(n: int, alfa: float = 0.05) -> float:
    """İki yanlı %5 için kritik |r| — n'e BAĞLI.

    İlk sürüm n=30'un kritik değerini (0,361) n=12'lik taramaya da uyguladı ve
    r=−0,55'i "anlamlı" saydı; oysa n=12 için kritik değer 0,576'dır ve o
    korelasyon da anlamlı DEĞİLDİR. Eşik örneklem büyüklüğünden bağımsız
    yazılırsa sınav sessizce yanlış hüküm verir.
    """
    if n < 4:
        return 1.0
    # t-dagilimindan: r_kritik = t / sqrt(t^2 + df),  df = n-2
    from statistics import NormalDist
    df = n - 2
    # Kucuk df icin t yaklasimi (Cornish-Fisher benzeri duzeltme)
    z = NormalDist().inv_cdf(1 - alfa / 2)
    t = z * (1 + (z * z + 1) / (4 * df))
    return t / math.sqrt(t * t + df)


NULL_DEGISKENLER = {
    "rho": ("Cd boyutsuz ve çözücü SABİT kinematik viskoziteyle koşuyor "
            "(nu=1,5e-5). Re = V·L/nu, rho'ya bağlı değil; Cd = F/(0,5 rho V^2 A) "
            "ifadesinde rho pay ve paydada birlikte gider."),
    "alpha_deg": ("Taban vaka bir KÜRE — eksenel simetrik. Hücum açısı bir "
                  "simetri işlemidir; Cd değişemez."),
}


def _taramalar(siki: dict) -> list[dict]:
    """İki taramanın korelasyonları — her biri KENDİ n'inin eşiğiyle."""
    out = []
    for etiket, kayit in (("gevşek (cd_tol 0,003)", GEVSEK_TARAMA),
                          ("sıkı (cd_tol 0,0003)",
                           {"n": siki.get("n_tamamlanan"),
                            "cd_tol": siki.get("cd_tol"),
                            "u_girdi_pct": siki.get("u_girdi_pct"),
                            "duyarlilik_pearson": siki.get("duyarlilik_pearson") or {}})):
        n = kayit.get("n")
        if not n:
            continue
        kr = kritik_r(n)
        r = kayit.get("duyarlilik_pearson") or {}
        out.append({
            "tarama": etiket, "n": n, "cd_tol": kayit.get("cd_tol"),
            "u_girdi_pct": kayit.get("u_girdi_pct"),
            "duyarlilik_pearson": r, "kritik_r": round(kr, 3),
            "anlamli_olan": [a for a, v in r.items()
                             if v is not None and abs(v) >= kr],
        })
    return out


def _oku(ad: str) -> dict | None:
    p = KOK / ad
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def olc() -> dict:
    # Tarama ciktilari artik TOLERANSI ADLARINDA tasiyor (birbirini ezmesinler).
    gevsek = (_oku("girdi_uq_sonuc_tol0.0003.json")
              or _oku("girdi_uq_sonuc.json") or {})
    taban = _oku("girdi_uq_gurultu_tabani.json") or {}

    band = gevsek.get("u_girdi_pct")
    tekrar = taban.get("gurultu_tabani_pct")
    cd = [x["cd"] for x in DUZGUN_TARAMA]
    yayilim_pct = 100.0 * (max(cd) - min(cd)) / (sum(cd) / len(cd))
    yakinsamamislik = max(max(x["drift_pct"] for x in DUZGUN_TARAMA),
                          max(x["genlik_pct"] for x in DUZGUN_TARAMA))

    hipotezler = [
        {"hipotez": "Erken-durdurma toleransı bandı üretiyor",
         "sinav": "cd_tol 0,003 → 0,0003 (10 kat sıkı), 12 koşu",
         "sonuc": "ÇÜRÜDÜ", "olcum": "band %0,95 → %0,89 (değişmedi)"},
        {"hipotez": "Ağ girdiye bağlı değişiyor",
         "sinav": "kalite preset'i n_layers ve ilk-katman yüksekliği",
         "sonuc": "ÇÜRÜDÜ",
         "olcum": "n_layers=0 → ilk katman yok; 30/30 koşu 316.514 hücre"},
        {"hipotez": "Koşu tekrarsızlığı (deterministik olmama)",
         "sinav": "aynı girdiyle 6 tekrar",
         "sonuc": "ÇÜRÜDÜ",
         "olcum": f"%{tekrar} — bandın ~1/{round(band / tekrar) if (band and tekrar) else '?'}'i"},
        {"hipotez": "Eşik altı salınım u_sayısal'a girmiyor",
         "sinav": "arşivdeki 22 koşuda eşik altı genlikler",
         "sonuc": "ÇÜRÜDÜ",
         "olcum": ("eşik altı genlikler %0,00–0,09; eşik üstü olanlar ZATEN "
                   "sayılıyor (10/22 eşik altı, u_toplam değişimi +%0)")},
        {"hipotez": "Koşular yakınsamadan duruyor",
         "sinav": "düzgün V taraması, koşu başına drift ve salınım",
         "sonuc": "DESTEKLENDİ",
         "olcum": (f"drift %0,07–0,54, genlik %0,06–0,55; gözlenen yayılım "
                   f"%{yayilim_pct:.2f} AYNI mertebede")},
    ]

    return {
        "vaka": "Girdi-UQ taraması ne ölçtü — hipotez eleme",
        "_neden": ("LHS taramasi %0,95 (2sigma) band verdi ve ikinci tarama "
                   "%0,89 — sayi yinelenebilir. Ama bandin GIRDILERDEN geldigi "
                   "gosterilemedi ve 'u_girdi' diye yayimlamak YANLIS olurdu."),
        "null_degisken_yontemi": {
            "_ne": ("Taramaya, etkisi OLAMAYACAGI ONCEDEN BILINEN girdiler "
                    "konur; calisma kendi kontrolune doner. Null bir degisken "
                    "gercek degiskenle ayni mertebede korelasyon gosteriyorsa, "
                    "olculen sey girdi yaniti DEGILDIR."),
            "degiskenler": NULL_DEGISKENLER,
            "taramalar": _taramalar(gevsek),
            "_esik_notu": ("Kritik |r| ORNEKLEM BUYUKLUGUNE baglidir. Ilk surum "
                           "n=30'un esigini (0,361) n=12'lik taramaya da "
                           "uyguladi ve r=-0,55'i 'anlamli' saydi; n=12 icin "
                           "esik 0,576 ve o korelasyon da anlamli DEGIL."),
        },
        "hipotezler": hipotezler,
        "duzgun_v_taramasi": DUZGUN_TARAMA,
        "band_pct": band, "tekrar_tabani_pct": tekrar,
        "yakinsamamislik_pct": yakinsamamislik,
        "verdikt": (
            f"u_girdi ÖLÇÜLEMEDİ. Tarama %{band} (2σ) band verdi ama dört "
            f"hipotezden üçü çürüdü ve desteklenen tek açıklama, koşuların "
            f"yakınsamadan durması: koşu başına drift/salınım %"
            f"{yakinsamamislik:.2f}'e kadar çıkıyor ve gözlenen yayılım "
            f"(%{yayilim_pct:.2f}) tam bu mertebede. İki NULL değişkenin "
            f"korelasyonu gerçek değişkeninkiyle aynı olduğu için band, girdi "
            f"duyarlılığı olarak OKUNAMAZ. %{band} bir ÜST SINIRDIR."),
        "ne_gerekir": (
            "Girdi duyarliligini ayirmak icin kosu-basina yakinsama hatasi "
            "girdi-kaynakli farktan KUCUK olmali. Bugun ikisi ayni mertebede. "
            "Gereken: iterasyon tavani ve rezidual denetimi siki tutulmus bir "
            "tarama; sonrasinda NULL degiskenlerin korelasyonu SIFIRA inmeli — "
            "bu, calismanin kendi ic denetimidir ve gecmeden band yayimlanmaz."),
        "_kisit": (
            "Null-degisken akil yurutmesi VAKAYA OZGUDUR: alpha ancak eksenel "
            "simetrik govdede nulldur, rho ise sabit-nu kabulune baglidir. "
            "Baska bir vakada bu iki degisken GERCEK olabilir ve o zaman "
            "kontrol islevini yitirirler. Ayrica 'yakinsamadan durma' "
            "aciklamasi DESTEKLENDI, KANITLANMADI: kesin sinav, tavani "
            "yukseltip bandin cokmesini gostermektir ve o kosulmadi."),
        "_uretim": "Üretim: python experiments/girdi_uq_teshis.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    print("Girdi-UQ taraması ne ölçtü\n")
    print(f"{'hipotez':<44}{'sonuç':<14}ölçüm")
    for h in r["hipotezler"]:
        print(f"{h['hipotez'][:43]:<44}{h['sonuc']:<14}{h['olcum'][:60]}")
    n = r["null_degisken_yontemi"]
    print(f"\nnull değişkenler: {', '.join(n['degiskenler'])}")
    for t in n["taramalar"]:
        print(f"  {t['tarama']:<24} n={t['n']:<3} kritik|r|={t['kritik_r']:.3f}  "
              f"u_girdi=%{t['u_girdi_pct']}")
        print(f"      r: {t['duyarlilik_pearson']}")
        print(f"      anlamlı olan: {t['anlamli_olan'] or 'HİÇBİRİ'}")
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
