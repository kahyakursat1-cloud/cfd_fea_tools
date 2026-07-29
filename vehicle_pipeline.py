"""
Araç analiz hattı: katı model (STL/OBJ) → araca uygun mesh → CFD → mühendis raporu.
===================================================================================
Tek giriş noktası: run_vehicle_analysis(). GUI (app_analyzer) ve CLI bunu çağırır.
Mesh/çözüm motoru analysis.openfoam_runner (snappyHexMesh + foamRun/kOmegaSST);
bu modül araç-tipi presetleri, referans alan hesabı, yakınsama/kalite teşhisi ve
rapor üretimini ekler.

CLI: python vehicle_pipeline.py model.stl --tip ucak --hiz 30 --aoa 4
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import ConvexHull

from analysis.ccx_runner import windows_to_wsl_path
from analysis.openfoam_runner import CFDCase, _wsl_run, run_cfd
from constants import NONORTHO_LIMIT, RESIDUAL_TARGET, SKEW_LIMIT
from validity_envelope import force_admissibility, geometry_sanity

VEHICLE_PRESETS = {
    "ucak": {
        "ad": "Sabit Kanatlı Uçak / İHA",
        "refinement": (2, 3), "domain": (5.0, 15.0, 5.0),
        "aref_mode": "planform", "lift_relevant": True,
    },
    "roket": {
        "ad": "Roket / Füze Gövdesi",
        "refinement": (2, 3), "domain": (5.0, 20.0, 5.0),
        "aref_mode": "frontal", "lift_relevant": False,
    },
    "multikopter": {
        "ad": "Multikopter / Drone Gövdesi",
        "refinement": (2, 3), "domain": (5.0, 12.0, 5.0),
        "aref_mode": "frontal", "lift_relevant": False,
    },
    "araba": {
        "ad": "Kara Aracı (otomobil / verimlilik aracı)",
        "refinement": (2, 3), "domain": (5.0, 15.0, 5.0),
        "aref_mode": "frontal", "lift_relevant": False,
        "ground": True,   # zemin-etkili: taban = noSlip duvar (Ahmed-tipi kurulum)
    },
    "genel": {
        "ad": "Genel Cisim (küt gövde)",
        "refinement": (1, 2), "domain": (5.0, 15.0, 5.0),
        "aref_mode": "frontal", "lift_relevant": False,
    },
}


def auto_ground_clearance(preset: dict, height_m: float,
                          ground_clearance: float | None) -> float | None:
    """Zemin-etkili preset'te (araba) clearance verilmemişse Ahmed-oranı varsayılanı:
    deney kurulumunun h/H≈50/288≈0.17'si. Kullanıcı değeri her zaman öncelikli."""
    if ground_clearance is not None:
        return ground_clearance
    if preset.get("ground"):
        return round(0.17 * height_m, 4)
    return None

# bg_div: arka-plan hucresi = L/bg_div. maxGlobalCells yalniz refinement'i
# sinirlar; domain ~21Lx11Lx11L oldugundan taban mesh = 2541*bg_div^3 hucre —
# tavani asil delen buydu (L/8 otomatigi tek basina ~1.3M taban uretiyordu).
# n_layers/yplus_target: "hassas" varsayılan olarak DUVAR-ÇÖZÜNÜR (y⁺≲1 + prizma katman)
# → sürtünme sürüklemesi duvar-fonksiyonu sınırından çıkar (SST low-Re; 10-15 katman önerisi).
# hizli/standart duvar-fonksiyonunda kalır (hız). Çağıran n_layers>0 verirse override eder.
MESH_QUALITY = {
    "hizli":    {"end_time": 200, "ref_bump": -1, "max_cells": 400_000,   "bg_div": 5, "n_layers": 0,  "yplus_target": 30.0},
    "standart": {"end_time": 400, "ref_bump": 0,  "max_cells": 1_200_000, "bg_div": 7, "n_layers": 0,  "yplus_target": 30.0},
    "hassas":   {"end_time": 800, "ref_bump": 1,  "max_cells": 2_500_000, "bg_div": 9, "n_layers": 12, "yplus_target": 1.0},
    # hassas_nl: hassas yoğunluk/yakınsama AMA katmansız — ince kanat firar-kenarı gibi
    # prizma-katmanın güvenle örülemediği geometriler için (y+ orta/duvar-fonksiyonu kalır;
    # label kalitesi mesh-yoğunluğu + yakınsamadan gelir). Thin-feature CAE standart yedek.
    "hassas_nl": {"end_time": 800, "ref_bump": 1, "max_cells": 2_500_000, "bg_div": 9, "n_layers": 0, "yplus_target": 30.0},
}

def farfield_domain(preset: dict, alpha_deg: float = 0.0) -> tuple[float, float, float]:
    """Far-field domain çarpanları (upstream, downstream, lateral) — rejim/geometri-bilinçli.

    Taşıyıcı (lift_relevant) cisimde sirkülasyon-kaynaklı basınç alanı yanal/yukarı YAVAŞ
    söner; yakın sınır basınç-drag'i orantısız bozar (bu oturumun far-field dersi; literatür:
    ses-altı RANS best-practice ≥ büyük domain). Bu yüzden lifting cisimde domain ölçülü
    büyütülür; yüksek |α|'da (daha çok lift) yanal biraz daha. Küt/eksenel cisim değişmez.

    MALİYET: lifting domain ~%50-100 daha çok taban hücre (hacim ∝ up·lat²). max_cells +
    bg_div sınırlar; yine de aircraft koşusu bir kademe ağırlaşır — doğruluk/maliyet takası.
    """
    up, down, lat = preset["domain"]
    if preset.get("lift_relevant"):
        up, down, lat = max(up, 7.0), max(down, 18.0), max(lat, 7.0)
        if abs(alpha_deg) >= 8.0:          # güçlü lift → daha geniş yan/üst
            lat = max(lat, 9.0)
    return (up, down, lat)


# Mesh kalite / yakınsama eşikleri: constants.py (tek kaynak — yukarıda import edildi).
DRIFT_LIMIT_PCT = 2.0    # son %20 pencerede |dCd|/Cd


CAD_EXTS = {".step", ".stp", ".iges", ".igs"}


def convert_cad_to_stl(cad_path: Path, out_stl: Path) -> Path:
    """STEP/IGES → STL (gmsh yüzey mesh'i; çekirdek bağımlılık, ek kurulum yok)."""
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(cad_path))
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
        L = max(xmax - xmin, ymax - ymin, zmax - zmin)
        gmsh.option.setNumber("Mesh.MeshSizeMin", L / 200)
        gmsh.option.setNumber("Mesh.MeshSizeMax", L / 60)
        gmsh.model.mesh.generate(2)
        gmsh.write(str(out_stl))
    finally:
        gmsh.finalize()
    return out_stl


def canonicalize_axial(m: trimesh.Trimesh):
    """Belirgin EKSENEL cismi (roket/füze: bir uzun eksen + YUVARLAK kesit)
    uçuş yönüne hizalar — uzun eksen→+x, ince eksen→+z. run_supersonic uzun-ekseni
    ≈+x ve frontal'i +x izdüşümü varsayar; dikey/yan modellenen roketi düzeltir.

    Yassı/kanat (kesit yuvarlak değil) ve küt cisimlere DOKUNMAZ — onlar zaten
    doğru sınıflanır ve ses-altı yolu nose_axis parametresini kullanır (çift-dönme
    riski yok). Döner: (mesh, açıklama|None)."""
    ext = (m.bounds[1] - m.bounds[0]).astype(float)
    order = np.argsort(ext)                       # küçük→büyük eksen indeksi
    e_thin, e_mid, e_long = ext[order[0]], ext[order[1]], ext[order[2]]
    # eksenel imza: belirgin uzun eksen (e_long»e_mid) + yuvarlak kesit (e_mid≈e_thin)
    if not (e_long >= 2.0 * e_mid and e_mid <= 1.7 * e_thin):
        return m, None
    long_axis = int(order[2])
    if long_axis == 0:
        return m, None                            # zaten +x hizalı
    axis = [0, 1, 0] if long_axis == 2 else [0, 0, 1]   # z→x: y-ekseni; y→x: z-ekseni
    out = m.copy()
    out.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, axis))
    return out, f"eksenel hizalama: uzun eksen {'xyz'[long_axis]}→x (uçuş yönü)"


def weld_axial_segments(m: trimesh.Trimesh):
    """KOPUK ama EŞ-EKSENLİ (aynı kesit, tek eksen boyunca dizili, aralarında BOŞLUK)
    gövdeleri tek watertight cisme birleştirir — konveks-zarf köprüleme. Roket/füze
    exploded/kopuk-ihraç artefaktını onarır (akış boşluklardan geçip Cd'yi bozuyordu).

    MUHAFAZAKÂR GUARD — yalnız EŞ-MERKEZLİ + BENZER-KESİT (koaksiyel silindir) segmentlere
    uygular. Yanal-yayılı çok-gövde (kanat/kontrol-yüzeyi montajı: a320/f16) ya da finli
    roket (yanal çıkıntı) GUARD'ı geçemez → DOKUNULMAZ (konveks-zarf onları bozardı).
    Döner: (mesh, açıklama|None)."""
    try:
        parts = m.split(only_watertight=False)
    except Exception:
        return m, None
    if len(parts) < 2:
        return m, None
    ext = (m.bounds[1] - m.bounds[0]).astype(float)
    long_ax = int(np.argmax(ext))
    minor = [a for a in range(3) if a != long_ax]
    ref = max(parts, key=lambda p: len(p.faces))            # ana gövde referans
    for p in parts:
        for ax in minor:
            rc = (ref.bounds[0][ax] + ref.bounds[1][ax]) / 2
            pc = (p.bounds[0][ax] + p.bounds[1][ax]) / 2
            rext = ref.bounds[1][ax] - ref.bounds[0][ax]
            pext = p.bounds[1][ax] - p.bounds[0][ax]
            # eş-merkez (merkez kayması < %25 çap) + benzer kesit (extent oranı < 1.6)
            if abs(pc - rc) > 0.25 * rext or not (1 / 1.6 < pext / max(rext, 1e-9) < 1.6):
                return m, None
    welded = m.convex_hull                                   # boşlukları köprüler
    if not welded.is_watertight:
        return m, None
    welded = welded.subdivide().subdivide()                 # CFD-dostu yüzey
    ek = ""
    try:
        trimesh.smoothing.filter_taubin(welded, iterations=2)
        welded.fix_normals()
    except Exception as e:
        ek = f"; ⚠ yumuşatma/normal düzeltme BAŞARISIZ ({type(e).__name__}) — köprü yüzeyi ham"
    return welded, (f"{len(parts)} kopuk eş-eksenli segment → tek watertight cisme "
                    "kaynatıldı (konveks-zarf köprüleme; exploded/kopuk-ihraç onarımı)" + ek)


def prepare_geometry(path, out_dir: Path, progress_cb=None,
                     auto_orient: bool = True) -> tuple[Path, dict]:
    """Her formatı analiz-hazır tek STL'e indirger: CAD dönüşümü, çok-gövde
    birleştirme, normal/sarım onarımı, delik kapatma. Onarım kaydı döner.
    auto_orient=False: canonicalize_axial atlanır — çağıran nose/up eksenini
    açıkça veriyorsa çift-dönme olmasın."""
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    info = {"kaynak": path.name, "onarimlar": []}

    if path.suffix.lower() in CAD_EXTS:
        if progress_cb:
            progress_cb(1, f"CAD dönüşümü (gmsh): {path.name}")
        path = convert_cad_to_stl(path, out_dir / f"{path.stem}_cad.stl")
        info["onarimlar"].append("CAD→STL dönüşümü (gmsh yüzey mesh)")

    m = trimesh.load(str(path), force="mesh")   # Scene ise gövdeler birleştirilir
    if not isinstance(m, trimesh.Trimesh) or len(m.faces) == 0:
        raise ValueError(f"Model okunamadı veya boş: {path}")

    try:
        info["govde_sayisi"] = len(m.split(only_watertight=False))
    except Exception:
        info["govde_sayisi"] = 1

    before_wt = bool(m.is_watertight)
    n_face0 = len(m.faces)
    try:
        m.process(validate=True)                # tekil nokta birleştirme + dejenere üçgen temizliği
        if len(m.faces) != n_face0:
            info["onarimlar"].append(f"dejenere/yinelenen üçgen temizliği ({n_face0}→{len(m.faces)})")
    except Exception:
        # trimesh fix_winding bazı çok-parçalı/tutarsız sarımlı mesh'lerde çöker;
        # onarımı atla, ham mesh ile devam et (analiz yine de koşar).
        info["onarimlar"].append("uyarı: tam topoloji onarımı atlandı (sarım tutarsız)")
    try:
        trimesh.repair.fix_normals(m)
        info["onarimlar"].append("normal/sarım onarımı")
    except Exception as e:
        # Yalnız BAŞARILAR kaydediliyordu; başarısızlık sessizdi ve çağıran
        # "onarım listesi kısa" ile "onarım denenmedi"yi ayırt edemiyordu.
        info["onarimlar"].append(f"⚠ normal/sarım onarımı BAŞARISIZ ({type(e).__name__})")
    if not m.is_watertight:
        try:
            if trimesh.repair.fill_holes(m) and m.is_watertight:
                info["onarimlar"].append("delik kapatma (su geçirmez hale getirildi)")
            elif not m.is_watertight:
                info["onarimlar"].append("⚠ delik kapatma denendi, model YİNE su geçirmez "
                                         "değil — snappyHexMesh iç yüzey/kaçak görebilir")
        except Exception as e:
            info["onarimlar"].append(f"⚠ delik kapatma BAŞARISIZ ({type(e).__name__}) — "
                                     "model su geçirmez değil")
    info["su_gecirmez_once"] = before_wt

    # Kopuk eş-eksenli segmentleri kaynat (roket exploded/kopuk-ihraç → tek cisim).
    # Akış boşluklardan geçip Cd'yi bozuyordu; muhafazakâr guard montajlara dokunmaz.
    m, _weld = weld_axial_segments(m)
    if _weld:
        info["onarimlar"].append(_weld)
        info["kaynak_birlestirme"] = _weld
    info["su_gecirmez_sonra"] = bool(m.is_watertight)

    # Yönelim: eksenel cismi (roket/füze) uçuş yönüne hizala (uzun eksen→+x).
    if auto_orient:
        m, _orient = canonicalize_axial(m)
        if _orient:
            info["onarimlar"].append(_orient)
            info["yonelim"] = _orient

    # Birim sezgisi: CAD (STEP/IGES) konvansiyonel mm; çözücü metre bekler.
    # BİLSEM araçları (roket/İHA/dron) 0.05–10 m; >50 birim => mm, ÷1000.
    lmax = float((m.bounds[1] - m.bounds[0]).max())
    if lmax > 50.0:
        m.apply_scale(0.001)
        info["onarimlar"].append(f"birim ölçek mm→m (÷1000; ham Lmax={lmax:.0f})")
        info["birim_olcek"] = "mm→m"

    prepared = out_dir / f"{Path(info['kaynak']).stem}_prep.stl"
    m.export(str(prepared))
    return prepared, info


AXIS_VECTORS = {
    "+x": np.array([1.0, 0, 0]), "-x": np.array([-1.0, 0, 0]),
    "+y": np.array([0, 1.0, 0]), "-y": np.array([0, -1.0, 0]),
    "+z": np.array([0, 0, 1.0]), "-z": np.array([0, 0, -1.0]),
}


def orientation_matrix(nose_axis: str, up_axis: str) -> np.ndarray:
    """Modeli burun→+x, üst→+z olacak şekilde döndüren 3x3 matris.
    nose ve up dik olmalı (aynı/karşıt eksen kabul edilmez)."""
    nose = AXIS_VECTORS[nose_axis]
    up = AXIS_VECTORS[up_axis]
    if abs(float(nose @ up)) > 1e-9:
        raise ValueError(f"Burun ({nose_axis}) ve üst ({up_axis}) eksenleri dik olmalı")
    side = np.cross(up, nose)            # sağ-el: y = z × x
    return np.vstack([nose, side, up])   # satırlar: hedef eksenlerin kaynak ifadesi


def orient_mesh(stl_path: Path, nose_axis: str, up_axis: str, out_path: Path) -> Path:
    """STL'i akış çerçevesine (+x burun, +z üst) döndürüp out_path'e yazar."""
    if nose_axis == "+x" and up_axis == "+z":
        return Path(stl_path)
    m = trimesh.load(str(stl_path), force="mesh")
    T = np.eye(4)
    T[:3, :3] = orientation_matrix(nose_axis, up_axis)
    m.apply_transform(T)
    m.export(str(out_path))
    return out_path


def _hull_projected_area(vertices: np.ndarray, drop_axis: int) -> float:
    """Konveks-zarf izdüşüm alanı (üst sınır kestirimi)."""
    pts2 = np.delete(vertices, drop_axis, axis=1)
    try:
        return float(ConvexHull(pts2).volume)   # 2D'de volume = alan
    except Exception:
        mn, mx = pts2.min(0), pts2.max(0)
        return float((mx[0]-mn[0]) * (mx[1]-mn[1]))


def _thin_flatness(m: trimesh.Trimesh, nb: int = 12) -> float:
    """Açıklık (en-uzun eksen) boyunca yerel yassılık profilinin alt-yüzdeliği:
    her dilimde kalınlık(en-ince eksen)/kiriş(orta eksen). İnce kaldırma yüzeyi
    (kanat) düşük (~0.1), kalın harmanlanmış/küt gövde yüksek (~0.4–1.0) verir.
    Yönelimden bağımsız (eksenler ekstent'e göre sıralanır)."""
    mm = m
    while len(mm.vertices) < 400:          # düşük-poligon (box) → yoğunlaştır
        mm = mm.subdivide()
    V = np.asarray(mm.vertices, float)
    V = V - V.mean(0)
    order = np.argsort(V.max(0) - V.min(0))           # küçük→büyük eksen
    a_long, a_mid, a_thin = order[2], order[1], order[0]
    y = V[:, a_long]
    edges = np.linspace(y.min(), y.max(), nb + 1)
    flat = []
    for i in range(nb):
        sel = (y >= edges[i]) & (y < edges[i + 1])
        if int(sel.sum()) < 5:
            continue
        chord = float(np.ptp(V[sel, a_mid]))
        thick = float(np.ptp(V[sel, a_thin]))
        if chord > 1e-9:
            flat.append(thick / chord)
    return float(np.percentile(flat, 20)) if flat else 1.0


def _radial_solidity(m: trimesh.Trimesh) -> float:
    """Üst-görünüm (en-ince eksene dik) DOLULUK: siluet-alanı / konveks-zarf-alanı.
    Radyal-kollu cisim (multikopter: gövde+ince kollar, aralarda boşluk) DÜŞÜK (~0.2);
    sürekli yüzey (kanat/küt gövde) YÜKSEK (~0.5–1.0). 'Radyal-simetri/spoke' ayırt edici —
    multikopter↔kanat bbox-örtüşmesini çözer (govde dejenere olduğunda bile çalışır)."""
    ext = m.bounds[1] - m.bounds[0]
    keep = [i for i in range(3) if i != int(np.argmin(ext))]
    V2 = np.asarray(m.vertices, float)[:, keep]
    tris = V2[m.faces]
    a, b = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    sil = 0.5 * float(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum()) * 0.5  # ~2-katman
    try:
        hull = float(ConvexHull(V2).volume)              # 2B'de volume = alan
    except Exception:
        return 1.0
    return round(min(sil / hull, 1.0), 4) if hull > 1e-12 else 1.0


DONEL_KATLAR = (3, 4, 5, 6, 8)
# 2-kat KASITLI dışarıda: uçağın üst-görünümü de 180°'de büyük ölçüde örtüşür, o yüzden
# 2-kat simetri "radyal çok-rotorlu" ile "kanatlı"yı ayırmaz. 3+ kat radyal topolojiye özgü.


def _donel_simetri(m: trimesh.Trimesh) -> float | None:
    """Üst-görünüm siluetinin en iyi DÖNEL SİMETRİSİ (IoU) — multikopter↔kanat ayırıcısı.

    Siluet, ağırlık merkezi etrafında 360/k derece döndürülüp orijinaliyle kesişim/
    birleşim alanı alınır; k ∈ DONEL_KATLAR üzerinden EN İYİSİ döner. Quadcopter k=4'te,
    tri-kopter k=3'te, hexa k=6'da kendine oturur (≈1.0); uçağın kanadı bir yöne gövdesi
    diğerine uzandığı için hiçbir katta oturmaz (≈0.3); roket en düşük (≈0.05).

    Yalnız 90° bakan ilk sürüm YETERSİZDİ ve bunu ayrı NX EĞİTİM ailesi yakaladı:
    tri-kopter 0.08, hexa-kopter 0.15 ölçüldü (90°, 120° ve 60° simetriyi görmez).
    Test ailesinde yalnız 4-kollu quad vardı, orada kusursuz görünüyordu.

    NEDEN GEREKLİ: kuralın multikopter dalı H/L ≥ 0.3 istiyordu ve bilinen 33
    multikopterin hepsi ≤ 0.28 olduğu için DAL HİÇ ATEŞLENMİYORDU. Eşiği gevşetmek
    denendi ve GERİLEDİ (ayrık NX setinde kural doğruluğu %51.2 → %34.1), çünkü
    mevcut ayırt edici olan radyal doluluk multikopter (0.25–0.39) ile uçağı
    (0.34–0.42) ayırmıyor. Ayıran şey yassılık değil DÖNEL SİMETRİ.

    Döner None: siluet çıkarılamadı (su-geçirmez olmayan/bozuk geometri) — çağıran
    bunu "bilinmiyor" saymalı, 0 ya da 1 varsaymamalı.
    """
    try:
        from shapely import affinity
        from trimesh.path import polygons as _tp
    # sessiz-yutma: kabul — None = 'bilinmiyor'; kural dalı bu durumda ATEŞLENMEZ (test_kural_simetri_yoksa_ateslenmez)
    except Exception:
        return None
    try:
        ext = m.bounds[1] - m.bounds[0]
        normal = [0.0, 0.0, 0.0]
        normal[int(np.argmin(ext))] = 1.0        # _radial_solidity ile aynı "üst" tanımı
        poly = _tp.projected(m, normal=normal)
        if poly is None or poly.is_empty or poly.area <= 0:
            return None
        merkez = poly.centroid
        en_iyi = 0.0
        for kat in DONEL_KATLAR:
            dondurulmus = affinity.rotate(poly, 360.0 / kat, origin=merkez)
            birlesim = poly.union(dondurulmus).area
            if birlesim > 0:
                en_iyi = max(en_iyi, poly.intersection(dondurulmus).area / birlesim)
        return round(en_iyi, 4)
    # sessiz-yutma: kabul — None = 'bilinmiyor'; kural dalı bu durumda ATEŞLENMEZ (test_kural_simetri_yoksa_ateslenmez)
    except Exception:
        return None


def _fasetli_egrilik_orani(m: trimesh.Trimesh, alt: float = 1.0, ust: float = 30.0) -> float:
    """ARA açılı (1°–30°) komşu yüz oranı — geometride EĞRİLİK var mı?

    Gerçek çok-yüzlüde (küp, tetrahedron) komşu yüzler ya düzlemsel (0°) ya keskindir;
    ara açı YOKTUR. Fasetli bir eğri yüzeyde (küre, ince bölünmüş silindir) ara açılar
    doludur. Küp tam olarak 12 üçgendir — bu bir yaklaşım değil, kesin geometridir;
    üçgen-sayısı uyarısı ona verilmemelidir.
    """
    a = np.degrees(m.face_adjacency_angles)
    return round(float(((a >= alt) & (a <= ust)).mean()) if len(a) else 0.0, 4)


def _keskin_kenar_orani(m: trimesh.Trimesh, esik_deg: float = 30.0) -> float:
    """Komşu yüz çiftlerinin kaçında dihedral açı > eşik (keskin kenar).

    Ayrılma noktasını ne belirler sorusunun proxy'si: keskin kenar ayrılmayı GEOMETRİK
    olarak sabitler (küp 0.67, silindir 0.33), pürüzsüz gövdede (küre/kapsül 0.00)
    ayrılma sınır-tabaka geçişine bağlıdır ve tam-türbülanslı RANS sistematik şaşırır.
    """
    a = m.face_adjacency_angles
    return round(float((a > np.radians(esik_deg)).sum() / max(len(a), 1)), 4)


def inspect_geometry(stl_path: Path) -> dict:
    m = trimesh.load(str(stl_path), force="mesh")
    if not isinstance(m, trimesh.Trimesh):
        raise ValueError(f"Model yüklenemedi: {stl_path}")
    dims = (m.bounds[1] - m.bounds[0]).astype(float)
    return {
        "dosya": Path(stl_path).name,
        "boyutlar_m": [round(float(d), 4) for d in dims],
        "lmax_m": round(float(dims.max()), 4),
        "ucgen_sayisi": int(len(m.faces)),
        "su_gecirmez": bool(m.is_watertight),
        "yuzey_alani_m2": round(float(m.area), 5),
        "on_alan_m2": round(_hull_projected_area(m.vertices, 0), 5),     # akış +x
        "yan_alan_m2": round(_hull_projected_area(m.vertices, 1), 5),    # yandan (eksen kontrolü)
        "planform_alan_m2": round(_hull_projected_area(m.vertices, 2), 5),  # üstten
        "ince_kalinlik_m": (lambda t: round(t, 5) if t else None)(estimate_thin_thickness(m)),
        "ince_kalinlik_olculdu": kalinlik_olculdu_mu(),   # ölçüm mü bbox yedeği mi
        # EN İNCE özellik (1. persentil): firar kenarı gibi keskin bölge. Yığın
        # kalınlığından AYRI kısıt — prizma katmanı feasibility'sini bu belirler.
        # 4000 örnek: 200'de p1 kararsız (6.15±4.74 mm), 1000'de ±0.61, 4000'de
        # ±0.20 mm ölçüldü. Firar kenarı yüzeyin küçük bir kesri olduğundan az
        # örnekle nadiren yakalanıyor; maliyet 3k-yüzlü mesh'te ihmal edilebilir.
        "min_ozellik_m": (lambda t: round(t, 6) if t else None)(
            estimate_thin_thickness(m, samples=4000, percentile=1.0)),
        "ince_yassilik": round(_thin_flatness(m), 4),    # kanat-inceliği (bbox-üstü)
        "keskin_kenar_orani": _keskin_kenar_orani(m),    # ayrılma geometrik mi geçiş-güdümlü mü
        "fasetli_egrilik_orani": _fasetli_egrilik_orani(m),  # geometride eğrilik var mı
        "radyal_doluluk": _radial_solidity(m),           # spoke↔sürekli (multikopter ayrımı)
        "donel_simetri": _donel_simetri(m),              # 90° dönel simetri (kopter↔kanat)
    }


# estimate_thin_thickness'in SON çağrısı gerçekten ölçtü mü, yoksa bbox'a mı düştü.
# Çağıran bunu bilmeden "ölçülen ince özellik" diye raporlayamaz.
_son_kaynak: dict = {"olculdu": False, "neden": "henüz çağrılmadı"}


def kalinlik_olculdu_mu() -> dict:
    """Son kalınlık kestiriminin kaynağı: {'olculdu': bool, 'neden': str}."""
    return dict(_son_kaynak)


def estimate_thin_thickness(m: trimesh.Trimesh, samples: int = 200,
                            percentile: float = 10.0) -> float | None:
    """Yüzeyden örneklenmiş yerel et-kalınlığı kestirimi (normal boyunca ray).
    Kanat/fin gibi ince özellikleri bbox'tan çok daha iyi temsil eder; alt
    persentil alınır ki gövde kalınlığı inceyi maskelemesin. (max_sphere
    kenar yakınında sistematik küçük verir — ray doğru semantik.)

    Ray backend (rtree/embree) yoksa ya da ince plaka gibi durumlarda geçerli
    örnek yetersiz kalırsa bbox en-ince-boyutuna düşülür — kaba ama güvenli."""
    extents = (m.bounds[1] - m.bounds[0]).astype(float)
    bbox_min = float(extents[extents > 0].min()) if np.any(extents > 0) else None
    try:
        pts, face_idx = trimesh.sample.sample_surface(m, samples)
        normals = m.face_normals[face_idx]
        th = trimesh.proximity.thickness(m, pts, normals=normals,
                                         method="ray")
        th = th[np.isfinite(th) & (th > 0)]
        if len(th) >= samples // 4:
            _son_kaynak.update(olculdu=True,
                               neden=f"ray ölçümü ({len(th)}/{samples} geçerli örnek)")
            return float(np.percentile(th, percentile))
        _son_kaynak["neden"] = f"yetersiz geçerli örnek ({len(th)}/{samples})"
    except Exception as e:
        # SESSİZ BOZULMA: `rtree` kurulu değilse ray yolu ModuleNotFoundError atar ve
        # burada yutulurdu; çağıran bbox yedeğini ÖLÇÜM sanıyordu (MiniHawk'ta "ince
        # özellik 80 mm" aslında gövde çapıydı, kanat hiç ölçülmemişti). Sebep kaydedilir.
        _son_kaynak["neden"] = f"{type(e).__name__}: {e}"
    _son_kaynak["olculdu"] = False
    return bbox_min


def resolution_warning(lmax_m: float, bg_div: int, ref_max: int, min_dim_m: float,
                       min_cells_across: int = 6, olculdu: bool = True) -> str | None:
    """En ince bbox boyutunun en ince yüzey hücresine oranı — kanat/fin gibi
    ince özelliklerin çözünürlük bekçisi. Yetersizse uyarı metni döner."""
    surf_cell = (lmax_m / bg_div) / (2 ** ref_max)
    n_across = min_dim_m / surf_cell
    if n_across >= min_cells_across:
        return None
    # ÖNERİ 'hassas' DEĞİL 'hassas_nl': bu uyarı tam olarak İNCE özellik varken çıkar ve
    # 'hassas' 12 prizma katmanı ekler — MESH_QUALITY notunun kendisi katmanın ince firar
    # kenarında güvenle örülemediğini, o vakada katmansız yoğun mesh gerektiğini söylüyor.
    return (f"En ince boyut ({min_dim_m:.3g} m) en ince yüzey hücresinin "
            f"~{n_across:.1f} katı (hedef ≥{min_cells_across}) — kanat/fin gibi ince "
            "özellikler yeterince çözülmüyor olabilir; Cl/Cd güvenilirliği için "
            "'--kalite hassas_nl' (katmansız yoğun mesh) önerilir; prizma katmanı "
            "güvenle örülebiliyorsa 'hassas'"
            + ("" if olculdu else
               " | DİKKAT: bu boyut ÖLÇÜLMEDİ, bbox yedeğidir (rtree kurulu olmayabilir) "
               "— gerçek ince özellik (firar kenarı) çok daha küçük olabilir"))


def salinim_analizi(vals, pencere_orani: float = 0.4, min_n: int = 40) -> dict | None:
    """Kuvvet tarihçesinin kuyruğunda SALINIM dedektörü (küp dersi: steady-SIMPLE
    keskin-kenar küt cisimde salınır; tek-değer/kısa-pencere raporu faz-piyangosu).
    Ölçüt: ortalamadan sapmanın ≥4 işaret-geçişi VE genlik > %0.5. Döner:
    {osilasyon, ortalama, genlik, genlik_pct, gecis} | None (kısa tarihçe)."""
    v = [x for x in vals if x is not None and math.isfinite(x)]
    if len(v) < min_n:
        return None
    w = v[-max(min_n, int(len(v) * pencere_orani)):]
    mu = sum(w) / len(w)
    dev = [x - mu for x in w]
    esik = 0.05 * max(abs(d) for d in dev) if any(dev) else 0.0
    isaretler = [1 if d > esik else (-1 if d < -esik else 0) for d in dev]
    isaretler = [s for s in isaretler if s != 0]
    gecis = sum(1 for a, b in zip(isaretler, isaretler[1:]) if a != b)
    genlik = (max(w) - min(w)) / 2.0
    genlik_pct = genlik / (abs(mu) + 1e-12) * 100
    return {"osilasyon": bool(gecis >= 4 and genlik_pct > 0.5),
            "ortalama": mu, "genlik": round(genlik, 6),
            "genlik_pct": round(genlik_pct, 2), "gecis": gecis}


def trailing_mean(vals, fallback, min_n: int = 20):
    """Kuvvet-katsayısı için kuyruk-penceresi ortalaması (son %20, ≥min_n iter).
    Son-iterasyon değeri erken-durdurucunun kestiği noktaya duyarlı (~%1-3 titreşim);
    bu gürültü mesh-seviye farklarıyla yarışıp GCI dizisini sahte-salınımlı gösteriyordu
    (2026-07-07 kampanya bulgusu). Steady-RANS raporlama pratiği: trailing-window mean."""
    v = [x for x in vals if x is not None and math.isfinite(x)]
    if len(v) < min_n:
        return fallback
    w = max(min_n, len(v) // 5)
    return sum(v[-w:]) / w


def parse_checkmesh(log: Path) -> dict:
    out = {"cells": None, "non_ortho_max": None, "skew_max": None, "mesh_ok": None}
    if not log.exists():
        return out
    txt = log.read_text(errors="ignore")
    m = re.search(r"cells:\s+(\d+)", txt)
    if m: out["cells"] = int(m.group(1))
    m = re.search(r"non-orthogonality Max:\s*([\d.]+)", txt)
    if m: out["non_ortho_max"] = float(m.group(1))
    m = re.search(r"Max skewness =\s*([\d.]+)", txt)
    if m: out["skew_max"] = float(m.group(1))
    out["mesh_ok"] = "Mesh OK" in txt
    return out


def yuzey_yuz_sayisi(case_dir: Path, patch: str) -> int | None:
    """constant/polyMesh/boundary'den gövde yamasının GERÇEK yüz sayısı."""
    b = case_dir / "constant" / "polyMesh" / "boundary"
    if not b.exists():
        return None
    t = b.read_text(errors="ignore")
    i = t.find(patch)
    if i < 0:
        return None
    m = re.search(r"nFaces\s+(\d+)", t[i:i + 400])
    return int(m.group(1)) if m else None


def parse_layer_report(log: Path) -> dict:
    """snappyHexMesh'in KENDİ katman raporunu oku — istenen vs EKLENEN katman.

    Katman çökmesi bugüne kadar yalnız DOLAYLI teşhis ediliyordu (ölçülen y⁺ hedefin
    5 katından büyükse "şüphe"). Oysa snappy sonunda tam olarak kaç katman ördüğünü
    ve gerçekleşen kalınlığı bir tabloda YAZIYOR:

        patch    faces    layers   overall thickness
                                   [m]        [%]
        minihawk 12345    0        0          0

    Doğrudan okumak şüpheyi ÖLÇÜME çevirir: 12 katman istenip 0 örülmüşse sonuç,
    sahip olmadığı sınır-tabaka çözünürlüğünü iddia ediyor demektir. MiniHawk
    'hassas' koşusunda ölçülmüştü: mesh katmansız koşuyla BİREBİR aynı hücre
    sayısı (3.943.330) ve y⁺=4113 — snappy katman adımı sessizce çökmüştü.

    Döndürür: {"okundu": bool, "yamalar": [{ad, yuz, katman, kalinlik_m, kalinlik_pct}],
               "neden": str|None}
    """
    out = {"okundu": False, "yamalar": [], "neden": None}
    if not log.exists():
        out["neden"] = f"{log.name} yok — katman adımı hiç koşmamış olabilir"
        return out
    txt = log.read_text(errors="ignore")
    if "overall thickness" not in txt:
        out["neden"] = ("log'da katman tablosu yok (addLayers false ya da katman "
                        "adımına hiç gelinmedi)")
        return out
    # Tablo: son "overall thickness" başlığından sonraki satırlar; ---- ayıracını atla.
    kuyruk = txt[txt.rfind("overall thickness"):].splitlines()[1:]
    for satir in kuyruk:
        s = satir.strip()
        if not s or s.startswith(("[", "-")) or "]" in s.split()[0:1]:
            continue
        t = s.split()
        if len(t) < 5:
            break
        try:
            out["yamalar"].append({"ad": t[0], "yuz": int(t[1]), "katman": int(t[2]),
                                   "kalinlik_m": float(t[3]),
                                   "kalinlik_pct": float(t[4])})
        except ValueError:
            break
    out["okundu"] = bool(out["yamalar"])
    if not out["okundu"]:
        out["neden"] = "katman tablosu bulundu ama satır ayrıştırılamadı"
    return out


def katman_hukmu(rapor: dict, istenen: int, patch: str | None = None) -> dict:
    """İstenen katman örüldü mü? Örülmediyse bunu ÖLÇÜM olarak söyle.

    'Katman istenip alınamamak, hiç istememekten TEHLİKELİDİR' — sonuç sahip
    olmadığı çözünürlüğü iddia eder. Bu yüzden hüküm y⁺'a DEĞİL, snappy'nin kendi
    sayımına dayanır; y⁺ bağımsız bir ikinci kanıttır.
    """
    if istenen <= 0:
        return {"durum": "katman_istenmedi", "istenen": 0}
    if not rapor.get("okundu"):
        return {"durum": "olculemedi", "istenen": istenen,
                "neden": rapor.get("neden") or "katman raporu okunamadı"}
    ilgili = [y for y in rapor["yamalar"]
              if patch is None or y["ad"] == patch] or rapor["yamalar"]
    eklenen = max((y["katman"] for y in ilgili), default=0)
    d = {"istenen": istenen, "eklenen": eklenen,
         "kalinlik_m": max((y["kalinlik_m"] for y in ilgili), default=0.0),
         "yamalar": ilgili}
    if eklenen == 0:
        d["durum"] = "COKTU"
    elif eklenen < istenen * 0.5:
        d["durum"] = "kismi"
    else:
        d["durum"] = "ok"
    return d


def propeller_params(thrust_n: float, cap_m: float, velocity: float,
                     rho: float = 1.225) -> dict:
    """Froude aktüatör diski: hedef itkiden indüksiyon faktörü.
    OF11 actuationDiskSource T = 2A·U₀²·a(1−a); diskDir akış yönünde (+x)
    seçilince kaynak akışkanı İTER (pervane). Froude sınırı τ ≤ 0.25."""
    area = math.pi * (cap_m / 2) ** 2
    tau = thrust_n / (2 * rho * area * velocity ** 2)
    uyari = None
    if tau > 0.24:
        uyari = (f"İtki Froude sınırını aşıyor (τ={tau:.2f}>0.25; bu hız/çapta "
                 f"max ~{0.24 * 2 * rho * area * velocity**2:.1f} N) — sınıra kapatıldı")
        tau = 0.24
    a = (1 - math.sqrt(1 - 4 * tau)) / 2
    ct = 0.7
    return {"itki_N": thrust_n, "cap_m": cap_m, "area": area,
            "a": round(a, 4), "Cp": round(ct * (1 - a), 4), "Ct": ct,
            "tau": round(tau, 4), "uyari": uyari}


def first_layer_height(velocity, lref, yplus_target, nu=1.5e-5):
    """Hedef y⁺ için ilk prizma katmanı YÜKSEKLİĞİ (m).
    Düz-plaka türbülanslı korelasyon: Cf=0.026·Re⁻¹ᐟ⁷, u*=V√(Cf/2),
    y₁=y⁺·ν/u* hücre MERKEZİ olduğundan yükseklik = 2·y₁."""
    re = max(velocity * lref / nu, 1e3)
    cf = 0.026 / re ** (1 / 7)
    utau = velocity * math.sqrt(cf / 2)
    return 2.0 * yplus_target * nu / utau


def measure_yplus(case_dir, patch: str | None = None, timeout=600) -> dict | None:
    """Çözülmüş alanda duvar y⁺'ını ÖLÇER (varsayım değil; foamPostProcess).
    patch verilirse O patch'in bloğundan okur — zemin-etkili kurulumda bottom da
    wall olduğundan ilk-eşleşme ZEMİNİN y⁺'ını veriyordu (5200'lük hayalet:
    2026-07-12 Ahmed teşhisi); gövde patch'ine kilitlenmek şart."""
    try:
        r = _wsl_run(windows_to_wsl_path(case_dir),
                     "foamPostProcess -solver incompressibleFluid -func yPlus -latestTime 2>&1",
                     timeout=timeout)
        out = r.stdout
        if patch:
            i = out.find(patch)
            if i >= 0:
                out = out[i:]
        m = re.search(r"y\+ : min = ([\d.eE+-]+), max = ([\d.eE+-]+), average = ([\d.eE+-]+)",
                      out)
        if m:
            return {"min": round(float(m.group(1)), 2), "max": round(float(m.group(2)), 2),
                    "ort": round(float(m.group(3)), 2), "patch": patch or "ilk-wall"}
        hata = "foamPostProcess çıktısında y⁺ satırı yok"
    except Exception as e:
        hata = f"{type(e).__name__}: {e}"

    # SESSİZ YUTMA YOK. Eskiden bu yol düz `None` dönüyordu ve `yplus: None`, "y⁺
    # ölçülemedi" ile "y⁺ ölçüldü ve iyi" arasında hiçbir fark bırakmıyordu. MiniHawk
    # yeniden koşusunda tam bu oldu: y⁺ ORTALAMA 5399 ölçülmüştü (duvar tümüyle
    # çözümsüz, hedef 30-300) ama sonuç None geldiği için rapor uyaramadı. Ölçüm
    # sonradan aynı case'te elle çalıştı → hata geçiciydi ve sebebi kayboldu.
    # Son çare: diskte kalan yPlus.dat okunur; o da yoksa SEBEP döner.
    d = _yplus_dat_oku(Path(case_dir), patch)
    if d:
        return d
    return {"olculemedi": True, "neden": hata, "patch": patch or "ilk-wall"}


def _yplus_dat_oku(case_dir: Path, patch: str | None) -> dict | None:
    """postProcessing/yPlus/<zaman>/yPlus.dat — foamPostProcess yeniden koşmadan okur."""
    kok = case_dir / "postProcessing" / "yPlus"
    if not kok.is_dir():
        return None
    dosyalar = sorted(kok.rglob("yPlus.dat"),
                      key=lambda f: float(f.parent.name) if
                      f.parent.name.replace(".", "", 1).isdigit() else -1.0)
    if not dosyalar:
        return None
    for satir in reversed(dosyalar[-1].read_text(errors="ignore").splitlines()):
        if satir.startswith("#") or not satir.strip():
            continue
        parca = satir.split()
        if len(parca) >= 5 and (patch is None or patch in parca[1]):
            try:
                return {"min": round(float(parca[2]), 2), "max": round(float(parca[3]), 2),
                        "ort": round(float(parca[4]), 2), "patch": parca[1],
                        "_kaynak": "yPlus.dat (foamPostProcess çıktısı okunamadı)"}
            # sessiz-yutma: kabul — bozuk satır atlanır; hepsi bozuksa çağıran 'olculemedi' sebebini alır
            except ValueError:
                continue
    return None


def export_surface_vtk(case_dir, patch_name: str, timeout=600) -> Path | None:
    """Çözülmüş alandan araç yüzeyini p alanıyla VTK olarak çıkarır
    (foamPostProcess, solver yeniden koşmaz — eski case'lere de uygulanabilir)."""
    case_dir = Path(case_dir)
    func = (
        'type surfaces; libs ("libsampling.so");\n'
        "surfaceFormat vtk; fields (p);\n"
        "interpolationScheme cellPoint;\n"
        f"surfaces ( yuzey {{ type patch; patches ({patch_name}); }} );\n"
    )
    (case_dir / "system" / "yuzeyBasinc").write_text(
        "FoamFile{version 2.0; format ascii; class dictionary; object yuzeyBasinc;}\n" + func)
    try:
        _wsl_run(windows_to_wsl_path(case_dir),
                 "foamPostProcess -solver incompressibleFluid -func yuzeyBasinc "
                 "-latestTime > log.yuzeyBasinc 2>&1", timeout=timeout)
        cands = sorted((case_dir / "postProcessing" / "yuzeyBasinc").rglob("*.vtk")) + \
                sorted((case_dir / "postProcessing" / "yuzeyBasinc").rglob("*.vtp"))
        return cands[-1] if cands else None
    # sessiz-yutma: kabul — görselleştirme çıktısı; yokluğu figür adımında görünür, katsayıları etkilemez
    except Exception:
        return None


def export_cutplane_vtk(case_dir, center, timeout=600) -> Path | None:
    """Simetri düzleminden (y=merkez) hız kesiti VTK'sı çıkarır (foamPostProcess)."""
    case_dir = Path(case_dir)
    cx, cy, cz = center
    func = (
        'type surfaces; libs ("libsampling.so");\n'
        "surfaceFormat vtk; fields (U p);\n"
        "interpolationScheme cellPoint;\n"
        "surfaces ( kesit { type cutPlane; planeType pointAndNormal; "
        f"pointAndNormalDict {{ point ({cx} {cy} {cz}); normal (0 1 0); }} "
        "interpolate true; } );\n"
    )
    (case_dir / "system" / "hizKesiti").write_text(
        "FoamFile{version 2.0; format ascii; class dictionary; object hizKesiti;}\n" + func)
    try:
        _wsl_run(windows_to_wsl_path(case_dir),
                 "foamPostProcess -solver incompressibleFluid -func hizKesiti "
                 "-latestTime > log.hizKesiti 2>&1", timeout=timeout)
        cands = sorted((case_dir / "postProcessing" / "hizKesiti").rglob("kesit.vtk"))
        return cands[-1] if cands else None
    # sessiz-yutma: kabul — görselleştirme çıktısı; yokluğu figür adımında görünür, katsayıları etkilemez
    except Exception:
        return None


def parse_residuals(log: Path) -> dict:
    """foamRun logundan alan bazlı initial-residual tarihçesi."""
    hist: dict[str, list[float]] = {}
    if not log.exists():
        return hist
    pat = re.compile(r"Solving for (\w+), Initial residual = ([\d.eE+-]+)")
    seen_this_iter: set[str] = set()
    for line in log.read_text(errors="ignore").splitlines():
        if line.startswith("Time ="):
            seen_this_iter = set()
            continue
        m = pat.search(line)
        if m and m.group(1) not in seen_this_iter:   # PIMPLE iç döngülerinde ilkini al
            seen_this_iter.add(m.group(1))
            hist.setdefault(m.group(1), []).append(float(m.group(2)))
    return hist


def yakinsama_teshisi(case_dir: Path, forces_history: list, scale: float = 1.0) -> dict:
    """Bir koşunun yakınsama hükmü — ANA KOŞU ve GCI SEVİYELERİ için TEK KAYNAK.

    Ayrı yazılsaydı iki yol kaçınılmaz olarak ayrışırdı; nitekim ayrışmıştı: ana koşu
    rezidüel/drift/salınım ölçüyordu, GCI seviyeleri ise HİÇ ÖLÇMÜYORDU. Sonuç
    MiniHawk kanıtında görülebilir: `rezidual_ok: false` ve `iterasyon: 103` yazarken
    aynı seviyeler Richardson fitine girip GCI %379 üretti. Yakınsamamış çözümlerden
    hesaplanan mesh-bağımsızlık sayısı, hatayı ayrıklaştırmaya YANLIŞ atfeder.
    """
    hist = [(t, c * scale) for t, c, _lc, _ in forces_history]
    n = len(hist)
    drift_pct = None
    if n >= 10:
        w = max(2, n // 5)
        drift_pct = abs(hist[-1][1] - hist[-w][1]) / (abs(hist[-1][1]) + 1e-12) * 100
    residuals = parse_residuals(case_dir / "log.foamRun")
    final_res = {f: (v[-1] if v else None) for f, v in residuals.items()}
    momentum_res = {f: v for f, v in final_res.items()
                    if f.startswith(("Ux", "Uy", "Uz", "p"))}
    res_ok = bool(momentum_res) and all(v is not None and v < RESIDUAL_TARGET
                                        for v in momentum_res.values())
    return {
        "iterasyon": n,
        "cd_drift_son20pct": round(drift_pct, 3) if drift_pct is not None else None,
        "drift_ok": drift_pct is not None and drift_pct < DRIFT_LIMIT_PCT,
        "son_rezidualler": {k: (f"{v:.2e}" if v is not None else None)
                            for k, v in final_res.items()},
        "rezidual_ok": res_ok,
        "salinim": salinim_analizi([h[1] for h in forces_history]),
    }


def seviye_yakinsadi_mi(conv: dict) -> tuple[bool, str]:
    """GCI'ya girmeye uygun mu? Değilse SEBEBİYLE birlikte söyle.

    Ölçüt ana koşununkiyle aynı: rezidüel hedefi + drift + salınım yokluğu.
    Yalnızca biri bile başarısızsa seviye Richardson fitine GİRMEZ; kayıtta gerekçesiyle
    kalır (fizik kapısıyla aynı desen — sessiz atlama yok).
    """
    g = []
    if not conv.get("rezidual_ok"):
        r = conv.get("son_rezidualler") or {}
        kotu = {k: v for k, v in r.items() if k.startswith(("Ux", "Uy", "Uz", "p"))}
        g.append(f"rezidueller hedefin ({RESIDUAL_TARGET:.0e}) uzerinde: {kotu}")
    if not conv.get("drift_ok"):
        g.append(f"Cd drifti son %20'de {conv.get('cd_drift_son20pct')}% "
                 f"(sinir {DRIFT_LIMIT_PCT}%)")
    if (conv.get("salinim") or {}).get("osilasyon"):
        g.append("kuvvet salinimi (limit cevrimi) — sabit noktaya oturmamis")
    if (conv.get("iterasyon") or 0) < 50:
        g.append(f"yalnizca {conv.get('iterasyon')} iterasyon")
    return (not g), "; ".join(g)


@dataclass
class VehicleAnalysisResult:
    status: str
    vehicle_type: str
    stl: str
    velocity: float
    alpha_deg: float
    geometry: dict
    kalite: str = ""                    # MESH_QUALITY preset'i — mentor öğrenmesi için kayıt
    aref_m2: float | None = None
    aref_mode: str = ""
    cd: float | None = None
    cd_wake: float | None = None        # far-field iz-momentum Cd (2.-mertebe çapraz-kontrol)
    # SESSİZ GERİLEMELER: bir savunma/çapraz-kontrol düştüğünde sonuç yine üretilir ama
    # güvencesi azalır. mesh_generator.gerilemeler deseni buraya taşındı; rapor gösterir.
    gerilemeler: list = field(default_factory=list)
    cl: float | None = None
    ld: float | None = None
    cda_m2: float | None = None
    drag_N: float | None = None
    cd_richardson: float | None = None  # 3-mesh GCI Richardson ekstrapolasyonu (mesh→0)
    belirsizlik: dict | None = None      # birleşik UQ: U_toplam = √(U_sayısal² + U_model²)
    mesh: dict | None = None
    convergence: dict | None = None
    uyarilar: list = None
    sinir_tabaka: dict | None = None
    pervane: dict | None = None
    cp_vtk: str = ""
    kesit_vtk: str = ""
    mesh_duyarlilik: dict | None = None
    case_dir: str = ""
    report: str = ""
    error: str = ""
    validity: dict | None = None    # geçerlilik-zarfı verdict'i (okula-güvenli kapı)
    fizik_kabul: dict | None = None  # fiziksel kabul-edilebilirlik kapısı (zarf sınıfından ÖNCE)
    kurulum: list | None = None      # kurulum kapısı (ölçek/eksen/A_ref) — raporun EN ÜSTÜNDE


def run_vehicle_analysis(stl_path, vehicle_type="ucak", velocity=30.0, alpha_deg=0.0,
                         quality="standart", out_root="vehicle_runs",
                         n_processors=0, rho=1.225,
                         nose_axis="+x", up_axis="+z",
                         mesh_sensitivity=False, n_layers=0, yplus_target=30.0,
                         pervane_itki_n=0.0, pervane_cap_m=0.0,
                         ground_clearance=None, mesh_levels=3, refinement_regions=None,
                         max_cells=None, ref_bump=0, turbulence_model="kOmegaSST",
                         progress_cb=None) -> VehicleAnalysisResult:
    stl_path = Path(stl_path)
    stem = stl_path.stem
    preset = VEHICLE_PRESETS[vehicle_type]
    q = MESH_QUALITY[quality]
    if n_layers == 0 and q.get("n_layers", 0) > 0:      # kalite-preset'i duvar-çözünür istiyor (çağıran override etmedi)
        n_layers = q["n_layers"]
        yplus_target = q.get("yplus_target", yplus_target)

    run_dir = Path(out_root) / stem
    run_dir.mkdir(parents=True, exist_ok=True)
    stl_path, prep = prepare_geometry(stl_path, run_dir, progress_cb,
                                      auto_orient=(nose_axis == "+x" and up_axis == "+z"))
    stl_path = orient_mesh(stl_path, nose_axis, up_axis,
                           run_dir / f"{stem}_oriented.stl")
    geo = inspect_geometry(stl_path)
    geo["hazirlik"] = prep
    geo["oryantasyon"] = f"burun={nose_axis} üst={up_axis} → akış çerçevesi (+x, +z)"
    if progress_cb:
        progress_cb(2, f"Geometri: {geo['lmax_m']} m, {geo['ucgen_sayisi']} üçgen")

    # KURULUM KAPISI — çözücüden ÖNCE. Ölçek/eksen/referans-alan hatası saatlerce
    # koşup "geçerli görünen" ama başka bir problemin cevabı olan bir sayı üretir.
    kurulum_uyarilari = geometry_sanity(geo, vehicle_type, velocity, n_layers=n_layers)
    # GEÇİŞ MODELİ ÖN KOŞULU — ÇÖZÜCÜDEN ÖNCE. Langtry-Menter laminer bölgeyi sınır
    # tabakanın İÇİNDE çözer; duvar-fonksiyonu mesh'inde (y⁺≫30) laminer altkatman
    # hiç ayrıklaştırılmaz. Model yine bir sayı üretir ama fiziksel karşılığı YOKTUR
    # — "makul görünen ama anlamsız sonuç" sınıfı. Saatlerce koşup sonra fark etmek
    # yerine baştan reddedilir.
    from analysis.openfoam_runner import gecis_modeli_onkosulu
    _gm = gecis_modeli_onkosulu(turbulence_model, n_layers, yplus_target)
    if _gm:
        # Bu bir CAGIRAN HATASI (katmansiz mesh'te gecis modeli istemek), calisma-zamani
        # durumu degil — sessiz bir uyariyla devam etmek yerine SERT hata dogru.
        raise ValueError(f"GECIS MODELI ON KOSULU: {_gm}")
    for _ku in kurulum_uyarilari:
        if progress_cb:
            progress_cb(3, f"⚠ KURULUM: {_ku}")

    a = math.radians(alpha_deg)
    rmin, rmax = preset["refinement"]
    bump = q["ref_bump"] + ref_bump             # ref_bump: çağıran-özel ek yüzey seviyesi
    q_max = max_cells or q["max_cells"]         # max_cells: hücre tavanı override
    _dom = farfield_domain(preset, alpha_deg)   # lift-bilinçli far-field
    ground_clearance = auto_ground_clearance(preset, geo["boyutlar_m"][2], ground_clearance)
    prop = None
    if pervane_itki_n > 0 and pervane_cap_m > 0:
        prop = propeller_params(pervane_itki_n, pervane_cap_m, velocity, rho)

    # Mach>0.3: sıkışabilir çözücü altyapısı mevcut (foamRun -solver fluid:
    # thermo + T/p/rho/alphat alanları + akı şemaları) ama soğuk-başlangıç
    # kararlılığı tuning gerektiriyor — DENEYSEL, varsayılan KAPALI.
    mach = velocity / 340.0
    compressible = mach > 0.3 and os.environ.get("CFD_COMPRESSIBLE") == "1"
    if compressible:
        rho = 101325.0 / (287.058 * 288.15)
        if progress_cb:
            progress_cb(3, f"Mach {mach:.2f} — DENEYSEL sıkışabilir çözücü (fluid)")
    case = CFDCase(
        name=stem,
        stl_path=stl_path,
        velocity=velocity,
        flow_direction=(math.cos(a), 0.0, math.sin(a)),
        rho=rho,
        domain_upstream=_dom[0],
        domain_downstream=_dom[1],
        domain_lateral=_dom[2],
        refinement_min=max(1, rmin + bump),
        refinement_max=max(1, rmax + bump),
        end_time=q["end_time"],
        max_global_cells=q_max,
        bg_cell_size=geo["lmax_m"] / q["bg_div"],
        n_layers=n_layers,
        turbulence_model=turbulence_model,
        first_layer_thickness=(first_layer_height(velocity, geo["lmax_m"], yplus_target)
                               if n_layers > 0 else None),
        propeller=prop,
        compressible=compressible,
        n_processors=n_processors,
        ground_clearance=ground_clearance,
        refinement_regions=refinement_regions,
    )
    # KATMAN YAPILABİLİRLİĞİ — ÇÖZÜCÜDEN ÖNCE (case kuruldu, henüz koşmadı). En ince
    # özellik (firar kenarı) yüzey hücresinden küçükse snappy o bölgeyi çözemez ve
    # üzerine katman HİÇ öremez. MiniHawk'ta ölçüldü: 12 katman istendi, mesh katmansız
    # koşuyla birebir aynı çıktı — bu 40 dakika sonra keşfedildi, artık başta söyleniyor.
    _min_oz = geo.get("min_ozellik_m")
    if n_layers > 0 and _min_oz:
        _surf = (geo["lmax_m"] / q["bg_div"]) / (2 ** case.refinement_max)
        if _min_oz < _surf:
            _m = (f"KATMAN YAPILAMAZ: en ince özellik {_min_oz * 1000:.2f} mm, yüzey "
                  f"hücresi {_surf * 1000:.1f} mm — özellik hücrenin {_min_oz / _surf:.2f} "
                  f"katı. snappyHexMesh bu bölgeyi çözemez, {n_layers} prizma katmanı "
                  "örülemez (mesh katmansızla aynı çıkar). Ya yüzey seviyesini artırın "
                  "(maliyet üstel) ya geometriyi künt yapın ya da duvar-fonksiyonlu yolu "
                  "kabul edin (--kalite hassas_nl)")
            kurulum_uyarilari.append(_m)
            if progress_cb:
                progress_cb(4, f"⚠ KURULUM: {_m}")
    res = run_cfd(case, run_dir, progress_callback=progress_cb)
    case_dir = res.case_dir

    base = VehicleAnalysisResult(
        status="failed", vehicle_type=vehicle_type, stl=str(stl_path),
        velocity=velocity, alpha_deg=alpha_deg, geometry=geo,
        kalite=quality, case_dir=str(case_dir),
    )
    if not res.success or res.cd is None:
        base.error = (res.stderr or res.stdout)[-2000:]
        (run_dir / "sonuc.json").write_text(json.dumps(asdict(base), indent=2, ensure_ascii=False), encoding="utf-8")
        return base

    # Katsayıları gerçek referans alana ölçekle (forceCoeffs Aref = lref^2 kullanır)
    lref = case.lref
    aref_of = lref * lref
    aref_mode = preset["aref_mode"]
    aref = geo["planform_alan_m2"] if aref_mode == "planform" else geo["on_alan_m2"]
    if aref <= 0:
        aref, aref_mode = aref_of, "lref^2 (fallback)"
    scale = aref_of / aref
    cd_raw = trailing_mean([h[1] for h in res.forces_history], res.cd)
    cl_raw = trailing_mean([h[2] for h in res.forces_history], res.cl)
    cd = cd_raw * scale
    cl = cl_raw * scale if cl_raw is not None and math.isfinite(cl_raw) else None
    q_dyn = 0.5 * rho * velocity**2

    history = [(t, c * scale, (lc * scale if math.isfinite(lc) else float("nan")))
               for t, c, lc, _ in res.forces_history]
    residuals = parse_residuals(case_dir / "log.foamRun")
    meshq = parse_checkmesh(case_dir / "log.checkMesh")

    # Yakınsama teşhisi ORTAK fonksiyondan — GCI seviyeleri de aynısını kullanır.
    conv = yakinsama_teshisi(case_dir, res.forces_history, scale)
    # `sal` AŞAĞIDA iki yerde daha kullanılıyor (salınım uyarısı + belirsizliğe RSS
    # katkısı). Refactor'de satır düşünce ruff NameError'ı yakaladı; 640 test
    # yakalayamadı çünkü bu yol GERÇEK bir CFD koşusu gerektiriyor.
    sal = conv["salinim"]

    base.status = "ok"
    base.aref_m2 = round(aref, 6)
    base.aref_mode = aref_mode
    base.cd = round(cd, 5)
    base.cl = round(cl, 5) if cl is not None else None
    base.ld = round(cl / cd, 2) if (cl is not None and cd) else None
    base.cda_m2 = round(cd * aref, 6)
    base.drag_N = round(cd * aref * q_dyn, 3)
    base.mesh = meshq
    base.convergence = conv

    # Far-field iz-momentum Cd (2.-mertebe). Tek mesh'te yüzey-Cd ile UYUŞMASI yakınsama
    # göstergesi (3-mesh GCI'nin ucuz vekili); AYRIŞMASI az-çözünürlük flag'i.
    cd_wake = None
    try:
        from farfield_drag import compute_case_wake_drag
        w = compute_case_wake_drag(case_dir, U_inf=velocity, A_ref=aref, rho=rho)
        if w and w.get("Cd") is not None:
            cd_wake = round(w["Cd"], 5)
            base.cd_wake = cd_wake
        else:
            base.gerilemeler.append("iz-momentum Cd çapraz-kontrolü sonuç vermedi — "
                                    "yüzey-integral Cd'nin BAĞIMSIZ doğrulaması yok")
    except Exception as e:
        # Bu bir ÇAPRAZ KONTROL: sessizce düşerse Cd tek kaynaklı kalır ve
        # "iki yöntem uyuştu" güvencesi kaybolur, üstelik kaybolduğu görünmez.
        base.gerilemeler.append(f"iz-momentum Cd çapraz-kontrolü DÜŞTÜ "
                                f"({type(e).__name__}: {e}) — Cd tek kaynaklı")

    # Kurulum uyarıları listenin en başında: yanlış kurulmuş bir analizin sonucunu
    # yorumlamanın anlamı yok (fizik kapısı bile geçse).
    uyarilar = list(kurulum_uyarilari)
    # FİZİK KAPISI — zarf sınıfından ve mesh/iterasyon ölçütlerinden ÖNCE gelir: sayısal
    # olarak kusursuz yakınsamış bir koşu da fizik-dışı Cd üretebilir (kaba gridde negatif
    # basınç sürüklemesi). Bu hüküm listenin BAŞINDA durur ki mühendis ilk onu görsün.
    fizik = force_admissibility(cd, cl, alpha_deg)
    base.fizik_kabul = fizik
    if fizik["verdict"] != "ok":
        etiket = ("SONUÇ FİZİK KAPISINDAN GEÇMEDİ" if fizik["verdict"] == "inadmissible"
                  else "SONUÇ FİZİKSEL OLARAK ŞÜPHELİ")
        uyarilar.append(f"{etiket}: {'; '.join(fizik['reasons'])} — bu sayı TASARIM KARARINDA "
                        "KULLANILMAZ; mesh çözünürlüğünü (özellikle iz/wake bölgesi) artırın")
    if cd_wake is not None and cd:
        fark = abs(cd - cd_wake) / abs(cd) * 100
        if fark > 12:
            uyarilar.append(f"Yüzey-Cd ({cd:.3f}) ile iz-momentum Cd ({cd_wake:.3f}) "
                            f"%{fark:.0f} ayrışıyor → mesh az-çözünür/yakınsamamış olabilir "
                            "(çapraz-kontrol; uyum yakınsama göstergesi)")
    elif cd:
        # Kontrolün YAPILAMADIĞI, yapılıp geçtiğiyle karıştırılmamalı: sessiz düşen
        # çapraz-kontrol mühendise "doğrulandı" izlenimi verir.
        uyarilar.append("İz-momentum çapraz-kontrolü YAPILAMADI (far-field Cd çıkarılamadı) "
                        "— bağımsız yakınsama göstergesi yok, Cd tek kaynağa dayanıyor")
    if compressible:
        uyarilar.append(f"Mach {mach:.2f} > 0.3 — DENEYSEL sıkışabilir çözücü "
                        "(soğuk-başlangıç kararlılığı tuning gerektirir)")
    elif mach > 0.3:
        uyarilar.append(f"Mach {mach:.2f} > 0.3 — sıkıştırılamaz çözücü varsayımı "
                        "İHLAL; Cd sistematik hatalı. Sıkışabilir yol deneysel "
                        "(CFD_COMPRESSIBLE=1 ile açılır, kararlılık garantisiz)")
    if ground_clearance is not None:
        uyarilar.append(f"Zemin düzlemi aktif (clearance={ground_clearance:g} m, sabit noSlip) "
                        "— serbest-akış DEĞİL; Cd yalnız zemin-etkili referanslarla kıyaslanır")
    if sal and sal["osilasyon"]:
        uyarilar.append(f"Kuvvet tarihçesi SALINIMLI (genlik ±%{sal['genlik_pct']}, "
                        f"{sal['gecis']} işaret-geçişi) — Cd pencere-ortalamasıdır ve genlik "
                        "sayısal belirsizliğe RSS ile eklendi. Steady-RANS bu rejimde sınırda; "
                        "kalıcı çözüm zaman-doğru (URANS) analizdir")
    if not geo["su_gecirmez"]:
        uyarilar.append("STL su geçirmez değil — snappyHexMesh toleranslı ama "
                        "kapalı yüzey önerilir")
    thin = geo.get("ince_kalinlik_m") or min(geo["boyutlar_m"])
    rw = resolution_warning(geo["lmax_m"], q["bg_div"], case.refinement_max, thin,
                            olculdu=bool((geo.get("ince_kalinlik_olculdu") or {}).get("olculdu")))
    if rw:
        uyarilar.append(rw)
    # Mesh-kalite uyarısı (reject zaten run_cfd'de elendi; warn-seviyesini yüzeye çıkar)
    no_max, sk_max = meshq.get("non_ortho_max"), meshq.get("skew_max")
    if no_max is not None and no_max > NONORTHO_LIMIT:
        uyarilar.append(f"Mesh non-ortogonallik {no_max:.0f}° > {NONORTHO_LIMIT:.0f} eşiği "
                        "— gradyan/Cd doğruluğu sınırda (mesh iyileştir)")
    if sk_max is not None and sk_max > SKEW_LIMIT:
        uyarilar.append(f"Mesh skewness {sk_max:.1f} > {SKEW_LIMIT:.0f} eşiği "
                        "— yerel hata kaynağı (mesh iyileştir)")
    if prop:
        base.pervane = prop
        if prop.get("uyari"):
            uyarilar.append(prop["uyari"])

    if progress_cb:
        progress_cb(78, "y+ olcumu...")
    _patch = Path(stl_path).stem.replace(" ", "_")
    yp = measure_yplus(case_dir, patch=_patch)
    # DOĞRUDAN ÖLÇÜM: snappy'nin kendi katman sayımı. Bugüne kadar katman çökmesi
    # yalnız y⁺'tan ÇIKARSANIYORDU; şimdi "12 istendi, 0 örüldü" diye ölçülüyor.
    kat = katman_hukmu(parse_layer_report(case_dir / "log.snappyHexMesh"),
                       n_layers, _patch)
    base.sinir_tabaka = {"katman_sayisi": n_layers, "yplus": yp,
                         "katman_olcumu": kat,
                         "yplus_hedef": yplus_target if n_layers > 0 else None,
                         "ilk_katman_m": (round(case.first_layer_thickness, 8)
                                          if case.first_layer_thickness else None)}
    # YÜZEY ÇÖZÜNÜRLÜĞÜ — NİYET DEĞİL SONUÇ. `resolution_warning` yüzey hücresini
    # (lmax/bg_div)/2^ref_max diye hesaplıyordu, yani iyileştirmenin UYGULANDIĞINI
    # varsayıyor. MiniHawk'ta 0.010 m rapor edip "sorun yok" derken snappy 0.167 m
    # teslim etmişti: arka plan mesh'i (3.94M) tavanı (2.5M) tek başına doldurmuş,
    # snappy "No cells marked for refinement since reached limit" yazmış ve gövde
    # 74 YÜZLE temsil edilmişti (uzak-alan yamaları 17-31 bin yüz). Bu tek kusur
    # y⁺≈5000'i, 12 katmanın 0 örülmesini ve Cl'in 1/16 çıkmasını birlikte açıklar.
    from analysis.openfoam_runner import yuzey_cozunurluk_hukmu
    _sn = case_dir / "log.snappyHexMesh"
    _yc = yuzey_cozunurluk_hukmu(_sn.read_text(errors="ignore") if _sn.exists() else "",
                                 yuzey_yuz_sayisi(case_dir, _patch))
    base.sinir_tabaka["yuzey_cozunurlugu"] = _yc
    if getattr(case, "bg_bilgi", None):
        base.sinir_tabaka["arka_plan"] = case.bg_bilgi
    if not _yc["cozuldu"]:
        uyarilar.insert(0, "GÖVDE YÜZEYİ ÇÖZÜLMEDİ (ÖLÇÜLDÜ): "
                        + "; ".join(_yc["gerekce"])
                        + ". Bu durumda Cd/Cl SAYISAL olarak üretilir ama GEOMETRİNİN "
                          "cevabı değildir; y⁺ ve katman sonuçları da bundan türer")
    if kat.get("durum") == "COKTU":
        uyarilar.append(
            f"KATMAN ÇÖKTÜ (ÖLÇÜLDÜ): {n_layers} prizma katmanı istendi, snappyHexMesh "
            f"kendi raporunda 0 katman örüldüğünü yazıyor. Sınır tabaka ÇÖZÜLMÜYOR ve "
            "sonuç katmansız koşuyla eşdeğerdir — duvar-çözünür (y⁺≈1) iddiası GEÇERSİZ. "
            "log.snappyHexMesh 'overall thickness' tablosuna bakın; olağan sebepler: "
            "ince firar kenarı, maxThicknessToMedialRatio, yüzey hücresi ilk-katmana "
            "göre çok büyük")
    elif kat.get("durum") == "kismi":
        uyarilar.append(
            f"KATMAN KISMİ (ÖLÇÜLDÜ): {n_layers} istendi, {kat['eklenen']} örüldü "
            f"(gerçekleşen kalınlık {kat.get('kalinlik_m', 0):.3e} m). Sınır tabaka "
            "kısmen çözülüyor; y⁺ hedefi tutmayabilir")
    elif kat.get("durum") == "olculemedi" and n_layers > 0:
        uyarilar.append(f"Katman sayımı ÖLÇÜLEMEDİ ({kat.get('neden')}) — "
                        "duvar çözünürlüğü iddiası doğrulanmamış durumda")
    if progress_cb:
        progress_cb(82, "Yuzey basinc alani cikariliyor...")
    vtk_path = export_surface_vtk(case_dir, Path(stl_path).stem.replace(" ", "_"))
    base.cp_vtk = str(vtk_path) if vtk_path else ""
    bb = trimesh.load(str(stl_path), force="mesh").bounds
    center = [(bb[0][i] + bb[1][i]) / 2 for i in range(3)]
    kesit = export_cutplane_vtk(case_dir, center)
    base.kesit_vtk = str(kesit) if kesit else ""
    # KATMAN ÇÖKMESİ: katman İSTENİP alınamamak, hiç istememekten TEHLİKELİDİR —
    # sonuç sahip olmadığı sınır-tabaka çözünürlüğünü iddia eder. MiniHawk 'hassas'
    # koşusunda ölçüldü: 12 katman istendi, y⁺ hedefi 1.0 idi, mesh katmansız koşuyla
    # BİREBİR aynı çıktı (3.943.330 hücre) ve y⁺=4113 ölçüldü — snappy katman adımı
    # sessizce çökmüş, rapor yine "12 katman" diyordu.
    # `measure_yplus` ÖLÇEMEDİĞİNDE {"olculemedi": True, "neden": ...} döner — bu,
    # sessiz None yerine SEBEBİ taşısın diye eklenmişti. Ama tüketiciler `yp["ort"]`
    # diye indekslemeye devam ediyordu ve ölçüm başarısız olunca TÜM analiz
    # KeyError ile çöküyordu. Güvenilirlik taramasında 12 geometrinin 2'si böyle
    # düştü. Sessiz başarısızlığı görünür yapmak, tüketicileri güncellemeden
    # yapılırsa sessiz hatayı SERT hataya çevirir.
    _ypo = yp.get("ort") if isinstance(yp, dict) else None
    if _ypo is not None and n_layers > 0 and yplus_target and _ypo > 5 * yplus_target:
        uyarilar.append(
            f"KATMAN ÇÖKMESİ ŞÜPHESİ: {n_layers} prizma katmanı istendi ve y⁺ hedefi "
            f"{yplus_target:g} idi, ama ÖLÇÜLEN y⁺={_ypo:.0f} — hedefin "
            f"{_ypo / yplus_target:.0f} katı. snappyHexMesh katman adımı büyük "
            "olasılıkla örülemedi (ince firar kenarı/keskin köşe). Sınır tabaka "
            "ÇÖZÜLMÜYOR; sonuç katmansız koşuyla eşdeğerdir. log.snappyHexMesh "
            "'Layer mesh' bölümünü ve yüzey kalitesini kontrol edin")
    if _ypo is not None and _ypo > 30 and n_layers == 0:
        # BÜYÜKLÜĞE GÖRE DERECELENDİR: duvar fonksiyonu log-bölgesi ~30-300'de geçerlidir.
        # MiniHawk hassas_nl koşusunda y⁺=4113 ölçüldü — üst sınırın 13 katı; buna
        # "sınırda" demek yanıltıcı, sürtünme bileşeni orada ÇÖZÜLMÜYOR.
        _yp = _ypo
        if _yp > 1000:
            uyarilar.append(
                f"Ölçülen y⁺ ort={_yp:.0f} — duvar fonksiyonu geçerlilik bandının "
                f"(~30-300) {_yp / 300:.0f} KATI. Sürtünme sürüklemesi ÇÖZÜLMÜYOR; "
                "Cd yalnız basınç bileşenini temsil eder. Prizma katmanı zorunlu "
                "(--kalite hassas veya --katman N --yplus 1)")
        else:
            uyarilar.append(f"Ölçülen y⁺ ort={_yp} (log bölgesi üstü) — sürtünme "
                            "sürüklemesi duvar fonksiyonu sınırında; katman sayısını artırın")
    elif _ypo is None:
        # "Ölçemedim" ile "iyi" AYNI ŞEY DEĞİL — sebep de yazılır.
        _ned = (yp or {}).get("neden") if isinstance(yp, dict) else None
        uyarilar.append("y⁺ ÖLÇÜLEMEDİ — sınır tabaka çözünürlüğü doğrulanamadı; "
                        "sürtünme sürüklemesinin duvar-fonksiyonu geçerliliği bilinmiyor"
                        + (f" (sebep: {_ned})" if _ned else ""))
    base.uyarilar = uyarilar
    base.kurulum = kurulum_uyarilari     # raporun EN ÜSTÜ: kurulum hatası her şeyi geçersizler

    # Opsiyonel mesh-bağımsızlık: aynı analizi daha kaba seviyelerde koş → 3-mesh Richardson
    # GCI (Celik 2008, Fs=1.25); mesh_levels≥4'te ek 'cokkaba' seviye + LSR (Eça-Hoekstra)
    # bandı — non-asimptotik/salınımlı dizide Richardson'ın veremediği dürüst U'yu verir.
    u_num_pct = None
    u_kaynak = None
    if mesh_sensitivity:
        from report_generator import compute_gci, gci_verdict, least_squares_gci
        cells_fine = (meshq or {}).get("cells")
        levels = [{"ad": "ince", "cells": cells_fine, "Cd": cd}] if cells_fine else []
        # Seviye ayrımı SABİT ORAN ile (Celik 2008: r ≥ 1.3). Eski kurulum taban hücreyi
        # `lmax / max(3, bg_div - ddiv)` ile kırpıyordu; bg_div=5 (hizli) presetinde orta
        # ve kaba seviyeler AYNI 3'e düşüp aynı mesh'i üretiyor, GCI sessizce
        # "hesaplanamadı" oluyordu (küp kampanyası: iki seviye de 70022 hücre).
        basarisiz: list[dict] = []
        GCI_ORANI = 1.5
        bg_ince = geo["lmax_m"] / q["bg_div"]
        kademeler = [("orta", 1, GCI_ORANI, q["end_time"]),
                     ("kaba", 2, GCI_ORANI ** 2, MESH_QUALITY["hizli"]["end_time"])]
        if mesh_levels >= 4:
            kademeler.append(("cokkaba", 3, GCI_ORANI ** 3,
                              MESH_QUALITY["hizli"]["end_time"]))
        for ad, dref, oran, et in kademeler:
            if progress_cb:
                progress_cb(80, f"Mesh-bağımsızlık: {ad} seviye koşusu…")
            lvl = CFDCase(
                name=f"{stem}_{ad}", stl_path=stl_path, velocity=velocity,
                flow_direction=(math.cos(a), 0.0, math.sin(a)), rho=rho,
                domain_upstream=_dom[0], domain_downstream=_dom[1], domain_lateral=_dom[2],
                refinement_min=max(1, rmin + bump - dref),
                refinement_max=max(1, rmax + bump - dref),
                end_time=et, max_global_cells=q_max,
                bg_cell_size=bg_ince * oran,
                n_layers=n_layers, first_layer_thickness=case.first_layer_thickness,
                n_processors=n_processors, ground_clearance=ground_clearance,
                refinement_regions=refinement_regions,
            )
            r = run_cfd(lvl, run_dir, progress_callback=None)
            mq = parse_checkmesh(r.case_dir / "log.checkMesh") if r.success else {}
            if not (r.success and r.cd is not None and mq.get("cells")):
                # SESSİZ ATLAMA YOK: düşen seviye kampanyadan sessizce çıkarsa kullanıcı
                # "yalnız 2 seviye tamamlandı" görür ve NEDENİNİ bilemez. MiniHawk'ta
                # 'orta' seviye mesh kalite kapısında reddedilmişti (checkMesh: Failed 1).
                _sebep = ((r.stderr or r.stdout or "")[-160:] if not r.success
                          else "Cd çıkarılamadı" if r.cd is None else "checkMesh okunamadı")
                basarisiz.append({"ad": ad, "sebep": _sebep.strip() or "bilinmiyor"})
                continue
            cd_lvl = trailing_mean([h[1] for h in r.forces_history], r.cd)
            lv_rec = {"ad": ad, "cells": mq["cells"], "Cd": round(cd_lvl * scale, 5)}
            try:
                w = compute_case_wake_drag(r.case_dir, U_inf=velocity, A_ref=aref, rho=rho)
                if w and w.get("Cd") is not None:
                    lv_rec["Cd_wake"] = round(w["Cd"], 5)
            except Exception as e:
                lv_rec["Cd_wake_hata"] = f"{type(e).__name__}: {e}"
            # FİZİK KAPISI seviye bazında: MiniHawk kampanyasında en kaba seviye
            # Cd=0.0 üretti (uçak hiç çözülmemiş) ve bu fizik-dışı değer Richardson
            # fitine girip GCI'ı %226'ya şişirdi. Fizik-dışı seviye fite GİRMEZ,
            # kayda gerekçesiyle kalır (vehicle_polar ile aynı desen).
            lv_rec["fizik"] = force_admissibility(lv_rec["Cd"], None, alpha_deg)
            # YAKINSAMA KAPISI seviye bazında — fizik kapısıyla AYNI desen.
            # Fizik kapısı "Cd fiziksel mi" sorar; bu "Cd OTURDU MU" sorar. İkincisi
            # yoktu ve MiniHawk kanıtında sonucu görülüyor: ana koşu `rezidual_ok:
            # false`, `iterasyon: 103` derken aynı seviyeler Richardson fitine girdi
            # ve GCI %379 çıktı. Yakınsamamış üç noktadan hesaplanan mesh-bağımsızlık
            # sayısı hatayı AYRIKLAŞTIRMAYA yanlış atfeder.
            lv_conv = yakinsama_teshisi(r.case_dir, r.forces_history, scale)
            ok, neden = seviye_yakinsadi_mi(lv_conv)
            lv_rec["yakinsama"] = {"gecti": ok, "iterasyon": lv_conv["iterasyon"],
                                   "rezidual_ok": lv_conv["rezidual_ok"],
                                   "drift_ok": lv_conv["drift_ok"]}
            if not ok:
                lv_rec["yakinsama"]["gerekce"] = neden
            levels.append(lv_rec)
        def _fizik_disi(lv):
            return (lv.get("fizik") or {}).get("verdict") == "inadmissible"

        def _yakinsamadi(lv):
            return not (lv.get("yakinsama") or {}).get("gecti", True)

        dislanan = [lv for lv in levels if _fizik_disi(lv)]
        yakinsamayan = [lv for lv in levels if not _fizik_disi(lv) and _yakinsamadi(lv)]
        levels = [lv for lv in levels
                  if lv.get("cells") and not _fizik_disi(lv) and not _yakinsamadi(lv)]
        levels.sort(key=lambda lv: lv["cells"])              # kaba→ince
        def h(lv):                                           # 3B temsili hücre boyu
            return lv["cells"] ** (-1.0 / 3.0)
        if len(levels) >= 3:
            f3, f2, f1 = levels[-3], levels[-2], levels[-1]
            gci = compute_gci(h(f3), h(f2), h(f1), f3["Cd"], f2["Cd"], f1["Cd"])
            # Dejenere seviye: iki kademe pratikte AYNI mesh'i ürettiyse GCI matematiksel
            # olarak tanımsızdır. "hesaplanamadı" demek sebebi gizler; kullanıcı saatlerce
            # compute yakıp neyi düzelteceğini bilemez.
            dejenere = [f"{a['ad']}↔{b['ad']} ({a['cells']}≈{b['cells']} hücre)"
                        for a, b in zip(levels, levels[1:])
                        if abs(a["cells"] - b["cells"]) / max(a["cells"], 1) < 0.05]
            if gci:
                verdikt = gci_verdict(gci)
            elif dejenere:
                verdikt = ("⚠️ GCI HESAPLANAMADI: seviyeler ayrışmadı — " +
                           ", ".join(dejenere) +
                           ". Mesh çözünürlüğü tabana dayandı; daha ince bir kalite "
                           "preset'i (--kalite standart/hassas) veya daha büyük "
                           "--seviyeler ile tekrarlayın")
            else:
                verdikt = ("⚠️ GCI HESAPLANAMADI: seviyeler arası Cd farkı sayısal "
                           "gürültü mertebesinde (Richardson tanımsız)")
            base.mesh_duyarlilik = {"seviyeler": levels, "gci": gci, "verdikt": verdikt}
            if basarisiz:
                base.mesh_duyarlilik["basarisiz_seviyeler"] = basarisiz
            if dejenere:
                base.mesh_duyarlilik["dejenere_seviyeler"] = dejenere
            if dislanan:
                base.mesh_duyarlilik["fizik_disi_seviyeler"] = [
                    {"ad": lv["ad"], "cells": lv["cells"], "Cd": lv["Cd"],
                     "gerekce": "; ".join((lv.get("fizik") or {}).get("reasons", []))}
                    for lv in dislanan]
            if yakinsamayan:
                # SESSİZ ATLAMA YOK: dışlanan seviye kayıtta gerekçesiyle kalır,
                # yoksa kullanıcı "3 seviye koştum, GCI yok" görür ve sebebini bilemez.
                base.mesh_duyarlilik["yakinsamayan_seviyeler"] = [
                    {"ad": lv["ad"], "cells": lv["cells"], "Cd": lv["Cd"],
                     "gerekce": (lv.get("yakinsama") or {}).get("gerekce", "")}
                    for lv in yakinsamayan]
            lsr = (least_squares_gci([h(lv) for lv in levels], [lv["Cd"] for lv in levels])
                   if len(levels) >= 4 else None)
            if lsr:
                base.mesh_duyarlilik["lsr"] = lsr
            # İz-momentum (wake) yolu: 2. mertebe, TE/yüzey-çözünürlüğüne az duyarlı —
            # roket bulgusu: yüzey-GCI çökerken yüzey↔iz %2.7'ye kapanıyordu. Yüzey yolu
            # kanıt veremezse drag kanıtı buradan gelebilir.
            wake_lv = [lv for lv in levels if lv.get("Cd_wake") is not None]
            gci_w = lsr_w = None
            if len(wake_lv) >= 3:
                w3, w2, w1 = wake_lv[-3], wake_lv[-2], wake_lv[-1]
                gci_w = compute_gci(h(w3), h(w2), h(w1),
                                    w3["Cd_wake"], w2["Cd_wake"], w1["Cd_wake"])
                lsr_w = (least_squares_gci([h(lv) for lv in wake_lv],
                                           [lv["Cd_wake"] for lv in wake_lv])
                         if len(wake_lv) >= 4 else None)
                base.mesh_duyarlilik["wake"] = {
                    "gci": gci_w, "lsr": lsr_w,
                    "verdikt": gci_verdict(gci_w) if gci_w else "hesaplanamadı"}
            wake_ok = gci_w and str(base.mesh_duyarlilik["wake"]["verdikt"]).startswith("✅")
            # U_sayısal hiyerarşisi: yüzey-GCI✅ > wake-GCI✅ > yüzey-LSR > wake-LSR > ham GCI
            if gci and str(base.mesh_duyarlilik["verdikt"]).startswith("✅"):
                u_num_pct, u_kaynak = gci["gci_fine_pct"], "GCI (3-mesh, asimptotik)"
                base.cd_richardson = gci["f_exact"]
            elif wake_ok:
                u_num_pct = gci_w["gci_fine_pct"]
                u_kaynak = "wake-GCI (iz-momentum, 2. mertebe, asimptotik)"
                base.cd_richardson = gci_w["f_exact"]
            elif lsr:
                u_num_pct, u_kaynak = lsr["u_pct"], f"LSR ({lsr['n']}-seviye; {lsr['kural']})"
                base.cd_richardson = lsr["f_exact"]
            elif lsr_w:
                u_num_pct = lsr_w["u_pct"]
                u_kaynak = f"wake-LSR ({lsr_w['n']}-seviye; {lsr_w['kural']})"
                base.cd_richardson = lsr_w["f_exact"]
            elif gci:
                u_num_pct = gci["gci_fine_pct"]
                u_kaynak = "GCI (asimptotik DEĞİL — band güvenilirliği düşük)"
                base.cd_richardson = gci["f_exact"]
        elif len(levels) == 2:                               # 3. seviye düştü → 2-mesh vekil-bant
            d = abs(levels[-1]["Cd"] - levels[0]["Cd"]) / (abs(levels[-1]["Cd"]) + 1e-12) * 100
            u_num_pct = round(d, 1)
            u_kaynak = "2-mesh vekil bant"
            base.mesh_duyarlilik = {
                "seviyeler": levels, "fark_pct": u_num_pct,
                "yorum": "yalnız 2 seviye tamamlandı — vekil bant, GCI değil"
                         + ("; DÜŞEN SEVİYE: "
                            + "; ".join(f"{b['ad']} ({b['sebep'][:80]})" for b in basarisiz)
                            if basarisiz else ""),
                **({"basarisiz_seviyeler": basarisiz} if basarisiz else {}),
                **({"yakinsamayan_seviyeler": [
                    {"ad": lv["ad"], "cells": lv["cells"], "Cd": lv["Cd"],
                     "gerekce": (lv.get("yakinsama") or {}).get("gerekce", "")}
                    for lv in yakinsamayan]} if yakinsamayan else {})}
        else:
            # "Yetersiz seviye" tek başına eyleme geçirilebilir bilgi değil — NEDEN
            # yetersiz kaldığı yazılmalı. Yakınsama kapısı eklendikten sonra en olası
            # sebep budur ve çözümü farklıdır (daha çok iterasyon, daha iyi mesh)
            # başarısız seviyeninkinden (daha küçük bütçe).
            _ned = []
            if yakinsamayan:
                _ned.append(f"{len(yakinsamayan)} seviye YAKINSAMADI")
            if dislanan:
                _ned.append(f"{len(dislanan)} seviye fizik-dışı")
            if basarisiz:
                _ned.append(f"{len(basarisiz)} seviye koşamadı")
            base.mesh_duyarlilik = {
                "durum": "yetersiz seviye — bant hesaplanamadı"
                         + (" (" + ", ".join(_ned) + ")" if _ned else ""),
                **({"yakinsamayan_seviyeler": [
                    {"ad": lv["ad"], "cells": lv["cells"], "Cd": lv["Cd"],
                     "gerekce": (lv.get("yakinsama") or {}).get("gerekce", "")}
                    for lv in yakinsamayan]} if yakinsamayan else {}),
                **({"basarisiz_seviyeler": basarisiz} if basarisiz else {})}

    # Birleşik belirsizlik (ASME V&V 20): U_total = √(U_sayısal² + U_model²).
    # Salınım genliği sayısal bileşene RSS ile katılır (Eça-Hoekstra salınım kuralı ruhu).
    from validation_anchors import combine_uncertainty, model_uncertainty_pct, regime_of
    u_sal_pct = sal["genlik_pct"] if (sal and sal["osilasyon"]) else None
    if u_sal_pct is not None:
        u_num_pct = round(math.sqrt((u_num_pct or 0.0) ** 2 + u_sal_pct ** 2), 2)
        u_kaynak = (u_kaynak + " ⊕ salınım-genliği") if u_kaynak else "salınım-genliği"
    wall_resolved = n_layers > 0 and (yp is None or yp.get("ort", 99) < 5)
    mu = model_uncertainty_pct(regime_of(vehicle_type, preset), wall_resolved)
    u_total = combine_uncertainty(u_num_pct, mu["u_model_pct"])
    base.belirsizlik = {
        "u_sayisal_pct": u_num_pct, "u_sayisal_kaynak": u_kaynak,
        "u_model_pct": mu["u_model_pct"], "model_kaynak": mu["kaynak"],
        "u_toplam_pct": u_total, "duvar_cozunur": wall_resolved,
        "rapor": (f"Cd = {cd:.4f} ± {u_total:.1f}% "
                  f"(sayısal {u_num_pct if u_num_pct is not None else '—'}% ⊕ model {mu['u_model_pct']}%)"
                  if u_total is not None else "belirsizlik hesaplanamadı"),
    }

    (run_dir / "sonuc.json").write_text(json.dumps(asdict(base), indent=2, ensure_ascii=False), encoding="utf-8")

    from vehicle_report import build_vehicle_report
    report_path = build_vehicle_report(base, history, residuals, run_dir / "rapor")
    base.report = str(report_path)
    (run_dir / "sonuc.json").write_text(json.dumps(asdict(base), indent=2, ensure_ascii=False), encoding="utf-8")
    return base


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Katı model → CFD → mühendis raporu")
    ap.add_argument("model", help="STL/OBJ/STEP/IGES dosyası")
    ap.add_argument("--tip", default="ucak", choices=list(VEHICLE_PRESETS))
    ap.add_argument("--hiz", type=float, default=30.0, help="m/s")
    ap.add_argument("--aoa", type=float, default=0.0, help="hücum açısı (derece)")
    ap.add_argument("--kalite", default="standart", choices=list(MESH_QUALITY))
    ap.add_argument("--islemci", type=int, default=0, help="0 = otomatik")
    ap.add_argument("--burun", default="+x", choices=list(AXIS_VECTORS),
                    help="modelin burun/akış ekseni")
    ap.add_argument("--ust", default="+z", choices=list(AXIS_VECTORS),
                    help="modelin üst ekseni")
    ap.add_argument("--duyarlilik", action="store_true",
                    help="ikinci (kaba) koşuyla mesh duyarlılık bandı hesapla")
    ap.add_argument("--seviyeler", type=int, default=3, choices=(3, 4),
                    help="duyarlılık seviye sayısı (4 = LSR bandı, non-asimptotikte de U verir)")
    ap.add_argument("--katman", type=int, default=0,
                    help="prizma sınır-tabaka katman sayısı (0=kapalı)")
    ap.add_argument("--yplus", type=float, default=30.0,
                    help="hedef y+ (ilk katman kalınlığı buna göre hesaplanır)")
    ap.add_argument("--itki", type=float, default=0.0,
                    help="pervane itkisi (N) — aktüatör disk modeli")
    ap.add_argument("--cap", type=float, default=0.0,
                    help="pervane çapı (m)")
    args = ap.parse_args()

    def _cb(pct, msg):
        print(f"[{pct:3d}%] {msg}", flush=True)

    r = run_vehicle_analysis(args.model, args.tip, args.hiz, args.aoa,
                             args.kalite, n_processors=args.islemci,
                             nose_axis=args.burun, up_axis=args.ust,
                             mesh_sensitivity=args.duyarlilik, n_layers=args.katman,
                             mesh_levels=args.seviyeler, yplus_target=args.yplus,
                             pervane_itki_n=args.itki, pervane_cap_m=args.cap,
                             progress_cb=_cb)
    if r.status == "ok":
        print(f"\nCd={r.cd}  CdA={r.cda_m2} m²  Drag={r.drag_N} N"
              + (f"  Cl={r.cl}  L/D={r.ld}" if r.cl is not None else ""))
        print(f"Rapor: {r.report}")
    else:
        print(f"\nBASARISIZ — {r.case_dir}\n{r.error[-500:]}")
