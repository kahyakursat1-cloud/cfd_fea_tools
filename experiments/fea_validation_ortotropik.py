"""FEA doğrulama #6 — ORTOTROPİK malzeme, kapalı-forma karşı.

NEDEN: `calculix_writer` ortotropik malzemeyi yazabiliyor
(`*ELASTIC, TYPE=ENGINEERING CONSTANTS`) ve `laminat.py` kompozit deriyi CLT
eşdeğeriyle bu yola besliyor. Ama beş kapalı-form çapasının HEPSİ izotropik:
kuvvet, basınç, öz-ağırlık, termal, burkulma. Yani ortotropik yol
YAZILIYOR ve sözdizimi birim-testli, ama HİÇBİR ÇAPA onu sınamıyor.

Doğru kartı `.inp`'e yazmak, doğru cevabı almakla aynı şey değildir. Bu boşluk
raporda da yoktu: FEA yetenek tablosu "beşi de kapalı-forma doğrulanmış"
diyordu ve bu DOĞRU, ama ortotropik/kompozit yolunun doğrulanmadığını hiçbir
yer söylemiyordu.

KAPALI FORM: uç yüklü konsol kiriş, lif yönü kiriş ekseninde (1=x).
    delta = P L^3 / (3 E1 I)
Ortotropik katıda eksenel rijitliği E1 belirler; ince/uzun kirişte kayma ve
Poisson düzeltmeleri küçüktür (L/h = 25 seçildi).

AYIRT EDİCİLİK: E1 ile E2 kasıtlı olarak ÇOK farklı (10 kat). İzotropik bir
okuma (ya da eksenlerin karışması) sehimi 10 kat kaydırır ve sınav DÜŞER ---
yani bu çapa gerçekten ortotropiyi sınıyor, yalnız "koştu mu" demiyor.

    python experiments/fea_validation_ortotropik.py
"""
import sys
from pathlib import Path

import gmsh
import meshio
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from analysis.calculix_writer import (  # noqa: E402
    FEACase,
    FEAMaterial,
    FixedBC,
    ForceLoad,
    write_inp,
)
from analysis.ccx_runner import run_ccx  # noqa: E402
from analysis.frd_parser import parse_frd  # noqa: E402
from analysis.tet_mesher import TetMesh  # noqa: E402

# Kiris: x boyunca L, kesit b x h. L/h = 25 -> Euler-Bernoulli gecerli.
L, B, H = 0.500, 0.020, 0.020
P = 200.0                                  # uc yuku (N), -z

# Tek yonlu karbon/epoksi mertebesinde ortotropik takim (Pa).
# 1 = lif/kiris ekseni (x), 2 = aciklik (y), 3 = kalinlik (z).
E1, E2, E3 = 135e9, 10e9, 10e9
NU12, NU13, NU23 = 0.28, 0.28, 0.40
G12, G13, G23 = 5.0e9, 5.0e9, 3.5e9
RHO = 1600.0

I_KESIT = B * H ** 3 / 12.0
DELTA_AN = P * L ** 3 / (3.0 * E1 * I_KESIT)      # m
# IZOTROPIK YANLIS-OKUMA hangi sehimi verirdi — ayirt ediciligin olcusu
DELTA_E2 = P * L ** 3 / (3.0 * E2 * I_KESIT)


def build_mesh(work: Path) -> TetMesh:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.addBox(0, 0, 0, L, B, H)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", H / 2)
        gmsh.option.setNumber("Mesh.MeshSizeMax", H)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / "ort.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    tet = next(c for c in m.cells if c.type == "tetra10")
    return TetMesh(points=m.points.astype(np.float64), tets=tet.data.astype(np.int64),
                   surface_tris=np.zeros((0, 6), np.int64), msh_path=msh,
                   element_type="C3D10")


def main():
    # TURKCE KONSOLDA UnicodeEncodeError ile dusmesin: bu betik ASCII-disi
    # basiyor (derece isareti, Turkce harfler) ve Windows cp1254 konsolunda
    # akis cevrilmezse cokerdi.
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    work = HERE.parent / "_fea_val_ort"
    work.mkdir(exist_ok=True)
    print(f"Analitik (E1={E1 / 1e9:.0f} GPa): delta = P L^3 / (3 E1 I) = "
          f"{DELTA_AN * 1e3:.4f} mm", flush=True)
    print(f"AYIRT EDICILIK: E2 ({E2 / 1e9:.0f} GPa) okunsaydi "
          f"{DELTA_E2 * 1e3:.4f} mm olurdu ({DELTA_E2 / DELTA_AN:.1f} kat)",
          flush=True)

    mesh = build_mesh(work)
    print(f"Mesh: {mesh.num_nodes:,} dugum, {mesh.num_tets:,} C3D10", flush=True)

    pts = mesh.points
    kok = np.where(np.abs(pts[:, 0]) < 1e-9)[0] + 1
    uc = np.where(np.abs(pts[:, 0] - L) < 1e-9)[0] + 1
    if len(kok) == 0 or len(uc) == 0:
        print("kok/uc dugumu bulunamadi"); return 1

    mat = FEAMaterial("KOMPOZIT_UD", E1, NU12, RHO,
                      engineering_constants=(E1, E2, E3, NU12, NU13, NU23,
                                             G12, G13, G23))
    # Uc yuku: ForceLoad toplam kuvveti dugumlere KENDI dagitir.
    case = FEACase(name="ort", mesh=mesh, material=mat,
                   fixed_bcs=[FixedBC(kok, "KOK", 1, 3)],
                   force_loads=[ForceLoad(uc, (0.0, 0.0, -1.0), P, "UC")],
                   analysis_type="STATIC")
    inp = write_inp(case, work)
    metin = Path(inp).read_text(encoding="utf-8", errors="replace")
    if "*ELASTIC, TYPE=ENGINEERING CONSTANTS" not in metin:
        print("HATA: .inp ortotropik blok TASIMIYOR — sinav anlamsiz"); return 1

    ccx = run_ccx(inp, timeout=900)
    if not ccx.success:
        print("CCX FAILED:", (ccx.stderr or ccx.stdout or "")[-400:]); return 1

    frd = parse_frd(ccx.frd_path)
    disp = frd.displacement_magnitude()
    d_fem = float(disp.max()) if disp is not None else None
    if d_fem is None:
        print("FRD'de deplasman yok"); return 1
    hata = abs(d_fem - DELTA_AN) / DELTA_AN * 100
    ayirt = abs(d_fem - DELTA_E2) / DELTA_E2 * 100
    print(f"FEM: delta={d_fem * 1e3:.4f} mm | E1 kapali-formuna hata %{hata:.1f} "
          f"| E2 okumasindan uzaklik %{ayirt:.0f}", flush=True)

    # Esik %15: kayma deformasyonu ve kok-mesnet lokal etkisi ince kiriste
    # birkac yuzde katar; diger FEA capalari da ayni esigi kullaniyor.
    ok = hata < 15.0 and ayirt > 50.0
    sonuc = (f"GECTI — %{hata:.1f}. Doğrular: ÜRETİMin ORTOTROPİK malzeme yolu "
             "(engineering_constants → *ELASTIC, TYPE=ENGINEERING CONSTANTS). "
             "Beş izotropik çapaya ek 6. mekanizma; laminat.py'nin CLT "
             "eşdeğer-kompozit yolu artık kapalı-formla bağlı."
             ) if ok else (
        f"TOLERANS DIŞI — hata %{hata:.1f}, ayırt edicilik %{ayirt:.0f}")
    print("SONUC:", sonuc, flush=True)

    import json

    import ortam
    _kayit = {
            "vaka": "Ortotropik konsol kiriş — kapalı-form (P L³ / 3 E1 I)",
            "yontem": ("ÜRETİM ORTOTROPİK yolu: FEAMaterial(engineering_constants) "
                       "→ *ELASTIC, TYPE=ENGINEERING CONSTANTS (calculix_writer) → "
                       "ccx → frd. Kök ankastre, uç yükü -z."),
            "geometri": {"L_m": L, "b_m": B, "h_m": H, "L_bolu_h": round(L / H, 1),
                         "P_N": P},
            "malzeme": {"E1_Pa": E1, "E2_Pa": E2, "E3_Pa": E3,
                        "nu12": NU12, "nu13": NU13, "nu23": NU23,
                        "G12_Pa": G12, "G13_Pa": G13, "G23_Pa": G23,
                        "rho_kg_m3": RHO,
                        "_not": "tek yönlü karbon/epoksi mertebesinde; "
                                "1=lif/kiriş ekseni (x)"},
            "analitik": {"delta_mm": round(DELTA_AN * 1e3, 4),
                         "formul": "delta = P L^3 / (3 E1 I), I = b h^3 / 12"},
            "fem": {"delta_mm": round(d_fem * 1e3, 4),
                    "delta_hata_pct": round(hata, 2),
                    "dugum": int(mesh.num_nodes),
                    "eleman_C3D10": int(mesh.num_tets)},
            "ayirt_edicilik": {
                "E2_okunsaydi_delta_mm": round(DELTA_E2 * 1e3, 4),
                "kat": round(DELTA_E2 / DELTA_AN, 1),
                "fem_E2_okumasindan_uzaklik_pct": round(ayirt, 1),
                "_neden": ("E1 ve E2 kasitli olarak 13,5 kat farkli secildi. "
                           "Izotropik bir okuma ya da eksenlerin karismasi "
                           "sehimi o kadar kaydirir ve sinav DUSER — yani bu "
                           "capa gercekten ortotropiyi siniyor, yalniz "
                           "'kostu mu' demiyor."),
            },
            "sonuc": sonuc,
            "_kisit": ("Eksenler GLOBAL cercevede (yazici *ORIENTATION yazmiyor); "
                       "lif yonu kiriş eksenine hizali secildi. Egik lif yonu "
                       "DOGRULANMADI. Ayrica bu bir DUZLEM-ICI rijitlik sinavi; "
                       "katmanlar arasi (interlaminar) kayma ve delaminasyon "
                       "KAPSAM DISI."),
            # `_uretim` ALANI ZORUNLU: damga basan dosya, damgayi URETIM aninda
            # bastigini gosterebilmeli (test_ESKI_kanitlar_toplu_damgalanmadi).
            # Diger FEA capalari damgasiz oldugu icin `_not` ile yetinebiliyor.
            "_uretim": "Üretim: python experiments/fea_validation_ortotropik.py",
            "_not": "Üretim: python experiments/fea_validation_ortotropik.py",
    }
    # ORTAM DAMGASI URETIM ANINDA. Diger bes FEA capasi damgasiz (damga onlardan
    # SONRA eklendi); yenisi kendi olcutunun disinda kalmamali.
    ortam.damgala(_kayit)
    (HERE.parent / "fea_validation_ortotropik.json").write_text(
        json.dumps(_kayit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
