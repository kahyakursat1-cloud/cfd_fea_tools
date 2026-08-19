"""FEA eleman-mertebesi etkisi — C3D4 (linear tet) vs C3D10 (quadratic tet) BÜKÜLMEDE.
Üretim araç-FEA'sı second_order=False (C3D4) kullanır; V&V ise C3D10. Linear tet bükülmede
shear-locking'le AŞIRI KATI → sehimi düşük tahmin (güvensiz: gerçek sehim daha büyük).
Bu script ankastre kirişi (Euler-Bernoulli δ=PL³/3EI analitik) her iki elemanla, birkaç
mesh-inceliğinde koşup C3D4'ün hata payını NİCELER → "üretimi C3D10'a geçirelim mi"yi
veriye bağlar. Kanonik V&V'ye (fea_validation.json, C3D8I hex %1) ek: tet-mertebe ekseni.
Kullanım: python experiments/fea_element_order.py
"""
import json
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

L, B, H = 1.0, 0.05, 0.05                  # m — kiriş boyu, kesit (narinlik L/H=20)
E, NU, RHO, P = 70e9, 0.33, 2700.0, 1000.0  # alüminyum, uç yük (N), -z
I_SEC = B * H ** 3 / 12.0
DELTA_AN_MM = P * L ** 3 / (3 * E * I_SEC) * 1e3      # Euler-Bernoulli uç sehim (mm)


def build_mesh(work: Path, size: float, order: int) -> TetMesh:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.addBox(0, 0, 0, L, B, H)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMin", size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.ElementOrder", order)
        if order == 2:
            gmsh.option.setNumber("Mesh.HighOrderOptimize", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        msh = work / f"beam_o{order}_{size:.4f}.msh"
        gmsh.write(str(msh))
    finally:
        gmsh.finalize()
    m = meshio.read(str(msh))
    ctype = "tetra10" if order == 2 else "tetra"
    etype = "C3D10" if order == 2 else "C3D4"
    tet = next(c for c in m.cells if c.type == ctype)
    ncol = 6 if order == 2 else 3
    return TetMesh(points=m.points.astype(np.float64), tets=tet.data.astype(np.int64),
                   surface_tris=np.zeros((0, ncol), np.int64), msh_path=msh, element_type=etype)


def run_case(work: Path, size: float, order: int) -> dict | None:
    mesh = build_mesh(work, size, order)
    pts = mesh.points
    tol = 1e-7
    root = np.where(np.abs(pts[:, 0] - 0.0) < tol)[0] + 1      # x=0 ankastre
    tip = np.where(np.abs(pts[:, 0] - L) < tol)[0] + 1          # x=L uç yük
    mat = FEAMaterial("AL", E, NU, RHO)
    case = FEACase(name=f"beam_o{order}", mesh=mesh, material=mat,
                   fixed_bcs=[FixedBC(root, "FIX", 1, 3)],
                   force_loads=[ForceLoad(tip, (0.0, 0.0, -1.0), P, "TIP")],
                   analysis_type="STATIC")
    inp = write_inp(case, work)
    ccx = run_ccx(inp, timeout=1200)
    if not ccx.success:
        return None
    frd = parse_frd(ccx.frd_path)
    disp = frd.displacement_magnitude()
    if disp is None:
        return None
    delta_mm = float(disp.max()) * 1e3                          # uç en çok sehir
    err = (delta_mm - DELTA_AN_MM) / DELTA_AN_MM * 100          # işaretli: <0 = çok katı

    # GERILME EKSENI — SEHIM YETMEZ. Bu betik yalniz sehim olcuyordu, ama
    # `vehicle_topopt` C3D4 aginda hesapladigi tepe gerilmeden GUVENLIK
    # FAKTORU hukmu veriyor. Eleman mertebesinin GERILMEYE etkisi hic
    # olculmemisti; TO'nun ag-marji kapisi ayriklastirma duyarliligindan
    # gelir, eleman mertebesinden DEGIL.
    #
    # ANKASTREDE OLCULMEZ. Kok kesitte gerilme TEKILDIR (ag inceldikce
    # buyur, yakinsamaz) ve kiris formulu orada nominal deger verir. Olcum
    # ORTA ACIKLIKTA yapilir: x=L/2'de M=P·L/2 ve kiris teorisi temizdir.
    # Ayni disiplin burulma capasinda da uygulandi (St. Venant bolgesi).
    # SIGMA(z) DOGRUSALDIR — MEDYAN DEGIL EGIM UYDUR.
    #
    # Ilk surum orta-aciklikta "ust life yakin" bir dilimin MEDYANINI aliyordu:
    #   dilim = |x-L/2| < size  &  z > H - size*0.6
    # Iki kusur vardi ve olculdu (2026-08-19): C3D10 hatasi seviyeler arasinda
    # -49,4 / -6,5 / -46,2 cikti — sacilmis ve MONOTON DEGIL, yani fizik degil
    # olcum artefakti. (a) dilim kalinligi `size`e bagliydi, yani her seviyede
    # farkli bolge; (b) `z > H - size*0.6` TARAFSIZ EKSENE yakin dugumleri de
    # kapsiyordu ve orada sigma -> 0, dolayisiyla medyan sistematik olarak
    # dusuk cikiyordu.
    #
    # Kiris teorisinde x=L/2'de  sigma_xx = M*(z - H/2)/I  ve M = P*L/2. Yani
    # sigma, (z - H/2) ile DOGRUSALDIR ve egim M/I'dir. Egimi uydurmak dugum
    # yerlesiminden bagimsizdir, tum kesiti kullanir ve R^2 ile kendini sinar.
    sig = frd.fields.get("STRESS")
    sig_orta_MPa = sig_hata = sig_r2 = None
    if sig is not None and len(sig):
        kimlik = np.asarray(frd.node_ids, dtype=np.int64)
        xk = pts[kimlik - 1, 0]
        zk = pts[kimlik - 1, 2]
        # DILIM SECIMI TUMUYLE KALDIRILDI. Ince bir x-dilimi C3D4'te yeterli
        # dugum yakalayamiyordu (169-353 dugum vs C3D10'un 906-1875'i) ve
        # olcum "None" donuyordu — dilimi genisletmek ise M'yi degistirip
        # baska bir sapma katardi.
        #
        # Kiris teorisi TUM acikligi tarif eder:  sigma_xx = P*(L-x)*(z-H/2)/I
        # Yani sigma, t = (L-x)*(z-H/2) carpimiyla DOGRUSALDIR ve egim P/I'dir.
        # Bu uydurma dilim yerlesiminden BAGIMSIZDIR, tum kirisi kullanir ve
        # her iki eleman tipinde de ayni sayida serbestlik gerektirir.
        bolge = (xk > 0.2 * L) & (xk < 0.8 * L)      # ankastre ve yuk ucu disarida
        if bolge.sum() >= 10:
            sxx = np.asarray(sig)[bolge, 0]          # S11 = eksenel
            t = (L - xk[bolge]) * (zk[bolge] - H / 2.0)
            egim, kesme = np.polyfit(t, sxx, 1)
            _art = sxx - (egim * t + kesme)
            _tss = float(((sxx - sxx.mean()) ** 2).sum())
            sig_r2 = 1.0 - float((_art ** 2).sum()) / _tss if _tss > 0 else 0.0
            # Egim = P/I; orta aciklik ust lif degerine cevir.
            sig_orta_MPa = float(egim) * (L / 2.0) * (H / 2.0) / 1e6
            sig_orta_an = P * (L / 2.0) * (H / 2.0) / I_SEC / 1e6
            sig_hata = (sig_orta_MPa - sig_orta_an) / sig_orta_an * 100

    return {"eleman": mesh.element_type, "h_m": size, "dugum": mesh.num_nodes,
            "eleman_sayisi": mesh.num_tets, "delta_mm": round(delta_mm, 4),
            "hata_pct": round(err, 1),
            "sigma_orta_MPa": (round(sig_orta_MPa, 3)
                               if sig_orta_MPa is not None else None),
            "sigma_hata_pct": (round(sig_hata, 1)
                               if sig_hata is not None else None),
            "sigma_uydurma_R2": (round(sig_r2, 4) if sig_r2 is not None else None)}


def main():
    work = HERE.parent / "_fea_elem_order"
    work.mkdir(exist_ok=True)
    print(f"Analitik (Euler-Bernoulli): δ=PL³/3EI = {DELTA_AN_MM:.3f} mm "
          f"(I={I_SEC:.3e} m⁴, narinlik L/H={L / H:.0f})", flush=True)
    sizes = [H, H / 1.5, H / 2.0]                               # kaba→ince (kesit-bölme ~1,1.5,2)
    rows = []
    for order in (1, 2):
        for s in sizes:
            r = run_case(work, s, order)
            if r is None:
                print(f"  CCX FAIL eleman-order={order} h={s:.4f}"); continue
            rows.append(r)
            print(f"  {r['eleman']:5s} h={s:.4f} ({r['dugum']:>6,} düğüm, "
                  f"{r['eleman_sayisi']:>6,} elm): δ={r['delta_mm']:.3f} mm "
                  f"(hata %{r['hata_pct']:+.1f})", flush=True)

    c3d4 = [r for r in rows if r["eleman"] == "C3D4"]
    c3d10 = [r for r in rows if r["eleman"] == "C3D10"]
    worst_c3d4 = min((r["hata_pct"] for r in c3d4), default=None)   # en negatif = en katı
    best_c3d10 = min((abs(r["hata_pct"]) for r in c3d10), default=None)

    def _sig(liste):
        v = [r["sigma_hata_pct"] for r in liste if r.get("sigma_hata_pct") is not None]
        return max(v, key=abs) if v else None
    sig4, sig10 = _sig(c3d4), _sig(c3d10)
    rec = {
        "vaka": "Eleman-mertebesi: C3D4 vs C3D10 ankastre kiriş bükülmesi (Euler-Bernoulli)",
        "analitik_delta_mm": round(DELTA_AN_MM, 3),
        "geometri": {"L_m": L, "kesit_m": B, "narinlik": L / H, "E_Pa": E, "P_N": P},
        "kosular": rows,
        "ozet": {
            "C3D4_en_kati_hata_pct": worst_c3d4,
            "C3D10_en_iyi_hata_pct": best_c3d10,
            "yorum": (f"C3D4 (linear, ÜRETİM default) sehimi %{abs(worst_c3d4):.0f}'a kadar "
                      f"DÜŞÜK tahmin (shear-locking → aşırı katı); C3D10 (V&V) analitiğe "
                      f"%{best_c3d10:.1f}. Düşük sehim GÜVENSİZ yöndedir (gerçek deformasyon "
                      "daha büyük). Sonuç: üretim FEA'sı bükülme-baskın yüklerde C3D10 "
                      "kullanmalı — özellikle ince kabuk/kanat-spar gibi narin yapılarda."
                      if worst_c3d4 is not None else "koşu eksik"),
        },
        "gerilme_ekseni": {
            "_neden": (
                "Sehim yetmez: `vehicle_topopt` C3D4 ağında hesapladığı TEPE "
                "GERİLMEDEN güvenlik faktörü hükmü veriyor. Eleman mertebesinin "
                "GERİLMEYE etkisi hiç ölçülmemişti; TO'nun ağ-marjı kapısı "
                "ayrıklaştırma duyarlılığından gelir, eleman mertebesinden DEĞİL."),
            "_nerede_olculdu": (
                "ORTA AÇIKLIK (x=L/2), üst lif. Ankastre kökte gerilme TEKİLDİR "
                "ve yakınsamaz; kiriş formülü orada nominal değer verir. Aynı "
                "disiplin burulma çapasında da uygulandı (St. Venant bölgesi)."),
            "analitik_MPa": round(P * (L / 2.0) * (H / 2.0) / I_SEC / 1e6, 3),
            "C3D4_hata_pct": sig4,
            "C3D10_hata_pct": sig10,
        },
        # BAGLAM NOTU BAYATTI VE DUZELTILDI (2026-08-19): `vehicle_fea` artik
        # second_order=True (C3D10) kullaniyor, yani bu betigin onerdigi gecis
        # URETIM FEA'sinda YAPILMIS. Geriye kalan tek C3D4 tuketicisi
        # `vehicle_topopt` (satir ~294) ve orasi SF HUKMU URETIYOR.
        "_not": ("Üretim: python experiments/fea_element_order.py. "
                 "BAĞLAM (2026-08-19): vehicle_fea ARTIK second_order=True "
                 "(C3D10) — bu betiğin önerdiği geçiş üretim FEA'sında YAPILDI. "
                 "Kalan tek C3D4 tüketicisi vehicle_topopt; orası kompliyans "
                 "döngüsü için meşru (maliyet) AMA aynı ağdan SF hükmü de "
                 "veriyor, ve TO'nun ağ-marjı kapısı eleman mertebesini "
                 "KAPSAMIYOR."),
    }
    (HERE.parent / "fea_element_order.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nÖZET: C3D4 en katı %{worst_c3d4}, C3D10 en iyi %{best_c3d10} "
          "→ fea_element_order.json", flush=True)
    return 0


if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
