"""Sürülen iki-yönlü FSI kıyası bu donanımda MÜMKÜN MÜ — bütçe türetimi.

NEDEN: tahrik bandı (sehim/açıklık %1--3) bulundu ve ilmek yakınsadı, ama
kuplaj fiziksel olarak sürülmedi. İki ayrı sebep ölçüldü:

  1. Düz konsol levha SAF EĞİLME yapıyor (burulma −0,041°, eşik 0,2°). Yerel
     hücum açısı değişmiyor, dolayısıyla basınç da değişmiyor. Sehim
     büyütmek bunu düzeltmez --- geometri değişmeli.

  2. Aracın KENDİ kurulum kapısı diyor ki firar kenarı çözülemiyor: "ince
     özellik yalnız 0,06 hücre (hedef ≥6) ... Kutta koşulu kurulamaz,
     sirkülasyon ve TAŞIMA doğmaz; Cl/L-D güvenilir DEĞİLDİR". Yani bu
     ailedeki her koşunun taşıması zaten güvenilmez.

BU DOSYA İKİNCİ KISITI NİCELLEŞTİRİR ve bir ÇELİŞKİ olduğunu gösterir:

  ÇÖZÜNÜRLÜK ister ki  t/L_maks ≥ 6/D      (kalınlık en az 6 hücre)
  ESNEKLİK  ister ki   t/L_maks ≤ (k·q / (hedef·E))^(1/3)

D = L_maks/hücre, yani ağın çözünürlük çarpanı. İkisi birleşince

  D ≥ 6 · (hedef·E / (k·q))^(1/3)

E'ye küp-kök bağlı: malzemeyi 100 kat yumuşatmak D'yi yalnız 4,6 kat düşürür.
q'ya da küp-kök bağlı ve q ~ V², yani hız 10 kat dinamik basınç için
V'yi 3,16 katlamak gerekir ve bu D'yi 2,15 kat düşürür.

k ÖLÇÜLEN VAKADAN kalibre edilir (uydurulmaz): fsi_tahrikH.

    python experiments/fsi_tahrik_fizibilite.py
Çıktı: fsi_tahrik_fizibilite.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "fsi_tahrik_fizibilite.json"

HEDEF_SEHIM = 0.02          # sehim/aciklik; band %1-3'un ortasi
MIN_HUCRE_KALINLIK = 6.0    # aracin kendi kurulum kapisi
KB_HUCRE = 0.779            # OLCULEN cozum bellek katsayisi
BOS_BELLEK_GB = 4.6         # bu makine
IS_ISTASYONU_GB = 192.0     # planlanan


def kalibre_k(sehim_oran: float, E_Pa: float, q_Pa: float, L_bolu_t: float) -> float:
    """δ/L = k·(q/E)·(L/t)³ bağıntısındaki k --- ÖLÇÜLEN koşudan.

    Kiriş kuramından türetmek yerine ölçülen koşuya oturtulur: yük dağılımının
    şekli, uç etkileri ve gerçek mesnet burada toplanır. Tek noktadan kalibre
    edilen bir katsayı ancak AYNI ailede kullanılabilir ve bu yazılıdır.
    """
    return sehim_oran * E_Pa / (q_Pa * L_bolu_t ** 3)


def gereken_D(E_Pa: float, q_Pa: float, k: float,
              hedef: float = HEDEF_SEHIM) -> float:
    """Çözünürlük ve esneklik AYNI ANDA sağlanması için gereken ağ çarpanı."""
    return MIN_HUCRE_KALINLIK * (hedef * E_Pa / (k * q_Pa)) ** (1.0 / 3.0)


def olc() -> dict:
    import math

    kosu = json.loads((KOK / "vehicle_runs" / "fsi_tahrikH"
                       / "sonuc.json").read_text(encoding="utf-8"))
    band = json.loads((KOK / "fsi_tahrik_bandi.json").read_text(encoding="utf-8"))
    ref = next(k for k in band["kosular"] if k["kosu"] == "fsi_tahrikH")

    V = float(kosu["velocity"])
    rho = 1.225
    q = 0.5 * rho * V * V
    L = float(ref["aciklik_m"])
    t = 1.0e-3                     # levha kalinligi (girdi geometrisi)
    E_al = 69e9
    k = kalibre_k(ref["sehim_aciklik_pct"] / 100.0, E_al, q, L / t)

    hucre = (kosu.get("mesh") or {}).get("cells")
    lmax = (kosu.get("geometry") or {}).get("lmax_m")
    # MEVCUT D, aracin KENDI olcumunden turetilir: "ince ozellik 0,06 hucre"
    # demek hucre = t/0,06 demektir.
    mevcut_hucre_m = t / 0.06
    D_mevcut = lmax / mevcut_hucre_m

    # MALZEME MODULU VERITABANINDAN, ELLE DEGIL. materials.json tek kaynak;
    # burada bir sayi yazmak onu ikinci kaynak yapardi.
    ham = json.loads((KOK / "materials.json").read_text(encoding="utf-8"))
    malz = {ad: float(ham[ad]["youngs_modulus"]) * 1e9
            for ad in ("Aluminum 6061", "Balsa Wood", "Glass Fiber (Epoxy)")
            if ad in ham and ham[ad].get("youngs_modulus")}
    if not malz:
        raise RuntimeError("materials.json'da beklenen malzemeler yok")

    senaryolar = []
    for ad, E in malz.items():
        for Vs in (V, 2 * V, 3.16 * V):
            qs = 0.5 * rho * Vs * Vs
            D = gereken_D(E, qs, k)
            oran = D / D_mevcut
            for us, etiket in ((2.0, "yüzey-yakın"), (3.0, "hacim")):
                n = hucre * oran ** us
                gb = n * KB_HUCRE / 1e6
                senaryolar.append({
                    "malzeme": ad, "E_GPa": round(E / 1e9, 1),
                    "hiz_m_s": round(Vs, 1), "gereken_D": round(D),
                    "D_kat": round(oran, 1), "olcek": etiket,
                    "hucre_M": round(n / 1e6, 1), "bellek_GB": round(gb, 1),
                    "bu_makinede": gb <= BOS_BELLEK_GB,
                    "is_istasyonunda": gb <= IS_ISTASYONU_GB,
                })

    uygun_mak = [s for s in senaryolar if s["bu_makinede"]]
    uygun_is = [s for s in senaryolar if s["is_istasyonunda"]]
    # EN UCUZ ULASILABILIR: is istasyonunda, IYIMSER olcekte
    en_ucuz = min((s for s in uygun_is if s["olcek"] == "yüzey-yakın"),
                  key=lambda s: s["bellek_GB"], default=None)
    # EN UCUZ SENARYONUN KOTUMSER UCU DA SOYLENIR. Hucre sayisi kestirimi bir
    # BANDDIR (D^2 ile D^3 arasi); yalniz iyimser ucu alintilamak, olculmemis
    # bir kesinlik yayimlamak olurdu — bu deponun her yerde reddettigi sey.
    kotu = next((s for s in senaryolar
                 if en_ucuz and s["malzeme"] == en_ucuz["malzeme"]
                 and s["hiz_m_s"] == en_ucuz["hiz_m_s"]
                 and s["olcek"] == "hacim"), None)

    return {
        "vaka": "Sürülen iki-yönlü FSI kıyası — fizibilite bütçesi",
        "_neden": ("Tahrik bandi bulundu ve ilmek yakinsadi ama kuplaj FIZIKSEL "
                   "olarak surulmedi: duz levha SAF EGILME yapiyor ve aracin "
                   "kendi kapisi firar kenarinin cozulemedigini soyluyor."),
        "kalibrasyon": {
            "kosu": "fsi_tahrikH", "V_m_s": V, "q_Pa": round(q, 1),
            "sehim_aciklik_pct": ref["sehim_aciklik_pct"],
            "L_bolu_t": round(L / t), "E_Pa": E_al, "k": round(k, 4),
            "_not": ("k KIRIS KURAMINDAN turetilmedi, OLCULEN kosuya oturtuldu; "
                     "yuk dagiliminin sekli ve mesnet etkisi burada toplanir. "
                     "Tek noktadan kalibre edilen katsayi ancak AYNI ailede "
                     "kullanilabilir."),
        },
        "mevcut": {"hucre": hucre, "lmax_m": lmax,
                   "yuzey_hucresi_mm": round(mevcut_hucre_m * 1e3, 1),
                   "D": round(D_mevcut, 1),
                   "_kaynak": "aracın kurulum kapısı: ince özellik 0,06 hücre"},
        "senaryolar": senaryolar,
        "bu_makinede_uygun": len(uygun_mak),
        "is_istasyonunda_uygun": len(uygun_is),
        "en_ucuz_ulasilabilir": en_ucuz,
        "en_ucuzun_kotumser_ucu": kotu,
        "verdikt": (
            (f"BU MAKINEDE ULASILAMAZ ({len(uygun_mak)}/{len(senaryolar)} senaryo). "
             + (f"192 GB iş istasyonunda en ucuz aday {en_ucuz['malzeme']} + "
                f"{en_ucuz['hiz_m_s']:.0f} m/s, AMA bütçe bir BAND: "
                f"{en_ucuz['bellek_GB']:.0f} GB (yüzey-yakın ölçekleme) ile "
                f"{kotu['bellek_GB']:,.0f} GB (hacim ölçekleme) arasında. "
                f"Yalnız iyimser uç tutarsa sığar; hangi ucun geçerli olduğu "
                f"ÖLÇÜLMEDİ, o yüzden bu bir PLAN değil bir ÜST/ALT SINIRDIR."
                if (en_ucuz and kotu) else
                "192 GB iş istasyonunda da ULAŞILAMAZ — geometri ailesi "
                "değişmeli, donanım değil."))
            if not uygun_mak else
            f"ULASILABILIR: {len(uygun_mak)} senaryo bu makinede sığıyor"),
        "_kisit": (
            "D ~ E^(1/3) ve D ~ q^(-1/3): malzemeyi 100 kat yumusatmak agi "
            "yalniz 4,6 kat ucuzlatir, dinamik basinci 10 katlamak 2,15 kat. "
            "Yani bu bir DONANIM sorunundan cok bir GEOMETRI-AILESI sorunudur; "
            "esneklik t/L'yi kucultur, cozunurluk buyutur ve ikisi ayni "
            "buyukluge zit yonde basar. Hucre sayisi kestirimi D^2 (yuzey-yakin) "
            "ile D^3 (hacim) arasinda bir BANDDIR, tek sayi degil.",
        ),
        "_uretim": "Üretim: python experiments/fsi_tahrik_fizibilite.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    kal = r["kalibrasyon"]
    print("Sürülen iki-yönlü FSI — fizibilite bütçesi\n")
    print(f"kalibrasyon: {kal['kosu']}  V={kal['V_m_s']} m/s  q={kal['q_Pa']} Pa  "
          f"L/t={kal['L_bolu_t']}  sehim/açıklık %{kal['sehim_aciklik_pct']}  "
          f"→ k={kal['k']}")
    m = r["mevcut"]
    print(f"mevcut ağ  : {m['hucre']:,} hücre  yüzey hücresi {m['yuzey_hucresi_mm']} mm"
          f"  D={m['D']}\n")
    print(f"{'malzeme':<22}{'V':>6}{'D':>7}{'D kat':>7}{'ölçek':>13}"
          f"{'hücre':>10}{'bellek':>10}")
    for s in r["senaryolar"]:
        im = "✓" if s["is_istasyonunda"] else " "
        print(f"{s['malzeme'][:21]:<22}{s['hiz_m_s']:>6.0f}{s['gereken_D']:>7}"
              f"{s['D_kat']:>7.1f}{s['olcek']:>13}{s['hucre_M']:>9.0f}M"
              f"{s['bellek_GB']:>9.0f}G {im}")
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
