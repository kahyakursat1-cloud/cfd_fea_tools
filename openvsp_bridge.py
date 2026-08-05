"""
OpenVSP Bridge
==============
AircraftLibrary nesnelerini OpenVSP modeline çevirir.
STL, STEP, DegenGeom ve VSPAero hızlı analiz için arayüz.

Gereksinim: openvsp conda ortamı (Python 3.13)
  conda run -n openvsp python openvsp_bridge.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dis_araclar import bul  # noqa: E402

# OpenVSP DLL yolu — Windows'ta gerekli. Mutlak yol GÖMÜLÜ DEĞİL: OPENVSP_DIR ortam
# değişkeni > PATH > platform varsayılanı (bkz. dis_araclar). Docker imajında yalnız
# ortam değişkeni ayarlanır; kod değişmez.
_VSP = bul("openvsp_dll")
if _VSP["yol"] and hasattr(os, "add_dll_directory"):
    os.add_dll_directory(_VSP["yol"])
elif _VSP["zorunlu"] and not _VSP["yol"]:
    # SESSİZ KALMASIN: eski sürüm `if os.path.exists(...)` ile atlıyordu ve import
    # birkaç satır sonra anlaşılmaz bir DLL hatasıyla düşüyordu.
    raise RuntimeError(f"{_VSP['neden']} Arandi: {_VSP['aranan']}")

import openvsp as vsp  # noqa: E402 — DLL dizini eklendikten sonra import edilmeli

# VLM span-panel sayisi. Varsayilan YAKINSAMAMIS: olculdu ki span verimi e=1.0788
# (eliptik ust sinir 1.0 — fiziksel olarak imkansiz) ve tasima egimi ~%6.6 yuksek.
# 40 panelde e=0.9954 ile sinir icine giriliyor (bkz. experiments/vlm_capa.py).
VLM_SPAN_PANEL = 80
# ACIKLIK YONUNDE UC KUMELEMESI. Panel dagilimi DUZGUN ARALIKLI idi
# (OutCluster=1.0) ve uc girdabinin guclu gradyanini yakalayamiyordu: MiniHawk'ta
# Cl(8) serisi 40/60/80 panelde 0.3866/0.3815/0.4324 — MONOTON DEGIL, sacilma
# %11.78. Uca sikistirinca (OLCULDU):
#   OutCluster 1.00  ->  monoton DEGIL, sacilma %11.78
#   OutCluster 0.50  ->  monoton,       sacilma  %4.65  (ama e salinan: 0.91/0.92/0.62)
#   OutCluster 0.25  ->  monoton,       sacilma  %2.07  (e 1.04/0.94/0.93, duzenli)
# 0.25'te son iki kademe farki %0.02 — oturmus. Band 5.7 KAT daraldi.
VLM_UC_KUMELEME = 0.25


def aircraft_to_vsp(aircraft, vsp3_path: str = None) -> str:
    """Aircraft nesnesinden OpenVSP modeli oluştur.
    Döndürür: .vsp3 dosya yolu (kaydedilmişse)

    aircraft: AircraftLibrary'den gelen Aircraft dataclass
    """
    vsp.VSPCheckSetup()
    vsp.ClearVSPModel()

    fus  = aircraft.fuselage
    wing = aircraft.wing
    af   = wing.airfoil
    L    = fus.length
    D    = fus.diameter

    # ── FUSELAGE ─────────────────────────────────────────────────────────
    fus_id = vsp.AddGeom("FUSELAGE")
    vsp.SetGeomName(fus_id, "Fuselage")

    # Gövde uzunluğu — XSec konumları ile kontrol edilir
    xsurf_fus = vsp.GetXSecSurf(fus_id, 0)
    n_xsec = vsp.GetNumXSec(xsurf_fus)

    # XSec 0: burun ucu (küçük kesit)
    xs0 = vsp.GetXSec(xsurf_fus, 0)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs0, "XLocPercent"), 0.0)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs0, "TopLAngle"), 0.0)

    # XSec 1-3: silindirik gövde
    for idx in range(1, min(n_xsec - 1, 4)):
        xs = vsp.GetXSec(xsurf_fus, idx)
        pct = idx / (n_xsec - 1)
        try:
            vsp.SetParmValUpdate(vsp.GetXSecParm(xs, "XLocPercent"), pct * 0.85)
        except Exception:
            pass

    # Gövde design parametreleri
    try:
        vsp.SetParmValUpdate(vsp.FindParm(fus_id, "Length", "Design"), L)
    except Exception:
        pass

    # ── ANA KANAT ────────────────────────────────────────────────────────
    wing_id = vsp.AddGeom("WING")
    vsp.SetGeomName(wing_id, "MainWing")

    # Kanat konumu (fuselage üzerinde)
    vsp.SetParmValUpdate(vsp.FindParm(wing_id, "X_Rel_Location", "XForm"), L * 0.35)
    vsp.SetParmValUpdate(vsp.FindParm(wing_id, "Y_Rel_Location", "XForm"), 0.0)
    vsp.SetParmValUpdate(vsp.FindParm(wing_id, "Z_Rel_Location", "XForm"), 0.0)

    # Kanat geometrisi — Bölüm 1
    chord_root = wing.root_chord()
    chord_tip  = wing.tip_chord()
    span_half  = wing.span / 2

    xsurf_w = vsp.GetXSecSurf(wing_id, 0)
    xs1_w   = vsp.GetXSec(xsurf_w, 1)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs1_w, "Span"),       span_half)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs1_w, "Root_Chord"), chord_root)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs1_w, "Tip_Chord"),  chord_tip)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs1_w, "Sweep"),      wing.sweep_angle)
    vsp.SetParmValUpdate(vsp.GetXSecParm(xs1_w, "Dihedral"),   wing.dihedral)

    # NACA 4-digit profil atama
    naca_code = _parse_naca_name(af.name)
    if naca_code:
        _set_naca_profile(wing_id, naca_code)

    # Simetri: sol-sağ
    vsp.SetParmValUpdate(vsp.FindParm(wing_id, "Sym_Planar_Flag", "Sym"),
                         vsp.SYM_XZ)

    # ── YATAY KUYRUK ─────────────────────────────────────────────────────
    if aircraft.empennage:
        emp    = aircraft.empennage
        h_af   = emp.horizontal_airfoil
        h_span = (emp.h_area / h_af.chord) / 2 if h_af.chord > 0 else 0.15

        htail_id = vsp.AddGeom("WING")
        vsp.SetGeomName(htail_id, "HTail")
        vsp.SetParmValUpdate(vsp.FindParm(htail_id, "X_Rel_Location", "XForm"),
                             L * 0.88)
        vsp.SetParmValUpdate(vsp.FindParm(htail_id, "Span",       "XSec_1"), h_span)
        vsp.SetParmValUpdate(vsp.FindParm(htail_id, "Root_Chord", "XSec_1"), h_af.chord)
        vsp.SetParmValUpdate(vsp.FindParm(htail_id, "Tip_Chord",  "XSec_1"), h_af.chord * 0.6)
        vsp.SetParmValUpdate(vsp.FindParm(htail_id, "Sym_Planar_Flag", "Sym"),
                             vsp.SYM_XZ)

        naca_h = _parse_naca_name(h_af.name)
        if naca_h:
            _set_naca_profile(htail_id, naca_h)

        # Dikey kuyruk
        v_af   = emp.vertical_airfoil
        v_span = (emp.v_area / v_af.chord) / 2 if v_af.chord > 0 else 0.10

        vtail_id = vsp.AddGeom("WING")
        vsp.SetGeomName(vtail_id, "VTail")
        vsp.SetParmValUpdate(vsp.FindParm(vtail_id, "X_Rel_Location", "XForm"),
                             L * 0.88)
        vsp.SetParmValUpdate(vsp.FindParm(vtail_id, "Z_Rel_Location", "XForm"),
                             D * 0.5)
        vsp.SetParmValUpdate(vsp.FindParm(vtail_id, "Span",       "XSec_1"), v_span)
        vsp.SetParmValUpdate(vsp.FindParm(vtail_id, "Root_Chord", "XSec_1"), v_af.chord)
        vsp.SetParmValUpdate(vsp.FindParm(vtail_id, "Tip_Chord",  "XSec_1"), v_af.chord * 0.6)
        vsp.SetParmValUpdate(vsp.FindParm(vtail_id, "X_Rel_Rotation", "XForm"), 90.0)

        naca_v = _parse_naca_name(v_af.name)
        if naca_v:
            _set_naca_profile(vtail_id, naca_v)

    vsp.Update()

    if vsp3_path:
        vsp.WriteVSPFile(vsp3_path)
        print(f"[OpenVSP] Model kaydedildi: {vsp3_path}")

    return vsp3_path or ""


def export_stl(aircraft, output_path: str, tess_w: int = 16, tess_u: int = 8) -> str:
    """OpenVSP modelinden yüksek kaliteli watertight STL üret.

    tess_w: kanat chord yönü tessellation (16 = ince)
    tess_u: gövde çevre tessellation (8 = ince)
    """
    aircraft_to_vsp(aircraft)

    # Tessellation kalitesini artır
    geom_ids = vsp.FindGeoms()
    for gid in geom_ids:
        try:
            vsp.SetParmValUpdate(vsp.FindParm(gid, "Tess_W", "Shape"), tess_w)
            vsp.SetParmValUpdate(vsp.FindParm(gid, "Tess_U", "Shape"), tess_u)
        except Exception:
            pass

    vsp.Update()
    vsp.ExportFile(output_path, vsp.SET_ALL, vsp.EXPORT_STL)
    print(f"[OpenVSP] STL kaydedildi: {output_path}")
    return output_path


def _ayar(analiz: str, ad: str, deger, tip: str = "int"):
    """VSPAERO analiz girdisi ata — AD YOKSA YÜKSEK SESLE DÜŞ.

    NEDEN: `SetIntAnalysisInput` bilinmeyen bir ad için İSTİSNA ATMAZ; yalnızca
    stdout'a "Error Code: 5, Can't Find Name ..." basar ve devam eder. Ölçüldü
    (OpenVSP 3.50.4): bu köprü "KRİTİK" yorumuyla `AnalysisMethod` ayarlıyordu, ama
    o isim bu sürümde HİÇ YOK (80 girdi arasında yalnız GeomSet/ThinGeomSet/CGGeomSet
    'method' benzeri). Yani hang'i çözdüğü sanılan ayar bir HİÇ-İŞLEMDİ ve kimse
    fark etmedi. Sarmalayıcı, API sürümü değişince sessiz kalmak yerine kırılır.
    """
    mevcut = set(vsp.GetAnalysisInputNames(analiz))
    if ad not in mevcut:
        raise KeyError(f"VSPAERO '{analiz}' analizinde '{ad}' girdisi yok "
                       f"(OpenVSP surumu degismis olabilir). Benzerleri: "
                       f"{sorted(x for x in mevcut if ad[:4].lower() in x.lower())}")
    {"int": vsp.SetIntAnalysisInput,
     "double": vsp.SetDoubleAnalysisInput}[tip](analiz, ad, deger)


def _vspaero_setup_vlm(aircraft):
    """VSPAERO geometriyi hazirlar.

    NOT: 3.50.4'te VLM/PANEL secimi ayri bir `AnalysisMethod` girdisiyle DEGIL,
    GeomSet/ThinGeomSet uzerinden yapiliyor. Varsayilan bu modelde takilmiyor ve
    Trefftz alanlari fiziksel; secim ACIKCA degistirilmiyor.
    """
    aircraft_to_vsp(aircraft)
    # PANEL YOGUNLUGU BURADA ATANMALI — `VSPAEROComputeGeometry`'DEN ONCE.
    # ComputeGeometry, VSPAERO'nun kullanacagi panel/DegenGeom dosyasini URETIR;
    # ondan SONRA yapilan tessellation degisikligi coktan yazilmis geometriyi
    # ETKILEMEZ. Ilk denemede kod tam da oraya konmustu ve sonuc BIREBIR AYNI
    # cikti (Cl/CDi %0.00 degisim, span verimi hala 1.08) — yani duzeltme
    # SESSIZCE hicbir sey yapmisti. Parm'in kendisi calisiyor (olculdu: 6.0->40.0),
    # kusur SIRALAMADAYDI.
    n_ayar = _panel_yogunlugu_ata(VLM_SPAN_PANEL)
    vsp.Update()
    vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
    vsp.ExecAnalysis("VSPAEROComputeGeometry")
    return n_ayar


def _panel_yogunlugu_ata(panel: int, uc_kumeleme: float = None) -> list[str]:
    """Kanat geometrilerine span-panel sayisi + UC KUMELEMESI ata; KACINA
    UYGULANDIGINI DONDUR.

    Sessiz `except: pass` yerine SAYIM: uygulanamayan geometri gorunur olmali,
    yoksa "duzeltme kondu ama ise yaramadi" durumu yine gizlenir — nitekim bir
    kez gizlendi (panel ayari ComputeGeometry'den SONRA yapilmisti ve sonuc
    birebir ayni cikti).
    """
    if uc_kumeleme is None:
        uc_kumeleme = VLM_UC_KUMELEME
    uygulanan = []
    for gid in vsp.FindGeoms():
        if vsp.GetGeomTypeName(gid) != "Wing":
            continue
        try:
            xs = vsp.GetXSec(vsp.GetXSecSurf(gid, 0), 1)
            pid = vsp.GetXSecParm(xs, "SectTess_U")
            if not pid:
                continue
            vsp.SetParmValUpdate(pid, panel)
            kid = vsp.GetXSecParm(xs, "OutCluster")
            if kid:
                vsp.SetParmValUpdate(kid, uc_kumeleme)
            if abs(vsp.GetParmVal(pid) - panel) < 1e-9:
                uygulanan.append(vsp.GetGeomName(gid))
        # sessiz-yutma: kabul — bu geometri parmi tasimiyorsa VARSAYILAN panelle
        # devam edilir; ADI listede GORUNMEZ, yani sonuc "kac kanada uygulandi"
        # sayisindan anlasilir (eski surumde sessizce yutuluyordu).
        except Exception:
            continue
    return uygulanan


def run_vspaero_polar(aircraft, alphas=(0, 4, 8, 12, 16), mach: float = 0.05,
                       output_dir: str = "./vspaero_results") -> list:
    """VSPAERO VLM ile TEK cagrida tum polar (saniyeler).
    Induced drag + Cl-alpha egrisi. Viskoz drag YOK (VLM inviscid).

    Donduru: [{'alpha','Cl','Cd_i','Cm'}...]
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    panel_uygulanan = _vspaero_setup_vlm(aircraft)

    a = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(a)
    _ayar(a, "AlphaStart", [float(min(alphas))], "double")
    _ayar(a, "AlphaEnd",   [float(max(alphas))], "double")
    _ayar(a, "AlphaNpts",  [len(alphas)])
    _ayar(a, "MachStart",  [mach], "double")
    _ayar(a, "Sref",       [aircraft.wing.area], "double")
    _ayar(a, "bref",       [aircraft.wing.span], "double")
    _ayar(a, "cref",       [aircraft.wing.root_chord()], "double")
    _ayar(a, "WakeNumIter", [5])

    rid = vsp.ExecAnalysis(a)

    # VSPAERO_Polar: aci-vektoru sonuc. Near-field (CLtot/CDtot) thick-surface
    # VLM'de bozuk; wake/Trefftz-entegre alanlar (CLwtot, CDiw) fizikseldir.
    pol = vsp.FindResultsID("VSPAERO_Polar", 0)
    if not pol:
        return []
    alpha = list(vsp.GetDoubleResults(pol, "Alpha"))
    cl    = list(vsp.GetDoubleResults(pol, "CLwtot"))   # Trefftz lift
    cdi   = list(vsp.GetDoubleResults(pol, "CDiw"))     # Trefftz induced drag
    cm    = list(vsp.GetDoubleResults(pol, "CMytot"))
    ld    = list(vsp.GetDoubleResults(pol, "L_Dw"))

    out = []
    for i in range(len(alpha)):
        out.append({
            "alpha": round(alpha[i], 1),
            "Cl":    round(cl[i], 5) if i < len(cl) else None,
            "Cd_i":  round(cdi[i], 6) if i < len(cdi) else None,
            "Cm":    round(cm[i], 5) if i < len(cm) else None,
            "LD_i":  round(ld[i], 2) if i < len(ld) and ld[i] else None,
            "method": "VSPAERO_VLM",
            # AYRIKLASTIRMA KAYDA GECER: ilk denemede panel ayari YANLIS YERDE
            # (ComputeGeometry'den SONRA) yapilmisti ve sonuc birebir ayni cikti.
            # Hangi panelle kosuldugu sonuca yazilmazsa ayni sessiz hata tekrar
            # fark edilmez.
            "span_panel": VLM_SPAN_PANEL,
            "uc_kumeleme": VLM_UC_KUMELEME,
            "panel_uygulanan_kanat": panel_uygulanan,
        })
    return out


def run_vspaero(aircraft, alpha_deg: float = 0.0, mach: float = 0.05,
                output_dir: str = "./vspaero_results") -> dict:
    """Tek alpha VSPAERO VLM (geriye uyumluluk)."""
    r = run_vspaero_polar(aircraft, alphas=(alpha_deg,), mach=mach,
                          output_dir=output_dir)
    return r[0] if r else {"alpha": alpha_deg, "Cl": 0, "Cd_i": 0, "status": "FAILED"}


# ── Yardımcı fonksiyonlar ────────────────────────────────────────────────────

def _parse_naca_name(name: str):
    """'NACA2412' → '2412', 'NACA0009' → '0009'. Tanınmazsa None."""
    n = name.upper().replace("NACA", "").strip()
    if len(n) == 4 and n.isdigit():
        return n
    return None


def _set_naca_profile(geom_id: str, naca_4: str, apply_camber: bool = False):
    """Wing'in TUM XSec'lerine NACA 4-digit kalinligi ata.
    apply_camber=True: camber da uygular (STL/OpenFOAM icin dogru geometri),
    ANCAK VSPAERO VLM bu DegenGeom'da diverge ediyor -> VSPAERO yolunda False.
    ChangeXSecShape imzasi (xsec_surf, index, type) — onceki kod yanlis imzayla
    sessizce except'e dusuyordu, camber hic uygulanmiyordu.
    """
    try:
        m = int(naca_4[0]) / 100.0   # max camber (kord orani)
        p = int(naca_4[1]) / 10.0    # camber konumu (kord orani)
        t = int(naca_4[2:]) / 100.0  # kalinlik (kord orani)
        if not apply_camber:
            # VSPAERO yolu: kesite DOKUNMA. OpenVSP 3.50.4 VLM, API ile
            # ChangeXSecShape/Camber manipulasyonunda yuksek-alpha'da diverge
            # ediyor (Cl=-37 gibi). Varsayilan four-series geometri temiz
            # slope/induced-drag verir; mutlak Cl OpenFOAM'dan gelir.
            return
        # STL/OpenFOAM yolu (apply_camber=True): tam NACA geometrisi
        xsec_surf = vsp.GetXSecSurf(geom_id, 0)
        n = vsp.GetNumXSec(xsec_surf)
        for i in range(n):
            vsp.ChangeXSecShape(xsec_surf, i, vsp.XS_FOUR_SERIES)  # (surf,index,type)
            vsp.Update()
            xsec_id = vsp.GetXSec(xsec_surf, i)
            vsp.SetParmValUpdate(vsp.GetXSecParm(xsec_id, "ThickChord"), t)
            vsp.SetParmValUpdate(vsp.GetXSecParm(xsec_id, "Camber"),     m)
            vsp.SetParmValUpdate(vsp.GetXSecParm(xsec_id, "CamberLoc"),  p)
    except Exception as e:
        print(f"[camber] uyari: {e}")


# ── CLI kullanımı ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from aircraft_geometry import AircraftLibrary

    a = AircraftLibrary().minihawk_uav()
    mode = sys.argv[1] if len(sys.argv) > 1 else "polar"

    if mode == "polar":
        alphas = [float(x) for x in sys.argv[2:]] or [0, 4, 8, 12, 16]
        print(f"VSPAERO VLM polar: alphas={alphas}", flush=True)
        res = run_vspaero_polar(a, alphas=alphas)
        for r in res:
            print(f"  alpha={r['alpha']}: Cl={r['Cl']} Cd_i={r['Cd_i']} Cm={r['Cm']}", flush=True)
        # DÜZ LİSTE DEĞİL, SÖZLÜK: liste hâlinde kanit.py bunu "artefakt" sınıfına
        # atıyordu — yani üretici komutu ve KISITI hiçbir yerde kayıtlı değildi.
        # En yanıltıcı olanı kamburluk kısıtı: bu yolda Cl(0°) TANIM GEREĞİ 0'dır,
        # dolayısıyla OpenFOAM'ın Cl'iyle düşük alfada kıyaslanamaz.
        cikti = {
            "vaka": f"VSPAERO VLM polar — {a.name}, alfalar={alphas}",
            "polar": res,
            "_kisit": ("KAMBURLUK UYGULANMIYOR: _set_naca_profile(apply_camber=False) "
                       "— OpenVSP 3.50.4 VLM kamburlu kesitte yuksek alfada iraksiyor. "
                       "Sonuc: alpha_L0 URETILEMEZ ve Cl(0)=0.0 bir OLCUM DEGIL, "
                       "kurulumun dogrudan sonucudur. Bu polar YALNIZ tasima egimi ve "
                       "induklenen direnc icin gecerlidir; mutlak Cl OpenFOAM'dan gelir."),
            "_uretim": "Üretim: python pipeline.py vspaero " + " ".join(str(x) for x in alphas),
        }
        # encoding ACIK olmali: Windows'ta varsayilan cp1254 ve ensure_ascii=False ile
        # dosya utf-8 olarak OKUNAMIYOR (pipeline UnicodeDecodeError ile dustu).
        Path("vspaero_polar.json").write_text(
            json.dumps(cikti, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Kaydedildi: vspaero_polar.json", flush=True)

    elif mode == "stl":
        out = sys.argv[2] if len(sys.argv) > 2 else "./openvsp_minihawk.stl"
        export_stl(a, out)
        import trimesh
        m = trimesh.load(out)
        print(f"STL: {len(m.vertices)} verts, watertight={m.is_watertight}")
