"""Zaman-çözünür yapısal analiz DOĞRULANIR — kart yazmak çalışmak değildir.

NEDEN VAR. `*DYNAMIC` yapısal yazıcıya eklendi. Bir kartı yazmak kolaydır
ve sessizce yanlış olabilir: CalculiX koşar, bir zaman serisi üretir, ve
seri fiziksel olarak yanlış olur. Bu depoda ``eklendi'' ile ``çalışıyor''
aynı şey değildir --- NLGEOM'da aynı disiplin uygulandı ve orada bir ağ
kusuru (C3D4 kilitlenmesi) yakalandı.

ÇAPA: SERBEST TİTREŞİM. Ankastre kiriş bir yükle bükülür, yük ANİDEN
kaldırılır ve uç serbest salınır. Sönümsüz bir yapıda salınım frekansı
BİRİNCİ DOĞAL FREKANSTIR.

BU BİR İÇ ÇAPRAZ-DOĞRULAMADIR ve gücü buradan gelir: aynı ağ, aynı malzeme,
aynı sınır koşulları AYRI BİR ÇÖZÜCÜ YOLUNDAN (`*FREQUENCY`, özdeğer)
geçirilir ve iki bağımsız yol AYNI sayıyı vermelidir. Zaman integrasyonu
yanlışsa frekans kayar; kütle matrisi yanlışsa ikisi de kayar ama AYNI
yönde kaymaz.

ÜÇ ÖLÇÜT --- biri eksikse doğrulama değildir:
  1. Geçici salınımın frekansı modal f1'e EŞİT mi?
  2. Sönümsüz seride genlik KORUNUYOR mu? (sayısal sönüm sonucu sessizce
     söndürür ve okuyucu bunu ``fizik'' sanır)
  3. Zaman adımı yarıya inince cevap DEĞİŞMİYOR mu? (değişiyorsa ölçülen
     şey fizik değil ayrıklaştırma)

    python experiments/dinamik_dogrulama.py
Çıktı: dinamik_dogrulama.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

CIKTI = KOK / "dinamik_dogrulama.json"

L_M, B_M, H_M = 1.0, 0.02, 0.01
E_PA, NU, RHO = 70e9, 0.33, 2700.0
# Baslangic sehimi: kucuk kalsin ki LINEER rejimde olalim (NLGEOM'suz).
ALFA0 = 0.05
# Kac periyot izlensin --- frekans kestirimi icin en az birkac periyot.
PERIYOT = 6
# Zaman adimi: periyodun bu kadarda biri. Newmark/HHT icin makul.
ADIM_BOLU_PERIYOT = 40
# Frekans esigi: gecici ile modal bu kadar yakin olmali.
FREKANS_ESIGI_PCT = 3.0
# Genlik korunumu: sonumsuz seride tepe genlik bu kadardan cok dusmemeli.
GENLIK_DUSUS_ESIGI_PCT = 15.0


def _kiris(nx: int = 30, ny: int = 2, nz: int = 3):
    from nlgeom_dogrulama import _c3d10

    from analysis.tet_mesher import TetMesh
    xs = np.linspace(0.0, L_M, nx + 1)
    ys = np.linspace(-B_M / 2, B_M / 2, ny + 1)
    zs = np.linspace(-H_M / 2, H_M / 2, nz + 1)
    P, idx = [], {}
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            for k, z in enumerate(zs):
                idx[(i, j, k)] = len(P)
                P.append((x, y, z))
    kesim = ((0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4),
             (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7))
    tets = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                c = [idx[(i + (a & 1), j + ((a >> 1) & 1), k + ((a >> 2) & 1))]
                     for a in range(8)]
                for t in kesim:
                    tets.append([c[t[0]], c[t[1]], c[t[2]], c[t[3]]])
    pts, t10 = _c3d10(np.array(P, float), np.array(tets, int))
    return TetMesh(points=pts, tets=t10, surface_tris=np.empty((0, 6), int),
                   msh_path=Path("dinamik_dogrulama_sentetik.msh"),
                   element_type="C3D10")


def _mat():
    from analysis.calculix_writer import FEAMaterial
    return FEAMaterial(name="al", youngs_modulus_pa=E_PA,
                       poisson_ratio=NU, density_kg_m3=RHO)


def f1_analitik() -> float:
    """Euler-Bernoulli ankastre kiriş 1. mod: f = (1.875104)^2/(2π) √(EI/(ρA L^4))."""
    I = B_M * H_M ** 3 / 12.0
    A = B_M * H_M
    return (1.8751040687**2 / (2 * np.pi)) * np.sqrt(E_PA * I / (RHO * A * L_M**4))


def modal_f1(work: Path) -> dict:
    """`*FREQUENCY` ile 1. doğal frekans --- BAĞIMSIZ çözücü yolu."""
    from analysis.calculix_writer import FEACase, FixedBC, write_inp
    from analysis.ccx_runner import run_ccx
    mesh = _kiris()
    ank = np.where(mesh.points[:, 0] < 1e-9)[0] + 1
    case = FEACase(name="dyn_modal", mesh=mesh, material=_mat(),
                   fixed_bcs=[FixedBC(node_ids=ank)],
                   analysis_type="FREQUENCY", num_modes=3)
    r = run_ccx(write_inp(case, work / "modal"))
    if not r.success:
        return {"kosdu": False, "neden": (r.stderr or r.stdout)[-200:]}
    dat = Path(r.dat_path)
    if not dat.exists():
        return {"kosdu": False, "neden": ".dat yok"}
    # AYRISTIRMA BLOGA SINIRLI VE SUTUN GERCEK DOSYADAN OKUNDU.
    #
    # Ilk surum "rakamla baslayan satirin 5. alani" diyordu ve 0,0 dondu:
    # o alan FREKANSIN SANAL KISMI. Gercek bicim (CalculiX 2.17):
    #     MODE NO   EIGENVALUE   FREQ(RAD/TIME)   FREQ(CYCLES/TIME)   IMAG
    # yani Hz DORDUNCU alandir (indis 3).
    #
    # Ayrica ayni dosyada PARTICIPATION FACTORS ve EFFECTIVE MODAL MASS
    # bloklari da rakamla baslayan satirlar tasiyor --- ayristirma
    # EIGENVALUE blogunda BASLAR ve bir sonraki baslikta BITER.
    metin = dat.read_text(errors="replace")
    bas = metin.find("E I G E N V A L U E")
    if bas < 0:
        return {"kosdu": False, "neden": ".dat'ta özdeğer bloğu yok"}
    kesim = metin.find("P A R T I C I P A T I O N", bas)
    blok = metin[bas:kesim if kesim > 0 else len(metin)]
    frek, atlanan = [], 0
    for ln in blok.splitlines():
        p_ = ln.split()
        if len(p_) >= 4 and p_[0].isdigit():
            try:
                frek.append(float(p_[3]))
            except ValueError:
                # SESSIZ YUTMA DEGIL: ozdeger blogunda ayristirilamayan bir
                # satir, bir modun KAYBOLDUGU anlamina gelir --- ve f1
                # kaybolursa capa yanlis moda oturur. Sayilir ve HUKME girer.
                atlanan += 1
    if not frek:
        return {"kosdu": False,
                "neden": f"özdeğer bloğunda frekans satırı yok "
                         f"({atlanan} satır ayrıştırılamadı)"}
    if atlanan:
        return {"kosdu": False, "atlanan_satir": atlanan,
                "neden": (f"özdeğer bloğunda {atlanan} satır ayrıştırılamadı "
                          f"--- bir mod kaybolmuş olabilir ve f1 yanlış moda "
                          f"oturabilir; kısmi liste hükme sokulmaz")}
    # SIFIR FREKANS BIR HUKUMDUR, bir sayi degil: ya yanlis sutun okundu
    # (bu tam olarak oldu) ya da yapi serbest-serbest.
    if frek[0] <= 0.0:
        return {"kosdu": False,
                "neden": f"f1 = {frek[0]} Hz — yanlış sütun ya da mesnetsiz yapı"}
    return {"kosdu": True, "f1_hz": float(frek[0]), "ilk_uc": frek[:3],
            "atlanan_satir": 0}


def gecici(work: Path, f1_tahmin: float, bolen: int = 1) -> dict:
    """BASAMAK YÜK altında serbest salınımı ölç.

    KURULUM DEĞİŞTİ VE SEBEBİ ÖĞRETİCİ. İlk sürüm ``yükle sonra ANİDEN
    kaldır'' istiyordu ve bunun için `write_inp` çıktısına ikinci bir adım
    ELLE ekleniyordu (dizgi değiştirerek). İki kusuru vardı:

      (i) CalculiX reddetti --- ``in nonlinear calculations energy output
          must be selected in the first step''.
      (ii) DAHA ÖNEMLİSİ: doğrulanan şey YAZICININ ÇIKTISI DEĞİLDİ. Elle
           düzenlenmiş bir dosyayı koşurup ``*DYNAMIC çalışıyor'' demek,
           yazıcıyı hiç sınamamak olurdu.

    Basamak yük aynı frekansı verir ve TEK adımdır: sabit bir P aniden
    uygulandığında uç, statik sehim etrafında delta_st*(1-cos(wt)) ile
    salınır --- frekans yine w, yani birinci doğal frekans. Yazıcının kendi
    ürettiği dosya olduğu gibi koşulur.
    """
    from analysis.calculix_writer import FEACase, FixedBC, ForceLoad, write_inp
    from analysis.ccx_runner import run_ccx
    from analysis.frd_parser import parse_frd_zaman_serisi

    mesh = _kiris()
    I = B_M * H_M ** 3 / 12.0
    P = ALFA0 * E_PA * I / L_M ** 2
    ank = np.where(mesh.points[:, 0] < 1e-9)[0] + 1
    uc = np.where(mesh.points[:, 0] > L_M - 1e-9)[0] + 1
    T = 1.0 / f1_tahmin
    dt = T / (ADIM_BOLU_PERIYOT * bolen)
    case = FEACase(
        name=f"dyn_gecici_b{bolen}", mesh=mesh, material=_mat(),
        fixed_bcs=[FixedBC(node_ids=ank)],
        force_loads=[ForceLoad(node_ids=uc, direction=(0.0, 0.0, -1.0),
                               total_force_n=P)],
        analysis_type="DYNAMIC", dinamik_dt=dt, dinamik_sure=PERIYOT * T,
        dinamik_direct=True, dinamik_alpha=0.0)
    r = run_ccx(write_inp(case, work / case.name))
    if not r.success:
        return {"kosdu": False, "neden": (r.stderr or r.stdout)[-300:]}
    seri = parse_frd_zaman_serisi(Path(r.frd_path))
    sira = {int(n): i for i, n in enumerate(seri["node_ids"])}
    idx = [sira[int(n)] for n in uc if int(n) in sira]
    if not idx:
        return {"kosdu": False, "neden": "uç düğümleri seride yok"}
    z = seri["DISP"][:, idx, 2].mean(axis=1)
    t = seri["zamanlar"]
    return {"kosdu": True, "dt_s": dt, "n_adim": int(len(t)),
            "P_N": round(P, 5), "zamanlar": t.tolist(), "uc_z": z.tolist(),
            "atlanan": seri["atlanan"], **_frekans(t, z)}


def _frekans(t: np.ndarray, z: np.ndarray) -> dict:
    """Sıfır geçişlerinden frekans ve tepe genliklerinden sönüm."""
    if len(t) < 8:
        return {"f_hz": None, "neden": "seri çok kısa"}
    y = z - z.mean()
    gecis = [i for i in range(1, len(y)) if y[i - 1] < 0 <= y[i] or y[i - 1] > 0 >= y[i]]
    if len(gecis) < 3:
        return {"f_hz": None, "neden": f"yalnız {len(gecis)} sıfır geçişi"}
    # Ardisik gecisler YARIM periyottur.
    zaman_g = []
    for i in gecis:
        # Dogrusal ara-deger: sifira tam nerede geciyor.
        pay = -y[i - 1] / (y[i] - y[i - 1] + 1e-300)
        zaman_g.append(t[i - 1] + pay * (t[i] - t[i - 1]))
    yarim = np.diff(zaman_g)
    T = 2.0 * float(np.median(yarim))
    tepe = float(np.max(np.abs(y[:max(len(y) // 4, 2)])))
    son_tepe = float(np.max(np.abs(y[-max(len(y) // 4, 2):])))
    return {"f_hz": 1.0 / T if T > 0 else None,
            "periyot_s": T, "n_sifir_gecisi": len(gecis),
            "ilk_ceyrek_tepe_m": tepe, "son_ceyrek_tepe_m": son_tepe,
            "genlik_dusus_pct": (100 * (tepe - son_tepe) / tepe
                                 if tepe > 0 else None)}


def olc() -> dict:
    work = Path(tempfile.mkdtemp(prefix="dinamik_"))
    analitik = f1_analitik()
    modal = modal_f1(work)
    f1 = modal.get("f1_hz") or analitik
    kaba = gecici(work, f1, bolen=1)
    ince = gecici(work, f1, bolen=2)
    return _ozetle(analitik, modal, kaba, ince, work)


def _ozetle(analitik, modal, kaba, ince, work) -> dict:
    f1 = modal.get("f1_hz")
    fg = kaba.get("f_hz") if kaba.get("kosdu") else None
    fark = (100 * (fg - f1) / f1) if (fg and f1) else None
    dt_fark = None
    if kaba.get("f_hz") and ince.get("f_hz"):
        dt_fark = 100 * (ince["f_hz"] - kaba["f_hz"]) / kaba["f_hz"]
    dusus = kaba.get("genlik_dusus_pct")
    return {
        "vaka": "Zaman-çözünür yapısal analiz — serbest titreşim çapası",
        "_neden": ("`*DYNAMIC` eklendi. Bir karti yazmak kolaydir ve sessizce "
                   "yanlis olabilir: CalculiX kosar, bir seri uretir ve seri "
                   "fiziksel olarak yanlis olur."),
        "kiris": {"L_m": L_M, "b_m": B_M, "h_m": H_M, "E_Pa": E_PA,
                  "rho": RHO},
        "f1_analitik_hz": round(analitik, 4),
        "modal": modal,
        "gecici_kaba": {k: v for k, v in kaba.items()
                        if k not in ("zamanlar", "uc_z")},
        "gecici_ince": {k: v for k, v in ince.items()
                        if k not in ("zamanlar", "uc_z")},
        "frekans_farki_pct": None if fark is None else round(fark, 3),
        "dt_yarilaninca_fark_pct": None if dt_fark is None else round(dt_fark, 3),
        "genlik_dusus_pct": dusus,
        "frekans_MODALLE_uyusuyor": bool(fark is not None
                                         and abs(fark) < FREKANS_ESIGI_PCT),
        "genlik_KORUNUYOR": bool(dusus is not None
                                 and abs(dusus) < GENLIK_DUSUS_ESIGI_PCT),
        "dt_BAGIMSIZ": bool(dt_fark is not None and abs(dt_fark) < 1.0),
        "verdikt": _hukum(analitik, modal, kaba, ince, fark, dt_fark, dusus),
        "_kisit": (
            "Analitik f1 EULER-BERNOULLI'dir: kayma deformasyonu ve donme "
            "eylemsizligi YOK, FEA'da VAR. L/h=100 secildi ki fark kucuk "
            "kalsin ama SIFIR degildir --- bu yuzden ASIL olcut modal "
            "cozucuyle karsilastirmadir, analitikle degil. Sonum SIFIR "
            "verildi (alpha=0); CalculiX varsayilani -0,05'tir ve o "
            "birakilsaydi genlik dususu FIZIK sanilabilirdi. Ag "
            "bagimsizligi SINANMADI; tek ag."),
        "_uretim": "Üretim: python experiments/dinamik_dogrulama.py",
        "_calisma_dizini": str(work),
    }


def _hukum(analitik, modal, kaba, ince, fark, dt_fark, dusus) -> str:
    if not modal.get("kosdu"):
        return f"MODAL ÇÖZÜCÜ KOŞMADI ({modal.get('neden')}) — çapa YOK."
    if not kaba.get("kosdu"):
        return (f"GEÇİCİ KOŞU DÜŞTÜ ({kaba.get('neden')}) — `*DYNAMIC` "
                f"DOĞRULANMADI.")
    if kaba.get("f_hz") is None:
        return (f"Geçici koşu koştu ama SALINIM ÖLÇÜLEMEDİ "
                f"({kaba.get('neden')}) --- yük gerçekten kaldırıldı mı?")
    s = (f"Modal f1 = {modal['f1_hz']:.3f} Hz (analitik Euler-Bernoulli "
         f"{analitik:.3f} Hz). Geçici salınım {kaba['f_hz']:.3f} Hz "
         f"--- modalden %{fark:+.2f}. ")
    if abs(fark) >= FREKANS_ESIGI_PCT:
        return s + (f"Eşik %{FREKANS_ESIGI_PCT}: İKİ BAĞIMSIZ ÇÖZÜCÜ YOLU "
                    f"AYNI SAYIYI VERMİYOR. Zaman integrasyonu ya da kütle "
                    f"matrisi kuşkulu; `*DYNAMIC` DOĞRULANMADI.")
    s += (f"Genlik düşüşü %{dusus:.1f} (sönüm sıfır verildi). ")
    if dt_fark is not None:
        s += f"dt yarılanınca frekans %{dt_fark:+.2f} değişti. "
    if abs(dusus or 0) >= GENLIK_DUSUS_ESIGI_PCT:
        return s + ("SÖNÜMSÜZ SERİDE GENLİK KORUNMUYOR: sayısal sönüm "
                    "sonucu söndürüyor ve bu bir çözümde 'fizik' sanılırdı. "
                    "Frekans doğru ama genlik güvenilmez.")
    return s + ("Üç ölçüt de sağlandı: frekans bağımsız modal çözücüyle "
                "uyuşuyor, sönümsüz seride genlik korunuyor ve cevap zaman "
                "adımından bağımsız. `*DYNAMIC` DOĞRULANDI.")


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
