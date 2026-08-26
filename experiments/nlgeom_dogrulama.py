"""NLGEOM DOĞRULANIR — eklenmiş olması çalıştığı anlamına gelmez.

NEDEN VAR. Büyük yer-değiştirme yeteneği `analysis/calculix_writer` içine
eklendi (`*STEP, NLGEOM` + artımlı yük). Bir bayrağı yazmak kolaydır ve
sessizce hiçbir şey yapmayabilir: CalculiX kartı kabul eder, koşu düşmez,
sonuç lineer kalır. Bu depoda ``eklendi'' ile ``çalışıyor'' aynı şey
değildir.

ÇAPA: ANKASTRE KİRİŞ, UÇTAN TEKİL YÜK (elastika).
Lineer kiriş teorisi $\\delta = PL^3/(3EI)$ verir ve sehim büyüdükçe
BİLİNEN bir hata yapar: gerçek kiriş kısalır (uç yatayda geri çekilir) ve
moment kolu küçülür, yani lineer teori sehimi FAZLA tahmin eder. Kesin
çözüm Bisshopp \\& Drucker (1945) elastikasıdır; burada aynı problem
sayısal olarak (elastika ODE'si) çözülüp referans üretilir.

ÜÇ ŞEY BİRDEN SINANIR --- biri eksikse doğrulama değildir:
  1. KÜÇÜK yükte NLGEOM lineere İNDİRGENİYOR mu? İndirgenmiyorsa yetenek
     değil KUSUR eklenmiştir.
  2. BÜYÜK yükte lineerden AYRIŞIYOR mu ve DOĞRU YÖNDE mi (daha az sehim)?
  3. Ayrışma bir REFERANSA yaklaşıyor mu? Yalnız ``farklı çıktı'' demek,
     yanlış bir farkı doğrulama sayardı.

    python experiments/nlgeom_dogrulama.py
Çıktı: nlgeom_dogrulama.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "nlgeom_dogrulama.json"

# Ince kiris: L=1 m, b=h ile dikdortgen kesit. Ince olmasi SART --- kalin
# kiriste kayma deformasyonu girer ve elastika referansi gecerliligini
# yitirir (Euler-Bernoulli varsayimi).
L_M = 1.0
B_M = 0.02
H_M = 0.01
E_PA = 70e9
# Boyutsuz yuk alpha = P L^2 / (E I). Kucuk uc lineer rejim, buyuk uc
# elastikanin lineerden belirgin ayristigi rejim.
ALFALAR = (0.05, 0.5, 1.0, 2.0, 3.0)
# Kucuk-yuk indirgeme esigi: bu alfada NLGEOM ile lineer bu kadar yakin
# olmali. Elastikanin kendisi de bu alfada lineerden ~%0,1 sapar, yani
# esik SIFIR OLAMAZ ve bu beyan edilmistir.
INDIRGEME_ALFA = ALFALAR[0]
INDIRGEME_ESIGI_PCT = 1.0


def _I() -> float:
    return B_M * H_M ** 3 / 12.0


def lineer_sehim(alfa: float) -> float:
    """delta = P L^3 / (3 E I), P = alfa E I / L^2  ->  delta/L = alfa/3."""
    return alfa / 3.0


def elastika(alfa: float, n: int = 20000) -> dict:
    """Ankastre kirişin BÜYÜK sehim çözümü --- elastika ODE'si.

    Uc yukunde moment M(s) = P (x_uc - x(s)), yani
        dθ/ds' = α (x'_uc - x'(s')),  dx'/ds' = cos θ,  dy'/ds' = sin θ
    burada α = P L² / (EI) ve s' = s/L. x'_uc çözümün KENDİSİNDEN gelir, o
    yüzden sabit-nokta yinelemesi var.

    RK2 (orta nokta) kullanılır; Euler n=4000'de bile görünür hata verdi.
    """
    ds = 1.0 / n

    def _ilerlet(x_uc: float) -> tuple[float, float, float]:
        th = x = y = 0.0
        for _ in range(n):
            dth1 = alfa * (x_uc - x)
            th_m = th + 0.5 * ds * dth1
            x_m = x + 0.5 * ds * math.cos(th)
            y_m = y + 0.5 * ds * math.sin(th)
            dth2 = alfa * (x_uc - x_m)
            th += ds * dth2
            x += ds * math.cos(th_m)
            y += ds * math.sin(th_m)
            _ = y_m
        return x, y, th

    x_uc = 1.0
    for _ in range(500):
        x, y, th = _ilerlet(x_uc)
        if abs(x - x_uc) < 1e-13:
            break
        x_uc = 0.5 * (x_uc + x)
    return {"delta_y_bolu_L": y, "x_uc_bolu_L": x, "uc_egimi_rad": th}


# C3D10 KENAR SIRASI (gmsh = CalculiX/Abaqus): 5=(0,1) 6=(1,2) 7=(2,0)
# 8=(0,3) 9=(1,3) 10=(2,3). `tet_mesher` de bu esitligi kullaniyor.
_KENARLAR = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))


def _c3d10(P: np.ndarray, tets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """C3D4 ağını C3D10'a yükselt --- kenar orta noktaları eklenerek.

    NEDEN ZORUNLU. Ilk surum C3D4 kullandi ve alfa=1'de sehim 0,041 cikti;
    beklenen 0,30. Sekiz kat sapma NLGEOM'dan DEGIL, LINEER TETIN EGILMEDE
    KILITLENMESINDEN geliyordu --- sabit-gerinim eleman egilmeyi temsil
    edemez. O agla olculen sey NLGEOM degil ELEMANIN KUSURU olurdu ve
    "NLGEOM neredeyse hicbir sey degistirmiyor" diye YANLIS bir dogrulama
    uretirdi. Deponun uretim elemani zaten C3D10.
    """
    yeni: dict[tuple[int, int], int] = {}
    ek: list[tuple[float, float, float]] = []
    n0 = len(P)
    out = np.zeros((len(tets), 10), int)
    out[:, :4] = tets
    for e, t in enumerate(tets):
        for k, (a, b) in enumerate(_KENARLAR):
            i, j = int(t[a]), int(t[b])
            anahtar = (min(i, j), max(i, j))
            if anahtar not in yeni:
                yeni[anahtar] = n0 + len(ek)
                ek.append(tuple((P[i] + P[j]) / 2.0))
            out[e, 4 + k] = yeni[anahtar]
    return (np.vstack([P, np.array(ek, float)]) if ek else P), out


def _kiris_agi(nx: int = 40, ny: int = 4, nz: int = 4):
    """Ankastre kiriş için yapılandırılmış hexa->tet ağı."""
    from analysis.tet_mesher import TetMesh
    xs = np.linspace(0.0, L_M, nx + 1)
    ys = np.linspace(-B_M / 2, B_M / 2, ny + 1)
    zs = np.linspace(-H_M / 2, H_M / 2, nz + 1)
    P, indeks = [], {}
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            for k, z in enumerate(zs):
                indeks[(i, j, k)] = len(P)
                P.append((x, y, z))
    tets = []
    # Her hexa 6 tete --- kanonik ayrisim.
    kesim = ((0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4),
             (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7))
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                c = [indeks[(i + (a & 1), j + ((a >> 1) & 1), k + ((a >> 2) & 1))]
                     for a in range(8)]
                for t in kesim:
                    tets.append([c[t[0]], c[t[1]], c[t[2]], c[t[3]]])
    # YUZEY UCGENLERI: bu capada basinc yuku YOK (tekil kuvvet), ama TetMesh
    # alani zorunlu. Kutu yuzeyi ucgenlenmez --- bos birakilir ve bunun
    # NEDEN gecerli oldugu burada yazilir: `write_inp` yuzey ucgenlerini
    # yalniz *DLOAD/basinc icin kullanir.
    pts, t10 = _c3d10(np.array(P, float), np.array(tets, int))
    return TetMesh(points=pts, tets=t10,
                   surface_tris=np.empty((0, 6), int),
                   msh_path=Path("nlgeom_dogrulama_sentetik.msh"),
                   element_type="C3D10")


def kos(alfa: float, nlgeom: bool, work: Path) -> dict:
    """CalculiX'i sür ve uç sehimini oku."""
    from analysis.calculix_writer import (
        FEACase,
        FEAMaterial,
        FixedBC,
        ForceLoad,
        write_inp,
    )
    from analysis.ccx_runner import run_ccx
    from analysis.frd_parser import parse_frd

    mesh = _kiris_agi()
    P = alfa * E_PA * _I() / L_M ** 2
    ankastre = np.where(mesh.points[:, 0] < 1e-9)[0] + 1
    uc = np.where(mesh.points[:, 0] > L_M - 1e-9)[0] + 1
    case = FEACase(
        name=f"kiris_a{alfa:g}_{'nl' if nlgeom else 'lin'}".replace(".", "p"),
        mesh=mesh,
        material=FEAMaterial(name="al", youngs_modulus_pa=E_PA,
                                poisson_ratio=0.33,
                                density_kg_m3=2700.0),
        fixed_bcs=[FixedBC(node_ids=ankastre, name="ANKASTRE")],
        force_loads=[ForceLoad(node_ids=uc, direction=(0.0, 0.0, -1.0),
                               total_force_n=P, name="UC")],
        nlgeom=nlgeom,
    )
    d = work / case.name
    try:
        inp = write_inp(case, d)
        r = run_ccx(inp)
    except Exception as e:                       # noqa: BLE001
        # SESSIZ YUTMA DEGIL: sebep KAYDA gecer. Bir seviyenin dusmesi
        # dogrulamayi durdurmamali ama GORUNMEZ de olmamali.
        return {"kosdu": False, "neden": f"{type(e).__name__}: {e}"[:200]}
    if not r.success:
        return {"kosdu": False, "neden": (r.stderr or r.stdout)[-200:]}
    frd = parse_frd(r.frd_path)
    if "DISP" not in frd.fields:
        return {"kosdu": False, "neden": "frd'de DISP alanı yok"}
    # DUGUM SIRASI FRD'DEN OKUNUR, varsayilmaz.
    sira = {int(nid): i for i, nid in enumerate(frd.node_ids)}
    idx = [sira[int(n)] for n in uc if int(n) in sira]
    if not idx:
        return {"kosdu": False, "neden": "uç düğümleri frd'de bulunamadı"}
    u = frd.fields["DISP"]
    return {"kosdu": True, "P_N": round(P, 4),
            "delta_z_bolu_L": float(-u[idx, 2].mean() / L_M),
            "uc_x_kisalmasi_bolu_L": float(-u[idx, 0].mean() / L_M)}


def olc() -> dict:
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="nlgeom_"))
    kayit = []
    for alfa in ALFALAR:
        lin = kos(alfa, False, work)
        nl = kos(alfa, True, work)
        ref = elastika(alfa)
        k = {"alfa": alfa, "lineer_teori": round(lineer_sehim(alfa), 6),
             "elastika_ref": round(ref["delta_y_bolu_L"], 6),
             "lineer_fea": lin, "nlgeom_fea": nl}
        if lin and lin.get("kosdu") and nl and nl.get("kosdu"):
            k["nl_vs_lin_fark_pct"] = round(
                100 * (lin["delta_z_bolu_L"] - nl["delta_z_bolu_L"])
                / max(abs(lin["delta_z_bolu_L"]), 1e-30), 3)
            k["nl_vs_elastika_pct"] = round(
                100 * (nl["delta_z_bolu_L"] - ref["delta_y_bolu_L"])
                / max(abs(ref["delta_y_bolu_L"]), 1e-30), 3)
            k["lin_vs_elastika_pct"] = round(
                100 * (lin["delta_z_bolu_L"] - ref["delta_y_bolu_L"])
                / max(abs(ref["delta_y_bolu_L"]), 1e-30), 3)
        kayit.append(k)
    return _ozetle(kayit, work)


def _ozetle(kayit: list, work: Path) -> dict:
    kosan = [k for k in kayit if "nl_vs_lin_fark_pct" in k]
    kucuk = next((k for k in kosan if k["alfa"] == INDIRGEME_ALFA), None)
    buyuk = kosan[-1] if kosan else None
    indirgeniyor = (kucuk is not None
                    and abs(kucuk["nl_vs_lin_fark_pct"]) < INDIRGEME_ESIGI_PCT)
    ayrisiyor = buyuk is not None and buyuk["nl_vs_lin_fark_pct"] > 1.0
    yaklasiyor = (buyuk is not None
                  and abs(buyuk["nl_vs_elastika_pct"])
                  < abs(buyuk["lin_vs_elastika_pct"]))
    return {
        "vaka": "NLGEOM doğrulaması — ankastre kiriş, elastika çapası",
        "_neden": ("Bir bayragi yazmak kolaydir ve sessizce hicbir sey "
                   "yapmayabilir: CalculiX karti kabul eder, kosu dusmez, "
                   "sonuc lineer kalir. 'Eklendi' ile 'calisiyor' ayni sey "
                   "degildir."),
        "kiris": {"L_m": L_M, "b_m": B_M, "h_m": H_M, "E_Pa": E_PA,
                  "_ince_mi": "L/h = %.0f --- Euler-Bernoulli gecerli" % (L_M / H_M)},
        "seviyeler": kayit,
        "kosan_seviye": len(kosan),
        "kucuk_yukte_lineere_INDIRGENIYOR": bool(indirgeniyor),
        "buyuk_yukte_AYRISIYOR": bool(ayrisiyor),
        "ayrisma_REFERANSA_yaklasiyor": bool(yaklasiyor),
        "dogrulandi": bool(indirgeniyor and ayrisiyor and yaklasiyor),
        "verdikt": _hukum(kosan, kucuk, buyuk, indirgeniyor, ayrisiyor,
                          yaklasiyor),
        "_kisit": (
            "Elastika referansi ANALITIK degil SAYISALDIR (elastika ODE'si "
            "RK2 ile, n=4000) --- Bisshopp & Drucker'in kapali formu elde "
            "dogrulanmadi. Ayrica referans Euler-Bernoulli'dir: kayma "
            "deformasyonu ve kesit carpilmasi YOK, FEA'da VAR. L/h=100 "
            "secildi ki bu fark kucuk kalsin ama SIFIR degildir. Ag "
            "bagimsizligi SINANMADI; tek ag."),
        "_uretim": "Üretim: python experiments/nlgeom_dogrulama.py",
        "_calisma_dizini": str(work),
    }


def _hukum(kosan, kucuk, buyuk, indirgeniyor, ayrisiyor, yaklasiyor) -> str:
    if not kosan:
        return "HİÇBİR SEVİYE KOŞMADI — CalculiX sürülemedi, doğrulama YOK."
    s = (f"{len(kosan)}/{len(ALFALAR)} seviye koştu. "
         f"KÜÇÜK YÜK (α={kucuk['alfa']}): NLGEOM ile lineer arasında "
         f"%{kucuk['nl_vs_lin_fark_pct']} fark --- ")
    s += ("indirgeme SAĞLANDI. " if indirgeniyor
          else f"eşik %{INDIRGEME_ESIGI_PCT} AŞILDI; bayrak küçük sehimde de "
               "sonucu değiştiriyor, yani yetenek değil KUSUR eklenmiş "
               "olabilir. ")
    s += (f"BÜYÜK YÜK (α={buyuk['alfa']}): lineer {buyuk['lineer_fea']['delta_z_bolu_L']:.4f}, "
          f"NLGEOM {buyuk['nlgeom_fea']['delta_z_bolu_L']:.4f}, elastika "
          f"{buyuk['elastika_ref']:.4f} (δ/L). ")
    if not ayrisiyor:
        return s + ("NLGEOM lineerden AYRIŞMIYOR --- bayrak yazılıyor ama "
                    "çözümü değiştirmiyor. YETENEK DOĞRULANMADI.")
    s += (f"Lineer referanstan %{buyuk['lin_vs_elastika_pct']:.1f} sapıyor, "
          f"NLGEOM %{buyuk['nl_vs_elastika_pct']:.1f}. ")
    if not yaklasiyor:
        return s + ("Ayrışma var ama YANLIŞ YÖNDE: NLGEOM referanstan lineerden "
                    "DAHA uzak. YETENEK DOĞRULANMADI.")
    return s + ("Üç ölçüt de sağlandı: küçük yükte lineere indirgeniyor, "
                "büyük yükte ayrışıyor ve ayrışma REFERANSA yaklaşıyor. "
                "NLGEOM DOĞRULANDI.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
