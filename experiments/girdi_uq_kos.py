"""Girdi belirsizliğini GERÇEKTEN yay — LHS tarama, ölçülen band.

Bütçe (`girdi_uq_butcesi`) bunun ulaşılabilir olduğunu söyledi: üç girdi,
LHS 30 koşu ≈ 1,4 saat. Bu betik o taramayı koşar ve `u_girdi`'yi ÖLÇER.

GİRDİ DAĞILIMLARI VARSAYIMDIR VE ÖYLE YAZILIR. Hızın ±%2 mi ±%10 mu belirsiz
olduğu kullanıcının vakasına bağlıdır; burada savunulabilir aralıklar
BEYAN EDİLİR ve sonuç "bu girdi belirsizlikleri VERİLDİĞİNDE çıktı bandı
şudur" biçiminde okunur. Dağılımı değiştirmek sonucu değiştirir ve bu bir
kusur değil, girdi UQ'nun tanımıdır.

AĞ SABİT TUTULUR. Aynı geometri, aynı kalite ön ayarı, aynı çözücü: sayısal
hata ORTAK-KİP olur ve saçılmanın girdiden geldiği söylenebilir. Farklı ağda
koşmak, girdi etkisiyle ayrıklaştırma etkisini karıştırırdı.

    python experiments/girdi_uq_kos.py [--n 30] [--kuru]
Çıktı: girdi_uq_sonuc.json
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

# CIKTI ADI TOLERANSI TASIR. Sabit ad kullanildiginda farkli
# toleransla kosulan iki calisma birbirini EZDI (olculdu 2026-08-23:
# gevsek taramanin ham verisi kayboldu ve teshis dosyasina elle
# tasinmak zorunda kaldi).
def _cikti(cd_tol: float, tavan: int | None = None) -> Path:
    # AD HER IKI AYARI DA TASIR: ayni toleransla farkli TAVANDA kosulan
    # iki calisma da birbirini ezerdi.
    ek = f"_it{tavan}" if tavan else ""
    return KOK / f"girdi_uq_sonuc_tol{cd_tol:g}{ek}.json"

# TABAN VAKA: kure — Cd'si literaturde bilinen, ucuz ve iyi huylu.
TABAN = {"stl": KOK / "vehicle_runs" / "test_sphere" / "test_sphere_prep.stl",
         "vehicle_type": "roket", "quality": "standart",
         "velocity": 20.0, "alpha_deg": 0.0, "rho": 1.225}

# GIRDI BELIRSIZLIKLERI — VARSAYIM, olcum degil. Her biri gerekceli.
GIRDI_BANDI = {
    "velocity": {"tip": "bagil", "yari_genislik": 0.05,
                 "gerekce": "rüzgâr tüneli/uçuş hız ölçümü ±%5 (pitot kalibrasyonu, "
                            "blokaj düzeltmesi)"},
    "alpha_deg": {"tip": "mutlak", "yari_genislik": 0.5,
                  "gerekce": "montaj/trim açı belirsizliği ±0,5° (model tutucu, "
                             "akış yönü)"},
    "rho": {"tip": "bagil", "yari_genislik": 0.03,
            "gerekce": "hava yoğunluğu ±%3 (irtifa 0–250 m, sıcaklık 10–30 °C)"},
}


def lhs(n: int, d: int, tohum: int = 20260823) -> list[list[float]]:
    """Latin hiperküp örneklemi [0,1)^d — dış bağımlılık YOK.

    Her boyut n dilime bölünür ve her dilimden BİR nokta alınır; dilim
    sırası bağımsız karıştırılır. Bu, saf rastgele örneklemin bırakabildiği
    boşlukları kapatır.
    """
    import random
    r = random.Random(tohum)
    out = [[0.0] * d for _ in range(n)]
    for j in range(d):
        dilimler = list(range(n))
        r.shuffle(dilimler)
        for i, s in enumerate(dilimler):
            out[i][j] = (s + r.random()) / n
    return out


def _deger(taban: float, band: dict, u: float) -> float:
    """[0,1) örneğini girdi değerine çevir — ÜÇGEN değil DÜZGÜN dağılım.

    Düzgün seçildi çünkü elde dağılımın şeklini gösterecek veri YOK; düzgün
    dağılım verilen aralıkta EN GENİŞ bandı verir, yani muhafazakâr yön.
    """
    yg = band["yari_genislik"]
    genlik = taban * yg if band["tip"] == "bagil" else yg
    return taban + (2 * u - 1) * genlik


def olc(n: int = 30, kuru: bool = False, cd_tol: float = 0.003,
        iterasyon_tavani: int | None = None) -> dict:
    from vehicle_pipeline import run_vehicle_analysis

    adlar = list(GIRDI_BANDI)
    ornekler = lhs(n, len(adlar))
    plan = []
    for u in ornekler:
        p = {a: _deger(TABAN[a], GIRDI_BANDI[a], ui) for a, ui in zip(adlar, u)}
        plan.append(p)

    if kuru:
        return {"vaka": "Girdi UQ — KURU KOŞU", "plan": plan, "n": n,
                "_uretim": "Üretim: python experiments/girdi_uq_kos.py --kuru"}

    kosular, dusen = [], []
    t0 = time.time()
    for i, p in enumerate(plan, 1):
        try:
            r = run_vehicle_analysis(
                str(TABAN["stl"]), vehicle_type=TABAN["vehicle_type"],
                velocity=p["velocity"], alpha_deg=p["alpha_deg"],
                quality=TABAN["quality"], rho=p["rho"], cd_tol=cd_tol,
                iterasyon_tavani=iterasyon_tavani,
                out_root=str(KOK / "_uq_runs"), n_processors=4)
        except Exception as e:      # noqa: BLE001 — sebep KAYDEDILIYOR
            dusen.append({"i": i, **p, "hata": f"{type(e).__name__}: {e}"[:120]})
            continue
        if r.status != "ok" or r.cd is None:
            dusen.append({"i": i, **p, "hata": (r.error or "cd yok")[:120]})
            continue
        kosular.append({"i": i, **p, "cd": r.cd, "cl": r.cl,
                        "hucre": (r.mesh or {}).get("cells")})
        print(f"[{i}/{n}] V={p['velocity']:.2f} α={p['alpha_deg']:+.2f} "
              f"ρ={p['rho']:.4f} → Cd={r.cd:.5f}", flush=True)

    return _ozetle(kosular, dusen, n, time.time() - t0)


def _band_ozeti() -> str:
    """Girdi bantlarının tek satırlık özeti — hükümde yazılı dursun."""
    return ", ".join(f"{a} ±{GIRDI_BANDI[a]['yari_genislik']:g}"
                     for a in GIRDI_BANDI)


def _ozetle(kosular: list[dict], dusen: list[dict], n: int, sure_s: float) -> dict:
    cd = [k["cd"] for k in kosular]
    if len(cd) < 3:
        return {"vaka": "Girdi belirsizliği yayılımı — LHS",
                "verdikt": f"ÖLÇÜLEMEDİ — yalnız {len(cd)} koşu tamamlandı",
                "dusen": dusen, "_uretim": "Üretim: python experiments/girdi_uq_kos.py"}
    ort = sum(cd) / len(cd)
    sd = math.sqrt(sum((x - ort) ** 2 for x in cd) / (len(cd) - 1))
    # u_girdi: %95 kapsama icin ~2 sigma, BAGIL yuzde olarak
    u_girdi = 200.0 * sd / ort

    # BIRINCI-MERTEBE DUYARLILIK: her girdi ile Cd arasindaki Pearson r.
    # Duzgun-dagilimli LHS'te bu, girdinin bandı ne kadar surukledigini
    # KABA olarak verir. Sobol degildir ve oyle SUNULMAZ.
    duyarlilik = {}
    for a in GIRDI_BANDI:
        x = [k[a] for k in kosular]
        mx = sum(x) / len(x)
        sx = math.sqrt(sum((v - mx) ** 2 for v in x) / (len(x) - 1))
        if sx <= 0 or sd <= 0:
            duyarlilik[a] = None
            continue
        kov = sum((v - mx) * (c - ort) for v, c in zip(x, cd)) / (len(x) - 1)
        duyarlilik[a] = round(kov / (sx * sd), 3)

    return {
        "vaka": "Girdi belirsizliği yayılımı — LHS taraması",
        "_neden": ("u_toplam bugun sayisal ve model-form bilesenlerinden "
                   "kuruluyor; ucuncu terim (girdi) SIFIR sayiliyordu."),
        "taban_vaka": {k: (str(v) if isinstance(v, Path) else v)
                       for k, v in TABAN.items()},
        "girdi_bandi": GIRDI_BANDI,
        "n_istenen": n, "n_tamamlanan": len(cd), "dusen": dusen,
        "sure_dk": round(sure_s / 60, 1),
        "cd_ort": round(ort, 6), "cd_sd": round(sd, 6),
        "cd_min": round(min(cd), 6), "cd_max": round(max(cd), 6),
        "u_girdi_pct": round(u_girdi, 2),
        "duyarlilik_pearson": duyarlilik,
        "kosular": kosular,
        # Ic ice f-string tirnagi Python 3.12+ sozdizimi; depo 3.11 uyumlulugu
        # koruyor (ruff yakaladi). Ifade disari alindi.
        "verdikt": (
            f"u_girdi = %{u_girdi:.2f} (2σ/ortalama). Verilen girdi bantlarında "
            f"({_band_ozeti()}) "
            f"Cd = {ort:.5f} ± {sd:.5f} (1σ), aralık [{min(cd):.5f}, {max(cd):.5f}], "
            f"{len(cd)}/{n} koşu, {sure_s / 60:.0f} dk."),
        "_kisit": (
            "GIRDI DAGILIMLARI VARSAYIMDIR, olcum degil — degistirilirse sonuc "
            "degisir ve bu girdi UQ'nun TANIMIDIR. Duzgun dagilim secildi cunku "
            "sekli gosterecek veri yok; duzgun, verilen aralikta EN GENIS bandi "
            "verir (muhafazakar yon). Pearson r birinci-mertebe bir gostergedir, "
            "SOBOL INDEKSI DEGILDIR ve etkilesimleri gormez. u_girdi mevcut "
            "u_sayisal ve u_model'in YERINE GECMEZ, yanina RSS ile girer. "
            "Ag sabit tutuldu ki sayisal hata ortak-kip olsun."),
        "_uretim": "Üretim: python experiments/girdi_uq_kos.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    n = 30
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    tol = 0.003
    if "--cd-tol" in sys.argv:
        tol = float(sys.argv[sys.argv.index("--cd-tol") + 1])
    tavan = None
    if "--iterasyon-tavani" in sys.argv:
        tavan = int(sys.argv[sys.argv.index("--iterasyon-tavani") + 1])
    r = olc(n, kuru="--kuru" in sys.argv, cd_tol=tol,
            iterasyon_tavani=tavan)
    r["iterasyon_tavani"] = tavan
    r["cd_tol"] = tol
    if "--kuru" in sys.argv:
        for p in r["plan"][:5]:
            print({k: round(v, 4) for k, v in p.items()})
        print(f"... toplam {r['n']} koşu")
        return 0
    print(f"\n{r['verdikt']}")
    if r.get("duyarlilik_pearson"):
        print("duyarlılık (Pearson r):", r["duyarlilik_pearson"])
    import ortam
    ortam.damgala(r)
    yol = _cikti(tol, tavan)
    yol.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"-> {yol.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
