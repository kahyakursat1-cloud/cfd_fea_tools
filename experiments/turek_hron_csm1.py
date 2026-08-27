"""Turek--Hron CSM1 --- yapısal zincirin AKIŞSIZ, yayımlanmış çapası.

NEDEN BU ÖLÇÜM ŞİMDİ. İki-yönlü FSI1 koşusunda düşey sehim referansın %77
üstünde kaldı ve üç aday sırayla elendi: akış çözücüsü (sürükleme
yayımlanan değerin %0,1'inde), ağ (dört seviyeli aile, taşıma yayılımı
%3,1) ve yapısal model. Ama yapısal modelin elenmesi DOLAYLIYDI: ux
referansı %1,3 bandında tutturuyor, ux ise EA'ya bağlı, dolayısıyla E ya da
kesit 1,8 kat yanlış olamaz. Doğru ama bir ÇIKARIM.

CSM1 aynı yapıyı DOĞRUDAN sınar ve akışı hiç işin içine sokmaz: aynı
bayrak, aynı malzeme, tek yük olarak yerçekimi (g = 2 m/s^2). Yayımlanan
uç yer değiştirmesi ux = -7,187 mm ve uy = -66,10 mm.

BU KIYASLAMA FSI1'DEN DAHA ZORDUR. Sehim/uzunluk = %19, yani BÜYÜK yer
değiştirme rejimi: lineer teori burada geçmez ve NLGEOM zorunludur.
Depoda NLGEOM elastika çözümüne karşı doğrulanmıştı; bu, onu Turek--Hron'un
kendi malzemesi ve kesitiyle YAYIMLANMIŞ bir değere bağlar.

REFERANS ÇİFTİ KENDİ İÇİNDE TUTARLI. Enine yüklü bir konsolda uç, kinematik
olarak 0,6 uy^2/L kadar kısalır: 0,6 x 66,10^2 / 350 = 7,49 mm, verilen
ux 7,187 mm. Bu, FSI1'de yazdığım kapının FORMÜLÜNÜN doğru olduğunu da
gösterir --- oradaki hata formülde değil, akışkan kayma çekmesinin eksenel
yükü baskın kılmasını hesaba katmamaktaydı.

    python experiments/turek_hron_csm1.py
Çıktı: turek_hron_csm1.json
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from turek_hron_ag import (  # noqa: E402
    BAYRAK_KALINLIK,
    BAYRAK_SON_X,
    MERKEZ,
    Z_KALINLIK,
    bayrak_bas_x,
)
from turek_hron_fsi1 import E_S, MU_S, NU_S, RHO_S, _bayrak_agi  # noqa: E402

CIKTI = KOK / "turek_hron_csm1.json"
IS = KOK / "turek_hron_csm1_fea"

G = 2.0
# Yayimlanan CSM1 uc yer degistirmesi (A noktasi). Feel++ CSM kiyaslama
# belgesinden alindi; ayni sayfa geometri ve malzemeyi de veriyor ve
# ikisi de bu depodakiyle ortusuyor (l=0,35, h=0,02, E=1,4e6, nu=0,4,
# rho=1000, g=2).
REF = {"ux_mm": -7.187, "uy_mm": -66.10, "_dogrulandi": True,
       "_kaynak": "Turek-Hron CSM kiyaslamasi; Feel++ CSM belgesi"}
# Buyuk yer degistirme rejiminde artim sayisi SONUCU ETKILER; kayda girer.
ARTIM = 40


def _kos(nlgeom: bool) -> dict:
    from analysis.calculix_writer import (
        FEACase,
        FEAMaterial,
        FixedBC,
        GravityLoad,
        write_inp,
    )
    from analysis.ccx_runner import run_ccx
    from analysis.frd_parser import parse_frd

    work = IS / ("nlgeom" if nlgeom else "lineer")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    mesh = _bayrak_agi()
    P = mesh.points
    xb = bayrak_bas_x()
    ankastre = np.where(P[:, 0] < xb + 1e-9)[0] + 1
    case = FEACase(
        name="csm1", mesh=mesh,
        material=FEAMaterial(name="tk_solid", youngs_modulus_pa=E_S,
                             poisson_ratio=NU_S, density_kg_m3=RHO_S),
        # DUZLEM GERINIM YAZICININ KENDI YOLUYLA. Turek-Hron 2B'dir; z
        # serbest birakilirsa problem duzlem GERILME olur ve kiris
        # 1/(1-nu^2) kadar daha esner. FSI1'de bu kisiti .inp metnine ELLE
        # enjekte etmistim ve burada BEDELINI ODEDI: eklenen blok
        # `*STATIC`'in artim satirini (`0.1, 1.0`) `*BOUNDARY` verisi
        # haline getirdi ve CalculiX girdiyi reddetti. Lineer adimda o
        # satir olmadigi icin FSI1'de sessizce calisiyordu. FixedBC zaten
        # dof_start/dof_end tasiyor --- elle duzenlemeye HIC GEREK YOKTU.
        fixed_bcs=[FixedBC(node_ids=ankastre, name="ANKASTRE"),
                   FixedBC(node_ids=np.where(
                       (P[:, 2] < 1e-12) | (P[:, 2] > Z_KALINLIK - 1e-12)
                   )[0] + 1, name="ZDUZLEM", dof_start=3, dof_end=3)],
        gravity_loads=[GravityLoad(accel_m_s2=G, direction=(0.0, -1.0, 0.0))],
        nlgeom=nlgeom, max_artim_sayisi=ARTIM,
    )
    r = run_ccx(write_inp(case, work))
    if not r.success:
        return {"kosdu": False, "neden": (r.stderr or r.stdout)[-300:]}
    frd = parse_frd(r.frd_path)
    if "DISP" not in frd.fields:
        return {"kosdu": False, "neden": "frd'de DISP yok"}
    sira = {int(n): i for i, n in enumerate(frd.node_ids)}
    hedef = np.array([BAYRAK_SON_X, MERKEZ[1], Z_KALINLIK / 2])
    mesafe = np.linalg.norm(P - hedef, axis=1)
    aday = [i for i in np.argsort(mesafe)[:20] if int(i + 1) in sira]
    if not aday:
        return {"kosdu": False, "neden": "A noktası frd'de yok"}
    i = aday[0]
    u = frd.fields["DISP"][sira[int(i + 1)]]
    return {"kosdu": True, "nlgeom": nlgeom, "artim": ARTIM,
            "A_uzaklik_m": float(mesafe[i]),
            "ux_mm": float(u[0]) * 1000, "uy_mm": float(u[1]) * 1000,
            "uz_mm": float(u[2]) * 1000}


def _kinematik() -> dict:
    """Referans çiftinin kendi içinde tutarlılığı --- FORMÜLÜN sınavı.

    FSI1'de bu formülü bir kapı olarak yazmış ve YANLIŞ uygulamıştım
    (akışkan kayma çekmesi orada eksenel yükü baskın kılıyor). Akışın
    olmadığı CSM1'de formülün kendisi sınanabilir: enine yüklü bir
    konsolun ucu kinematik olarak 0,6 uy^2/L kadar kısalır.
    """
    L = (BAYRAK_SON_X - bayrak_bas_x()) * 1000.0
    beklenen = 0.6 * REF["uy_mm"] ** 2 / L
    return {"ux_kinematik_mm": round(beklenen, 4),
            "ux_referans_mm": abs(REF["ux_mm"]),
            "oran": round(beklenen / abs(REF["ux_mm"]), 3)}


def olc() -> dict:
    IS.mkdir(parents=True, exist_ok=True)
    return _ozetle(_kos(nlgeom=False), _kos(nlgeom=True))


def _sapma(r) -> dict | None:
    if not (r and r.get("kosdu")):
        return None
    return {"ux_pct": round(100 * (r["ux_mm"] - REF["ux_mm"])
                            / abs(REF["ux_mm"]), 2),
            "uy_pct": round(100 * (r["uy_mm"] - REF["uy_mm"])
                            / abs(REF["uy_mm"]), 2)}


def _ozetle(lineer, nl) -> dict:
    return {
        "vaka": "Turek-Hron CSM1 — yapı, yerçekimi altında, akış yok",
        "_neden": ("Iki-yonlu FSI1'de yapisal model DOLAYLI elenmisti "
                   "(ux/EA cikarimi). CSM1 onu DOGRUDAN ve yayimlanmis bir "
                   "degere karsi sinar; ustelik sehim/uzunluk %19 oldugu "
                   "icin NLGEOM'u da zorlar."),
        "kati": {"mu_s_Pa": MU_S, "nu_s": NU_S, "E_Pa": E_S, "rho": RHO_S,
                 "g_m_s2": G},
        "geometri": {"L_m": round(BAYRAK_SON_X - bayrak_bas_x(), 5),
                     "h_m": BAYRAK_KALINLIK, "duzlem_gerinim": True},
        "lineer": lineer, "nlgeom": nl,
        "sapma_lineer": _sapma(lineer), "sapma_nlgeom": _sapma(nl),
        "referans": REF,
        "referans_kinematigi": _kinematik(),
        "verdikt": _hukum(lineer, nl),
        "_kisit": (
            "AG-BAGIMSIZLIGI SINANMADI: FSI1 ile AYNI yapi agi kullanildi "
            "(NX=70, NY=6, C3D10) --- bu KASITLIDIR, cunku sinanan sey o "
            "agdir. Artim sayisi (40) sonucu etkileyebilir ve "
            "yakinsatilmadi. Malzeme St. Venant-Kirchhoff DEGIL, "
            "CalculiX'in NLGEOM ile kullandigi lineer-elastik "
            "buyuk-yerdegistirme modelidir; %19 sehimde ikisi arasindaki "
            "fark kucuktur ama SIFIR degildir ve OLCULMEDI."),
        "_uretim": "Üretim: python experiments/turek_hron_csm1.py",
    }


def _hukum(lineer, nl) -> str:
    k = _kinematik()
    s = (f"Referans çifti kendi içinde tutarlı: uy={REF['uy_mm']} mm bir "
         f"konsolda {k['ux_kinematik_mm']} mm kısalma gerektirir, verilen "
         f"ux {abs(REF['ux_mm'])} mm (oran {k['oran']}). ")
    if not (nl and nl.get("kosdu")):
        return s + f"NLGEOM KOŞUSU DÜŞTÜ: {(nl or {}).get('neden')}"
    sn = _sapma(nl)
    if lineer and lineer.get("kosdu"):
        sl = _sapma(lineer)
        s += (f"LİNEER çözüm uy={lineer['uy_mm']:.3f} mm (%{sl['uy_pct']}) "
              f"--- büyük yer değiştirme rejiminde beklendiği gibi "
              f"kullanılamaz. ")
    s += (f"NLGEOM: ux={nl['ux_mm']:.3f} mm, uy={nl['uy_mm']:.3f} mm; "
          f"yayımlanan {REF['ux_mm']} ve {REF['uy_mm']} --- sapma "
          f"%{sn['ux_pct']} ve %{sn['uy_pct']}. ")
    if abs(sn["uy_pct"]) < 5.0:
        return s + (
            "YAPISAL ZİNCİR YAYIMLANMIŞ BİR DEĞERE KARŞI DOĞRULANDI: ağ, "
            "malzeme, düzlem gerinim seçimi ve büyük-yer-değiştirme yolu "
            "birlikte %5 bandında. Bu, FSI1'de yapılan DOLAYLI elemeyi "
            "doğrudan bir ölçümle değiştirir --- iki-yönlü koşuda kalan "
            "%77'lik sapmanın kaynağı yapıda DEĞİLDİR. Tek ağ, tek artım "
            "sayısı; bant bir GCI değil.")
    return s + (
        "YAPISAL ZİNCİR YAYIMLANMIŞ DEĞERİ ÜRETMEDİ. Bu, FSI1'de yapılan "
        "dolaylı elemeyi ÇÜRÜTÜR: ux/EA çıkarımı eksenel rijitliği "
        "sınıyordu, CSM1 ise EĞİLME rijitliğini sınar ve ikisi aynı şey "
        "değildir. Sıradaki soru artık kuplajda değil YAPIDA: ağ, düzlem "
        "gerinim seçimi, ya da büyük-yer-değiştirme yolu.")


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
