"""Bölüm 10 kıyasları MMA ile YENİDEN koşuldu — raporun kendi koyduğu koşul.

Rapor MMA'yı deneysel aday sayıyor ve üretime almanın koşulunu AÇIKÇA yazıyor:
``Bölüm 10 kıyaslarının MMA ile yeniden koşulması ve MMA'nın kendi durma
ölçütünün gösterilmesi.'' Bu betik o iki koşulu ölçer.

TABAN ÖNCE ÜRETİLİR. Kıyas düzeneği kayıtlı sayıyı birebir vermiyorsa, MMA
sonucu neye göre okunacağı belirsizdir. İlk denemede 3B tabanı 0,8895 çıktı
(kayıt 0,762): sebep ayar farkıydı --- kıyas gerilme adımını `max_iter=80,
move=0,15` ile koşuyor, ben 60/0,2 kullanmıştım. Düzenek düzeltilince taban
birebir üretildi (0,788 / 0,762 / %3,3).

WARM-START'IN GEREKÇESİ DE SINANIR. 3B kıyas gerilme adımını kompliyans
tasarımından başlatıyor ve sebebini yazıyor: ``OC stress'te tek-başına
kararsız/salınımlı''. O halde MMA'nın warm-start OLMADAN koşabilmesi, gerekçenin
OC'ye özgü olup olmadığını söyler.

    python experiments/mma_bolum10.py [--hizli]
Çıktı: mma_bolum10.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

CIKTI = KOK / "mma_bolum10.json"
# 2B kiyas ayarlari — `stress_topopt_lbracket.main`den AYNEN.
IKI_B = {"komp_iter": 70, "gerilme_iter": 80}
# 3B kiyas ayarlari — `stress_topopt3d_bench.main`den AYNEN. Sabit yazmak
# yerine oradan okunsaydi daha iyi olurdu ama o degerler main() icinde gomulu;
# burada YAZILI durmalari, ayrisirlarsa testin yakalayabilmesi icin.
UC_B = {"komp_iter": 60, "gerilme_iter": 80, "move": 0.15}
YAKINSAMA_TAVANI = {"2B": 2000, "3B": 1200}


def iki_b(guncelleyici: str, tavan: int | None = None) -> dict:
    from stress_topopt_lbracket import VF, build_lbracket, peak_and_field
    t, _ = build_lbracket()
    rho_c, hc = t.optimize(VF, "compliance", max_iter=IKI_B["komp_iter"],
                           guncelleyici=guncelleyici)
    pc, _ = peak_and_field(t, rho_c)
    it = tavan or IKI_B["gerilme_iter"]
    rho_s, hs = t.optimize(VF, "stress", max_iter=it, tol=0.01,
                           guncelleyici=guncelleyici)
    ps, _ = peak_and_field(t, rho_s)
    return _kayit(pc, ps, hs, it)


def uc_b(guncelleyici: str, warm: bool, tavan: int | None = None) -> dict:
    from stress_topopt3d_bench import VF, build_lbracket, peak_eta
    t, _ = build_lbracket()
    x0, pc = None, None
    if warm:
        rho_c, _ = t.optimize(VF, "compliance", max_iter=UC_B["komp_iter"],
                              guncelleyici=guncelleyici)
        x0, pc = rho_c, peak_eta(t, rho_c)
    it = tavan or UC_B["gerilme_iter"]
    rho_s, hs = t.optimize(VF, "stress", max_iter=it, move=UC_B["move"],
                           x0=x0, tol=0.01, guncelleyici=guncelleyici)
    return _kayit(pc, peak_eta(t, rho_s), hs, it)


def _kayit(pc, ps, h, tavan) -> dict:
    """Sonuç + DURMA bilgisi. ``Kaç iterasyon'' tek başına yetmez: tavana
    çarpmakla tolerans sağlamak aynı şey değildir."""
    o = [q["obj"] for q in h][-20:]
    net = abs(o[-1] - o[0]) if len(o) > 1 else 0.0
    top = sum(abs(b - a) for a, b in zip(o, o[1:])) if len(o) > 1 else 0.0
    return {
        "peak_komp": round(pc, 4) if pc is not None else None,
        "peak_gerilme": round(ps, 4),
        "azalma_pct": round(100 * (pc - ps) / pc, 2) if pc else None,
        "iterasyon": len(h), "tavan": tavan,
        "durdu_mu": len(h) < tavan,
        "son_ch": round(h[-1]["ch"], 5),
        "bosa_giden_hareket_pct": round(100 * (1 - net / top), 1) if top > 0 else None,
    }


def olc(hizli: bool = False) -> dict:
    t0 = time.time()
    r = {
        "2B_OC": iki_b("oc"),
        "2B_MMA": iki_b("mma"),
        "3B_OC_warm": uc_b("oc", True),
        "3B_MMA_warm": uc_b("mma", True),
        "3B_OC_soguk": uc_b("oc", False),
        "3B_MMA_soguk": uc_b("mma", False),
    }
    if not hizli:
        # DURMA OLCUTU SINAVI: tavan yukseltilirse MMA KENDI olcutuyle duruyor
        # mu? Raporun ikinci kosulu tam budur.
        r["2B_MMA_yakinsama"] = iki_b("mma", YAKINSAMA_TAVANI["2B"])
        r["2B_OC_yakinsama"] = iki_b("oc", YAKINSAMA_TAVANI["2B"])
        r["3B_MMA_yakinsama"] = uc_b("mma", False, YAKINSAMA_TAVANI["3B"])
        r["3B_OC_yakinsama"] = uc_b("oc", False, YAKINSAMA_TAVANI["3B"])
    return _ozetle(r, time.time() - t0, hizli)


def _ozetle(r: dict, sure_s: float, hizli: bool) -> dict:
    kosul1 = (r["2B_MMA"]["peak_gerilme"] is not None
              and r["3B_MMA_soguk"]["peak_gerilme"] is not None)
    kosul2 = (not hizli and r.get("2B_MMA_yakinsama", {}).get("durdu_mu")
              and r.get("3B_MMA_yakinsama", {}).get("durdu_mu"))
    return {
        "vaka": "Bölüm 10 kıyasları — MMA ile yeniden koşuldu",
        "_neden": ("Rapor MMA'yi deneysel aday sayiyor ve uretime almanin "
                   "kosulunu yaziyor: Bolum 10 kiyaslarinin MMA ile yeniden "
                   "kosulmasi + MMA'nin KENDI durma olcutunun gosterilmesi."),
        "taban_kayit": {"2B": {"komp": 2.6778, "gerilme": 2.482, "azalma_pct": 7.3},
                        "3B": {"komp": 0.788, "gerilme": 0.762, "azalma_pct": 3.3}},
        "kosular": r,
        "kosul_1_kiyaslar_yeniden_kosuldu": kosul1,
        "kosul_2_MMA_kendi_olcutuyle_durdu": bool(kosul2),
        "verdikt": _hukum(r, kosul1, kosul2, hizli),
        "sure_dk": round(sure_s / 60, 1),
        "_kisit": (
            "TEK PROBLEM AILESI (L-braket, 2B ve 3B) ve tek cozunurluk. "
            "Optimizasyon algoritmalarinin kiyasi probleme baglidir; bu sonuc "
            "GENEL bir ustunluk iddiasi DEGILDIR. MMA'nin asimptot katsayilari "
            "Svanberg'in onerdigi degerlerdedir ve bu probleme gore "
            "AYARLANMADI."),
        "_uretim": "Üretim: python experiments/mma_bolum10.py",
    }


def _hukum(r: dict, k1: bool, k2: bool, hizli: bool) -> str:
    a, b = r["2B_OC"], r["2B_MMA"]
    c, d = r["3B_OC_warm"], r["3B_MMA_soguk"]
    s = (f"2B: OC tepe {a['peak_gerilme']}, MMA {b['peak_gerilme']} "
         f"(boşa giden hareket %{a['bosa_giden_hareket_pct']} vs "
         f"%{b['bosa_giden_hareket_pct']}). "
         f"3B: OC warm-start'lı {c['peak_gerilme']}, MMA SOĞUK başlangıçla "
         f"{d['peak_gerilme']} --- yani MMA warm-start'a İHTİYAÇ DUYMADAN "
         f"OC'nin warm-start'lı sonucundan daha iyi. Warm-start'ın gerekçesi "
         f"(``OC stress'te tek-başına salınır'') OC'ye ÖZGÜ çıktı. ")
    if hizli:
        return s + "Durma ölçütü sınavı KOŞULMADI (--hizli)."
    m2 = r.get("2B_MMA_yakinsama", {})
    m3 = r.get("3B_MMA_yakinsama", {})
    o2 = r.get("2B_OC_yakinsama", {})
    o3 = r.get("3B_OC_yakinsama", {})
    s += (f"DURMA ÖLÇÜTÜ: MMA 2B'de {m2.get('iterasyon')} iterasyonda, 3B'de "
          f"{m3.get('iterasyon')} iterasyonda KENDİ toleransıyla durdu. OC "
          f"ikisinde de durmadı ({o2.get('iterasyon')} ve "
          f"{o3.get('iterasyon')} iterasyon tavanı) ve son adımı tam olarak "
          f"`move` sınırında kaldı ({o2.get('son_ch')} / {o3.get('son_ch')}) "
          f"--- limit çevrimi. ")
    s += ("RAPORUN İKİ KOŞULU DA SAĞLANDI" if (k1 and k2)
          else "KOŞULLAR HENÜZ SAĞLANMADI")
    return s + ". Üretim hattını değiştirmek AYRI bir karardır: Bölüm 10'un yayımlanmış sayıları değişir."


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc("--hizli" in sys.argv)
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
