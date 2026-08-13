"""NACA0012 doğrulaması, REFERANSIN KENDİ Reynolds koşulunda — ve bir belirsizliği ölçer.

NEDEN: Makale §5.1 hattın Re = 3,4×10⁶'da koştuğunu, referansın ise Ladson
(NASA TMR, TM-4074) Re = 6×10⁶ olduğunu söylüyor. Buna karşılık
`validation_suite.py` AYNI referans değerlerini "Ladson 1988 Re=3e6" diye
etiketliyor. İkisi birden doğru olamaz ve kaynak veri dosyası depoda yok.

Bu belirsizlik iki nedenle önemlidir. Birincisi, dış hakem "toleransı üreten
veriyle doğrulama yapıyorsunuz" dedi ve düzeltmesi referansın KENDİ koşulunda
koşmaktır — hangi koşul olduğunu bilmeden bu yapılamaz. İkincisi, bağlı-akış
zarfının ilan ettiği ≤%8 taşıma toleransı bu referanstan okunmuştur.

YÖNTEM: Tartışmak yerine ÖLÇ. Aynı ağ ve aynı çözücüyle iki Reynolds sayısında
koş (3×10⁶ ve 6×10⁶), her ikisini de aynı referansa karşı değerlendir. Hangi
Re referansa sistematik olarak daha yakınsa, referansın koşulu odur — Cd
Reynolds'a duyarlıdır (Cd₀ ≈ 0,0085 @3e6 vs ≈ 0,0080 @6e6), taşıma değildir.

SINANAN İDDİA (koşudan ÖNCE yazılıyor):
    R1  Cd sapması iki Re arasında AYIRT EDİLEBİLİR biçimde farklıdır
        (yani referansın Re'si veriden okunabilir).
    R2  Referansın kendi Re'sinde koşulduğunda α=8° taşıma hatası ilan edilen
        %8 toleransının ALTINA iner.
R1 tutmazsa referansın Re'si bu veriyle belirlenemez ve bu SÖYLENİR.
R2 tutmazsa %8 toleransı bağımsız veriyle DOĞRULANMAMIŞ kalır ve bu da söylenir.

Üretim: python experiments/naca0012_re_eslesme.py
Çıktı : naca0012_re_eslesme.json
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validation_suite import NACA0012_NASA, NACA0012Validation  # noqa: E402

KOK = HERE.parent
KANIT = KOK / "naca0012_re_eslesme.json"
ALPHALAR = [0, 4, 8]
YOGUNLUK = ("mid", 200, 80)          # doğrulayıcı korpusta güvenilir seviye
TOLERANS_LIFT_PCT = 8.0              # zarfın ilan ettiği bağlı-akış toleransı

# (etiket, nu) — V ve kord sabit; Re yalnız viskoziteden değişir ki AĞ AYNI kalsın.
RE_AILESI = [("Re3e6", 50.0 * 1.0 / 3.0e6), ("Re6e6", 50.0 * 1.0 / 6.0e6)]


def _kos(etiket: str, nu: float) -> list[dict]:
    out = []
    for a in ALPHALAR:
        ad, nprof, nnorm = YOGUNLUK
        v = NACA0012Validation(str(KOK / f"_re_esleme/{etiket}_a{a}"))
        v.NU = nu
        v.RE = v.V * v.C / nu
        v.n_prof, v.n_norm = nprof, nnorm
        print(f"  [{etiket} a={a}] Re={v.RE:.2e} koşuluyor...", flush=True)
        try:
            r = v.run(a)
        except Exception as e:                                    # noqa: BLE001
            out.append({"re": etiket, "alpha": a, "error": f"{type(e).__name__}: {e}"})
            print(f"  [{etiket} a={a}] HATA {e}", flush=True)
            continue
        cl_ref, cd_ref, kaynak = NACA0012_NASA[a]
        if r.get("status") == "FAILED":
            out.append({"re": etiket, "alpha": a,
                        "error": f"FAILED@{r.get('step')}"})
            continue
        cl, cd = r.get("Cl_sim"), r.get("Cd_sim")
        h_cl = (100 * abs(cl - cl_ref) / abs(cl_ref)) if (cl is not None and cl_ref) else None
        h_cd = (100 * abs(cd - cd_ref) / abs(cd_ref)) if (cd is not None and cd_ref) else None
        out.append({"re": etiket, "Re": v.RE, "alpha": a, "Cl": cl, "Cd": cd,
                    "Cl_ref": cl_ref, "Cd_ref": cd_ref, "ref_kaynak": kaynak,
                    "Cl_hata_pct": h_cl, "Cd_hata_pct": h_cd})
        print(f"  [{etiket} a={a}] Cl={cl} (%{h_cl}) Cd={cd} (%{h_cd})", flush=True)
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    hucreler = []
    for etiket, nu in RE_AILESI:
        hucreler += _kos(etiket, nu)

    def _ort_cd(et):
        v = [h["Cd_hata_pct"] for h in hucreler
             if h.get("re") == et and h.get("Cd_hata_pct") is not None]
        return sum(v) / len(v) if v else None

    def _a8_cl(et):
        return next((h.get("Cl_hata_pct") for h in hucreler
                     if h.get("re") == et and h.get("alpha") == 8), None)

    cd3, cd6 = _ort_cd("Re3e6"), _ort_cd("Re6e6")
    r1 = (cd3 is not None and cd6 is not None and abs(cd3 - cd6) > 2.0)
    yakin = None if not r1 else ("Re3e6" if cd3 < cd6 else "Re6e6")
    a8 = _a8_cl(yakin) if yakin else None
    r2 = a8 is not None and a8 < TOLERANS_LIFT_PCT

    if not r1:
        verdikt = ("⚠️ R1 TUTMADI: iki Reynolds sayısı Cd sapmasında ayırt "
                   f"edilemiyor (ort |Δ| {cd3}% vs {cd6}%). Referansın Re'si "
                   "bu veriyle BELİRLENEMEZ; makale–kod etiket çelişkisi açık "
                   "kalır ve kaynak veriden çözülmelidir.")
    elif r2:
        verdikt = (f"✅ Referans koşulu {yakin} (ort Cd sapması {min(cd3, cd6):.1f}% "
                   f"vs {max(cd3, cd6):.1f}%). O koşulda α=8° taşıma hatası "
                   f"%{a8:.1f} < %{TOLERANS_LIFT_PCT} — ilan edilen tolerans "
                   "BAĞIMSIZ olarak doğrulandı.")
    else:
        verdikt = (f"⚠️ Referans koşulu {yakin} görünüyor ama α=8° taşıma hatası "
                   f"%{a8:.1f} ≥ %{TOLERANS_LIFT_PCT}: ilan edilen tolerans bu "
                   "koşulda SAĞLANMIYOR ve tolerans yeniden gerekçelendirilmeli.")

    o = {"vaka": "NACA0012 — referansın Reynolds koşulu ÖLÇÜLÜYOR",
         "sinanan_iddia": {"R1": "iki Re, Cd sapmasında ayırt edilebilir",
                           "R2": "referans koşulunda α=8° taşıma hatası < %8",
                           "_not": "İddialar koşudan ÖNCE modül docstring'inde sabitlendi."},
         "celiskinin_kaynagi": {
             "makale": "§5.1: referans Ladson, Re = 6×10⁶ (NASA TMR / TM-4074)",
             "kod": "validation_suite.NACA0012_REF etiketi: 'Ladson 1988 Re=3e6'",
             "_not": "Kaynak veri dosyası depoda yok; çelişki ÖLÇÜMLE sınanıyor."},
         "yogunluk": {"ad": YOGUNLUK[0], "n_profil": YOGUNLUK[1], "n_normal": YOGUNLUK[2]},
         "hucreler": hucreler,
         "ortalama_Cd_sapma_pct": {"Re3e6": cd3, "Re6e6": cd6},
         "a8_Cl_hata_pct": {"Re3e6": _a8_cl("Re3e6"), "Re6e6": _a8_cl("Re6e6")},
         "R1": r1, "R2": r2, "referansa_yakin": yakin,
         "verdikt": verdikt,
         "_uretim": "Üretim: python experiments/naca0012_re_eslesme.py"}
    KANIT.write_text(json.dumps(o, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + verdikt)
    print(f"-> {KANIT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
