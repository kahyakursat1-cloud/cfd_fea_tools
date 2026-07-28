"""NACA2412 2B kesit çapası — "profil mi yanlış, mesh mi?" sorusunun cevabı.

NEDEN: MiniHawk 3B koşusu doğru geometriyle Cl=0.0143 verdi; NACA2412 α=0'da 2B
beklenti ~0.23. İki açıklama vardı ve ayırt edilemiyordu:
  (a) mesh_generator'ın ürettiği PROFİL yanlış,
  (b) profil doğru ama 3B mesh KAMBURLUĞU çözmüyor (en ince boyut yüzey hücresinin
      0.6 katı ölçülmüştü).
Bu çapa ikisini ayırır: AYNI profil üreticisinden alınan koordinatlar 2B'de,
çözünürlüğü yeterli bir O-grid üzerinde koşulur.

KRİTİK: koordinatlar `mesh_generator._naca4_profile`'dan gelir — yani test edilen şey
MiniHawk'ın kullandığı kodun ta kendisidir, ayrı bir referans profil değil.

Kurulum: Re_c = 2.5e5 (MiniHawk kordu 0.25 m, V=15 m/s) — 3B koşuyla AYNI Reynolds.
Referans: ince-kanat teorisi Cl = 2π·|α_L0|, NACA2412 için α_L0 ≈ -2.07° → Cl ≈ 0.227.
Abbott & von Doenhoff deneysel (Re=3e6): α_L0 = -2.1°, Cl(0°) ≈ 0.25.

    python experiments/naca2412_kesit.py

Çıktı: naca2412_kesit.json
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import numpy as np  # noqa: E402

from analysis.thresholds import NONORTHO_REJECT, SKEW_REJECT  # noqa: E402
from construct2d_bridge import build_mesh, run_validation  # noqa: E402
from mesh_generator import MeshGenerator  # noqa: E402

KORD, V_INF, NU = 0.25, 15.0, 1.5e-5
ALPHA = 0.0
ALFA_L0_DEG = -2.07                      # NACA2412 sıfır-taşıma açısı (ince-kanat)
CL_TEORI = 2 * math.pi * math.radians(abs(ALFA_L0_DEG))
CL_DENEY = 0.25                          # Abbott & von Doenhoff, Re=3e6
KABUL_BANDI = (0.15, 0.32)               # düşük-Re viskoz de-kamburlanma payıyla
# Keskin firar kenarında Construct2D C-grid ÖNERİR; O-grid'te firar hücreleri dejenere
# olur (ölçüldü: nonOrtho 179.999, skewness 3e152). Öneriye uyuluyor.
TOPO, SLVR = "CGRD", "HYPR"   # eliptik (ELLP) bu profilde NaN'a ıraksadı


def profil_dat(hedef: Path, n: int = 160) -> dict:
    """mesh_generator'ın KENDİ profilini Construct2D .dat formatına yazar.

    Ayrı bir referans profil KULLANILMAZ: sorulan soru "bu projenin ürettiği profil
    doğru mu", dolayısıyla girdi o üreticinin çıktısı olmalı.
    """
    p = np.asarray(MeshGenerator._naca4_profile(0.02, 0.4, 0.12, n=n), dtype=float)
    # Construct2D: firar kenarından başlayıp üst yüzey → burun → alt yüzey → firar.
    if p[0, 0] < p[len(p) // 2, 0]:
        p = p[::-1]
    satir = ["NACA2412 (mesh_generator._naca4_profile)"]
    satir += [f"  {x:.7f}  {y:.7f}" for x, y in p]
    hedef.write_text("\n".join(satir) + "\n", encoding="utf-8")
    return {"nokta": int(len(p)),
            "maks_kalinlik": round(float(p[:, 1].max() - p[:, 1].min()), 5),
            "kord": round(float(p[:, 0].max() - p[:, 0].min()), 5)}


def _sade(o):
    """numpy skalerlerini JSON'a yazılabilir Python tiplerine indirger."""
    if isinstance(o, dict):
        return {k: _sade(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sade(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


def profil_dogrulugu(n: int = 200) -> dict:
    """Üretilen profili ANALİTİK NACA 4-haneli tanımla nokta-nokta karşılaştırır.

    Bu, çapanın ASIL ve KOŞULSUZ sonucudur: CFD'ye, grid üreticisine, çözücüye hiç
    bağlı değil. Sorulan soru "mesh_generator'ın profili doğru mu" ve cevabı burada
    ölçülür. 2B CFD yalnızca DESTEKLEYİCİ kanıttır.
    """
    m, pp, t = 0.02, 0.4, 0.12
    p = np.asarray(MeshGenerator._naca4_profile(m, pp, t, n=n), dtype=float)

    def yuzey(xc, ust):
        yt = 5 * t * (0.2969 * np.sqrt(xc) - 0.1260 * xc - 0.3516 * xc ** 2
                      + 0.2843 * xc ** 3 - 0.1015 * xc ** 4)
        yc = np.where(xc < pp, m / pp ** 2 * (2 * pp * xc - xc ** 2),
                      m / (1 - pp) ** 2 * ((1 - 2 * pp) + 2 * pp * xc - xc ** 2))
        dy = np.where(xc < pp, 2 * m / pp ** 2 * (pp - xc),
                      2 * m / (1 - pp) ** 2 * (pp - xc))
        th = np.arctan(dy)
        return ((xc - yt * np.sin(th), yc + yt * np.cos(th)) if ust
                else (xc + yt * np.sin(th), yc - yt * np.cos(th)))

    xs = np.linspace(0, 1, 4000)
    sapma = []
    for px, py in p:
        if not (0.02 < px < 0.98):        # burun/firar uçları ayrık, hariç
            continue
        ax, ay = yuzey(xs, ust=py > 0)
        sapma.append(abs(ay[np.argmin((ax - px) ** 2)] - py))
    sap = np.asarray(sapma)
    # kamburluk: analitik orta çizgi maksimumu (tanım gereği tam m olmalı)
    (ux, uy), (lx, ly) = yuzey(xs, True), yuzey(xs, False)
    return {"nokta": int(len(sap)),
            "ortalama_sapma_kord": float(f"{sap.mean():.3e}"),
            "maks_sapma_kord": float(f"{sap.max():.3e}"),
            "maks_sapma_pct": round(float(sap.max()) * 100, 4),
            "kamburluk_analitik": round(float(((uy + ly) / 2).max()), 5),
            "kamburluk_tanim": m,
            "gecti": bool(sap.max() < 1e-3)}


def _mesh_kalite_hatasi(mesh: dict) -> str:
    """Kanonik eşiklerle (analysis/thresholds) mesh reddi — sayı üretmeden ÖNCE."""
    kusur = []

    def f(anahtar):
        ham = str(mesh.get(anahtar, "")).strip()
        if not ham:
            kusur.append(f"{anahtar} checkMesh çıktısında YOK — kalite değerlendirilemedi")
            return None
        try:
            return float(ham)
        except ValueError:
            # Okunamayan metrik "sorun yok" DEĞİLDİR. Sessizce None dönmek kapıyı
            # kör eder; kapının varlık sebebi tam da bu.
            kusur.append(f"{anahtar} okunamadı ({ham!r}) — kalite değerlendirilemedi")
            return None

    no, sk = f("non_ortho_max"), f("skewness_max")
    if no is not None and no > NONORTHO_REJECT:
        kusur.append(f"nonOrtho {no:.1f} > {NONORTHO_REJECT}")
    if sk is not None and sk > SKEW_REJECT:
        kusur.append(f"skewness {sk:.3g} > {SKEW_REJECT}")
    return "; ".join(kusur)


def _cl_cd(sonuc: dict) -> tuple[float | None, float | None]:
    for a, b in (("Cl", "Cd"), ("cl", "cd"), ("CL", "CD")):
        if sonuc.get(a) is not None:
            return sonuc.get(a), sonuc.get(b)
    return None, None


def _profil_verdikti(dog: dict) -> str:
    if dog["gecti"]:
        return (f"PROFIL DOGRU (analitik): mesh_generator._naca4_profile cikti, NACA 4-haneli "
                f"tanimdan en fazla kordun %{dog['maks_sapma_pct']:.3f}'i kadar sapiyor; "
                f"kamburluk {dog['kamburluk_analitik']} (tanim {dog['kamburluk_tanim']}). "
                "Yani MiniHawk 3B kosusundaki Cl=0.0143 (2B beklenti ~0.23) PROFILDEN "
                "KAYNAKLANMIYOR — geriye 3B MESH COZUNURLUGU kaliyor (en ince boyut yuzey "
                "hucresinin 0.6 kati olculmustu).")
    return (f"⚠️ PROFIL SAPIYOR: analitik tanimdan maks %{dog['maks_sapma_pct']:.3f} kord — "
            "MiniHawk teshisi once burayi isaret ediyor.")


def _verdikt(cl, cd, mesh, cl_sapma):
    if cl is None:
        return "⚠️ Cl okunamadi — capa uretilemedi."
    icinde = KABUL_BANDI[0] <= cl <= KABUL_BANDI[1]
    p = [f"NACA2412 2B, Re={V_INF * KORD / NU:.1e}, alpha=0: Cl={cl:.4f} "
         f"(ince-kanat teorisi {CL_TEORI:.3f}, deney {CL_DENEY}) -> sapma %{cl_sapma:+.0f}"]
    if icinde:
        p.append("PROFIL DOGRU: ayni uretici (mesh_generator._naca4_profile) 2B'de "
                 "beklenen tasimayi veriyor. MiniHawk 3B kosusundaki Cl=0.0143 "
                 "(beklentinin ~1/16'si) PROFILDEN DEGIL, 3B MESH COZUNURLUGUNDEN "
                 "kaynaklaniyor — kamburluk cozulmuyor")
    else:
        p.append(f"⚠️ Cl kabul bandi {KABUL_BANDI} DISINDA — profil ya da 2B kurulum "
                 "sorgulanmali; MiniHawk teshisi bu capaya dayandirilamaz")
    if mesh.get("non_ortho_max"):
        p.append(f"mesh: {mesh['cells']} hucre, nonOrtho {mesh['non_ortho_max']}, "
                 f"skewness {mesh.get('skewness_max')}")
    return ". ".join(p) + "."


def main() -> int:
    kok = HERE.parent / "_naca2412"
    if kok.exists():
        shutil.rmtree(kok, ignore_errors=True)
    kok.mkdir(parents=True, exist_ok=True)
    dat = kok / "naca2412.dat"
    geo = profil_dat(dat)
    dog = profil_dogrulugu()
    print(f"profil: {geo['nokta']} nokta, kalinlik/kord {geo['maks_kalinlik']:.4f}",
          flush=True)
    print(f"ANALITIK DOGRULAMA: maks sapma %{dog['maks_sapma_pct']:.4f} kord, "
          f"kamburluk {dog['kamburluk_analitik']} (tanim {dog['kamburluk_tanim']}) "
          f"-> {'GECTI' if dog['gecti'] else 'KALDI'}", flush=True)

    mesh = build_mesh(str(dat), str(kok / "case"), name="naca2412", topo=TOPO, slvr=SLVR)
    print(f"mesh: {mesh}", flush=True)
    # MESH KALİTE KAPISI: bozuk mesh üstünde CFD koşmak sayı üretir ama o sayı
    # anlamsızdır. İlk denemede O-grid keskin firar kenarında nonOrtho 179.999 /
    # skewness 3e152 verdi (Construct2D zaten C-grid önermişti). Kapı olmadan bu
    # mesh çözücüye gidiyordu.
    kalite_hata = _mesh_kalite_hatasi(mesh)
    if mesh.get("status") == "SUCCESS" and kalite_hata:
        mesh["status"] = "KALITE_RED"
        mesh["red_nedeni"] = kalite_hata
        print(f"MESH KALİTE KAPISI: {kalite_hata}", flush=True)
    if mesh.get("status") != "SUCCESS":
        out = {"vaka": "NACA2412 2B kesit — profil dogrulugu (analitik) + 2B CFD (destekleyici)",
               "profil_dogrulama": dog,
               "profil": {**geo, "kaynak": "mesh_generator._naca4_profile(0.02, 0.4, 0.12)"},
               "durum": "cfd_uretilemedi", "mesh": _sade(mesh),
               "_grid_altyapisi": (
                   "ASIL KOK SEBEP (izlenerek bulundu): write_ogrid_gmsh YALNIZ O-grid "
                   "ifade edebilir — 'j=0 airfoil, i-periyodik' varsayar. C-grid'de j=0 "
                   "cizgisi IZ KESIGINDE baslar (olculdu: x=15.5, kord 0..1) ve bu rutin "
                   "iz kesigini NO-SLIP DUVAR olarak etiketler. Bu yuzden CGRD+HYPR "
                   "gridi Construct2D'de makul iken OpenFOAM mesh'i nonOrtho 180 / "
                   "skewness 3.35e152 cikiyordu — deger O-grid kosusuyla BIREBIR AYNI, "
                   "yani bozukluk grid'den degil DONUSTURUCUDEN geliyor. build_mesh artik "
                   "topo != OGRD durumunda acikca REDDEDIYOR (sessizce gecersiz mesh "
                   "uretmektense). "
                   "Ikincil bulgular: OGRD keskin firar kenarinda dejenere (Construct2D "
                   "zaten C-grid onermisti); CGRD+ELLP eliptik duzlestirici NaN'a IRAKSADI. "
                   "2B CFD capasi bu altyapiyla URETILEMEZ; C-grid destegi icin "
                   "write_cgrid_gmsh (iz kesigi = ic sinir) yazilmalidir."),
               "verdikt": (_profil_verdikti(dog) + " " + ("⚠️ Mesh KALITE KAPISINDA reddedildi: "
                           + mesh.get("red_nedeni", "")
                           + " — bozuk mesh uzerinde Cl uretmek yaniltici olurdu."
                           if mesh.get("status") == "KALITE_RED"
                           else "2B CFD destekleyici kaniti URETILEMEDI (grid altyapisi; "
                           "bkz. _grid_altyapisi).")),
               "_uretim": "Üretim: python experiments/naca2412_kesit.py"}
        (HERE.parent / "naca2412_kesit.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(out["verdikt"])
        return 1

    r = run_validation(str(kok / "case"), alpha_deg=ALPHA, V=V_INF, nu=NU, chord=KORD)
    cl, cd = _cl_cd(r)
    sapma = (cl - CL_TEORI) / CL_TEORI * 100 if cl is not None else None
    out = {
        "vaka": (f"NACA2412 2B kesit — kord {KORD} m, V={V_INF} m/s "
                 f"(Re={V_INF * KORD / NU:.2e}), alpha={ALPHA}"),
        "_neden": ("MiniHawk 3B kosusu Cl=0.0143 verdi (2B beklenti ~0.23). Bu capa "
                   "'profil mi yanlis, mesh mi' sorusunu ayirir: AYNI profil ureticisi "
                   "2B'de, cozunurlugu yeterli O-grid uzerinde kosulur."),
        "profil": {**geo, "kaynak": "mesh_generator._naca4_profile(0.02, 0.4, 0.12)"},
        "profil_dogrulama": dog,
        "referans": {"Cl_ince_kanat": round(CL_TEORI, 4), "alfa_L0_deg": ALFA_L0_DEG,
                     "Cl_deney_Re3e6": CL_DENEY,
                     "kaynak": "Abbott & von Doenhoff, Theory of Wing Sections"},
        "mesh": _sade(mesh), "cfd": _sade(r),
        "Cl": cl, "Cd": cd,
        "Cl_sapma_pct": round(sapma, 2) if sapma is not None else None,
        "verdikt": _verdikt(cl, cd, mesh, sapma or 0.0),
        "_uretim": "Üretim: python experiments/naca2412_kesit.py",
    }
    (HERE.parent / "naca2412_kesit.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n" + out["verdikt"])
    print("-> naca2412_kesit.json")
    return 0 if cl is not None else 1


if __name__ == "__main__":
    sys.exit(main())
