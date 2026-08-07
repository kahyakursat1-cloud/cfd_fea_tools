"""
Otomatik Mesh Generator
Aircraft/Rocket geometrisi → Gmsh mesh
Boundary layer, refinement kontrol
"""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

from aircraft_geometry import Aircraft


def generate_stl_openvsp(aircraft: Aircraft, output_path: str,
                          tess_w: int = 24, tess_u: int = 12) -> str:
    """OpenVSP Python API ile yüksek kaliteli watertight STL üret.

    Trimesh tabanlı generate_stl()'den üstünlüğü:
    - Kanat-gövde kavşağı düzgün birleşir
    - NACA profil geometrik olarak doğru
    - snappyHexMesh daha tutarlı Cd üretir

    Gereksinim: conda openvsp ortamı (Python 3.13)
    tess_w: chord yönü tessellation (artırınca daha pürüzsüz)
    tess_u: gövde çevre tessellation
    """
    # OpenVSP ortamındaki Python ile bridge script'i çalıştır
    bridge_script = Path(__file__).parent / "openvsp_bridge.py"
    # Mutlak yollar GÖMÜLÜ DEĞİL (Docker'da tamamı kırılır) — bkz. dis_araclar.
    from dis_araclar import bul
    _py, _dll = bul("openvsp_python"), bul("openvsp_dll")
    vsp_python = _py["yol"]
    vsp_dll_dir = _dll["yol"] or ""
    if not vsp_python:
        print(f"[OpenVSP] {_py['neden']}\n          arandi: {_py['aranan']}")
        return None

    # Parametreleri JSON ile geç
    import json
    import tempfile
    params = {
        "aircraft_name": aircraft.name,
        "aircraft_type": aircraft.aircraft_type,
        "wing": {
            "span": aircraft.wing.span,
            "root_chord": aircraft.wing.root_chord(),
            "tip_chord": aircraft.wing.tip_chord(),
            "sweep": aircraft.wing.sweep_angle,
            "dihedral": aircraft.wing.dihedral,
            "naca": aircraft.wing.airfoil.name,
        },
        "fuselage": {
            "length": aircraft.fuselage.length,
            "diameter": aircraft.fuselage.diameter,
        },
        "output": output_path,
        "tess_w": tess_w,
        "tess_u": tess_u,
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                      delete=False) as f:
        json.dump(params, f)
        param_file = f.name

    # Inline script — OpenVSP ortamında çalışır
    script = f"""
import os, sys, json
# add_dll_directory YALNIZ Windows'ta var; Linux imajinda kutuphane rpath/LD_LIBRARY_PATH
# ile bulunur. Kosulsuz cagri konteynerde AttributeError veriyordu.
if hasattr(os, 'add_dll_directory') and r'{vsp_dll_dir}':
    os.add_dll_directory(r'{vsp_dll_dir}')
import openvsp as vsp

p = json.load(open(r'{param_file}'))
vsp.VSPCheckSetup()
vsp.ClearVSPModel()

# Wing
wid = vsp.AddGeom("WING")
vsp.SetGeomName(wid, "Wing")
vsp.SetParmValUpdate(vsp.FindParm(wid,"X_Rel_Location","XForm"),
                     p['fuselage']['length']*0.35)
xsurf = vsp.GetXSecSurf(wid, 0)
xs1 = vsp.GetXSec(xsurf, 1)
vsp.SetParmValUpdate(vsp.GetXSecParm(xs1,"Span"),       p['wing']['span']/2)
vsp.SetParmValUpdate(vsp.GetXSecParm(xs1,"Root_Chord"), p['wing']['root_chord'])
vsp.SetParmValUpdate(vsp.GetXSecParm(xs1,"Tip_Chord"),  p['wing']['tip_chord'])
vsp.SetParmValUpdate(vsp.GetXSecParm(xs1,"Sweep"),      p['wing']['sweep'])
vsp.SetParmValUpdate(vsp.GetXSecParm(xs1,"Dihedral"),   p['wing']['dihedral'])
vsp.SetParmValUpdate(vsp.FindParm(wid,"Sym_Planar_Flag","Sym"), vsp.SYM_XZ)

# NACA profil
naca = p['wing']['naca'].replace('NACA','').strip()
if len(naca)==4 and naca.isdigit():
    t = int(naca[2:])/100
    m = int(naca[0])/100
    c = int(naca[1])/10
    for xs_i in [0,1]:
        xs = vsp.GetXSec(vsp.GetXSecSurf(wid,0), xs_i)
        vsp.SetParmValUpdate(vsp.GetXSecParm(xs,"ThickChord"), t)
        if m > 0:
            vsp.SetParmValUpdate(vsp.GetXSecParm(xs,"Camber"),    m)
            vsp.SetParmValUpdate(vsp.GetXSecParm(xs,"CamberLoc"), c)

# Fuselage (POD)
fid = vsp.AddGeom("POD")
vsp.SetGeomName(fid, "Fuselage")
vsp.SetParmValUpdate(vsp.FindParm(fid,"Length","Design"),    p['fuselage']['length'])
vsp.SetParmValUpdate(vsp.FindParm(fid,"FineRatio","Design"), p['fuselage']['length']/p['fuselage']['diameter'])

# Tessellation kalitesi
for gid in vsp.FindGeoms():
    try:
        vsp.SetParmValUpdate(vsp.FindParm(gid,"Tess_W","Shape"), p['tess_w'])
        vsp.SetParmValUpdate(vsp.FindParm(gid,"Tess_U","Shape"), p['tess_u'])
    except Exception: pass  # opsiyonel tessellation — geom desteklemiyorsa atla

vsp.Update()
vsp.ExportFile(p['output'], vsp.SET_ALL, vsp.EXPORT_STL)
print("VSP_STL_OK:" + p['output'])
"""

    result = subprocess.run(
        [vsp_python, "-c", script],
        capture_output=True, text=True, timeout=60
    )

    os.unlink(param_file)

    if "VSP_STL_OK:" in result.stdout:
        print(f"[OpenVSP] STL uretildi: {output_path}")
        return output_path
    else:
        # OpenVSP mevcut değilse trimesh fallback
        print("[OpenVSP] Kullanilamiyor, trimesh fallback kullaniliyor")
        print(f"  Hata: {result.stderr[:200] if result.stderr else 'unknown'}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# MESH GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def _dokuntu_temizle(m, alan_esigi: float = 1e-6):
    """Ayrık DÖKÜNTÜ parçalarını at (dejenere/sıfır-alanlı üçgenler).

    Ölçüldü (MiniHawk, 2026-07-27): üretilen STL 99 ayrık gövdeden oluşuyordu —
    gövde, kanat ve **96 adet tek-üçgenlik döküntü**. Toplam yüzey alanına katkıları
    %0.0000 (sıfır-alanlı), ama STL'i su-geçirmez olmaktan çıkarıp snappyHexMesh'in
    onlara yapışmasına yol açıyorlardı; pipeline her koşuda "STL su geçirmez değil"
    uyarısı veriyordu ve sebebi bilinmiyordu.

    Eşik ORANSAL: toplam alanın `alan_esigi` katından küçük parça atılır — mutlak
    boyut varsayımı yapmaz (0.1 m'lik İHA ile 30 m'lik kanat aynı kuralla temizlenir).
    """
    import trimesh
    try:
        parcalar = m.split(only_watertight=False)
    except Exception:
        return m
    if len(parcalar) <= 1:
        return m
    toplam = float(m.area) or 1.0
    saglam = [p for p in parcalar if float(p.area) / toplam > alan_esigi]
    if not saglam or len(saglam) == len(parcalar):
        return m
    return trimesh.util.concatenate(saglam) if len(saglam) > 1 else saglam[0]


class MeshGenerator:
    """OpenFOAM uyumlu mesh oluştur"""

    def __init__(self, aircraft: Aircraft, mesh_size: float = 0.01,
                 wind_speed: float = 15.0, target_yplus: float = 1.0):
        """
        aircraft: Aircraft nesnesi
        mesh_size: Temel mesh boyutu (m)
        wind_speed: serbest akim hizi (m/s) — y+ hesabi icin
        target_yplus: hedef y+ (1.0 = low-Re cozunmus BL, 30-50 = wall function)
        """
        self.aircraft = aircraft
        # Geometri üretiminde sessizce düşülen geri-adımlar burada birikir; çağıran
        # (ve testler) bunu okuyabilmeli — "üretildi" ile "istenildiği gibi üretildi"
        # ayni sey degil.
        self.gerilemeler: list[str] = []
        self.base_mesh_size = mesh_size
        self.wind_speed = wind_speed
        self.target_yplus = target_yplus
        self.refinement_regions = []
        # snappyHexMeshDict'teki maxGlobalCells ile AYNI sayı olmalı; arka plan
        # çözünürlüğü de bu bütçeden türetiliyor (bkz. blockMesh üretimi).
        # Ayrışırsa ya bütçe boş kalır ya tavan aşılır.
        self.max_global_cells = 5_000_000

    def first_layer_thickness(self, nu: float = 1.5e-5, rho: float = 1.225) -> float:
        """Hedef y+ icin prizmatik ilk katman yuksekligi (m).
        Flat-plate korelasyonu: Cf = 0.058*Re^-0.2, tau_w = 0.5*rho*U^2*Cf,
        u_tau = sqrt(tau_w/rho), y = y+ * nu / u_tau.
        """
        import math
        try:
            L_ref = self.aircraft.wing.root_chord()
        except Exception:
            L_ref = 0.25
        U = self.wind_speed
        Re = U * L_ref / nu
        Cf = 0.058 * Re ** (-0.2)
        tau_w = 0.5 * rho * U ** 2 * Cf
        u_tau = math.sqrt(tau_w / rho)
        return self.target_yplus * nu / u_tau

    def add_refinement_region(self, region_name: str, location: tuple[float, float, float],
                             radius: float, factor: float) -> None:
        """Mesh iyileştirme bölgesi ekle"""
        self.refinement_regions.append({
            "name": region_name,
            "center": location,
            "radius": radius,
            "size_factor": factor  # 1.0 = base, 0.5 = iki kat inceltilmiş
        })

    @staticmethod
    def _naca4_profile(m: float, p: float, t: float, n: int = 64) -> np.ndarray:
        """NACA 4-digit airfoil — kapalı profil koordinatları döndürür.
        m: max camber (0-1), p: camber position (0-1), t: thickness (0-1)
        Döndürür: (2n, 2) array — üst yüzey CW + alt yüzey CCW, burun önde
        """
        # Yarı-kosinüs dağılımı → burun bölgesi yoğun
        beta = np.linspace(0, np.pi, n)
        x = 0.5 * (1 - np.cos(beta))

        # NACA 4 kalınlık dağılımı (açık TE için son katsayı -0.1015)
        yt = (t / 0.2) * (0.2969 * np.sqrt(x) - 0.1260 * x
                          - 0.3516 * x**2 + 0.2843 * x**3 - 0.1015 * x**4)

        # Eğrilik çizgisi ve türevi
        if m > 0 and p > 0:
            yc  = np.where(x < p,
                           m / p**2 * (2*p*x - x**2),
                           m / (1-p)**2 * (1 - 2*p + 2*p*x - x**2))
            dyc = np.where(x < p,
                           2*m / p**2 * (p - x),
                           2*m / (1-p)**2 * (p - x))
        else:
            yc  = np.zeros(n)
            dyc = np.zeros(n)

        theta = np.arctan(dyc)
        xu = x - yt * np.sin(theta)
        yu = yc + yt * np.cos(theta)
        xl = x + yt * np.sin(theta)
        yl = yc - yt * np.cos(theta)

        # Kapalı profil: üst (LE→TE) + alt (TE→LE)
        px = np.concatenate([xu, xl[::-1]])
        py = np.concatenate([yu, yl[::-1]])
        return np.column_stack([px, py])

    # STATICMETHOD DEGIL: kapak orme duserse gerileme KAYDEDILMELI ve o kanal
    # ornek uzerinde (self.gerilemeler). Iki cagiran da zaten `self.` uzerinden
    # cagiriyordu, yani cagri yerleri degismedi.
    def _extrude_profile_to_mesh(self, profile_2d: np.ndarray,
                                  y_root: float, y_tip: float,
                                  chord_root: float, chord_tip: float,
                                  le_x_root: float, le_x_tip: float) -> "trimesh.Trimesh":  # noqa: F821 — trimesh fonksiyon govdesinde lazy import
        """2D NACA profili → watertight kanat solid.
        trimesh.creation.extrude_polygon ile Shapely üzerinden garantili watertight.
        Taper için kök ve uç ayrı extrude edilip blend yapılır.
        """
        import trimesh
        from shapely.geometry import Polygon

        def make_section_poly(chord: float, le_x: float) -> Polygon:
            xs = le_x + profile_2d[:, 0] * chord
            zs = profile_2d[:, 1] * chord
            return Polygon(zip(xs, zs))

        root_poly = make_section_poly(chord_root, le_x_root)
        tip_poly  = make_section_poly(chord_tip,  le_x_tip)

        span = abs(y_tip - y_root)

        # Kök ve uç extrusion'ı blend ederek trapez kanat oluştur
        # Her iki poly aynı sayıda vertex içermeli → interpolasyon
        # n GİRDİ profilinden değil POLİGONDAN türetilir: Shapely, hücum kenarında
        # çakışan ilk/son noktayı birleştiriyor (48 panelde 96 yerine 95 köşe) ve
        # sabit n ile column_stack ValueError atıyordu. Hata `except Exception` ile
        # yutulup kanat sessizce DÜZ KUTUYA düşüyordu.
        root_xz = np.array(list(root_poly.exterior.coords)[:-1])
        tip_xz  = np.array(list(tip_poly.exterior.coords)[:-1])
        if len(root_xz) != len(tip_xz):
            raise ValueError(f"kök/uç kesit köşe sayısı farklı: {len(root_xz)} vs {len(tip_xz)}")
        n = len(root_xz)

        # 3D vertices
        root_v = np.column_stack([root_xz[:, 0], np.full(n, y_root), root_xz[:, 1]])
        tip_v  = np.column_stack([tip_xz[:, 0],  np.full(n, y_tip),  tip_xz[:, 1]])
        all_v  = np.vstack([root_v, tip_v])

        faces = []
        # Yan yüzler — outward normal garantisi için winding kontrol
        for i in range(n):
            j = (i + 1) % n
            r0, r1, t0, t1 = i, j, i+n, j+n
            # Normal direction: cross product of edge vectors
            e1 = all_v[r1] - all_v[r0]
            e2 = all_v[t0] - all_v[r0]
            norm = np.cross(e1, e2)
            # For external surface, normal should point outward (away from profile interior)
            # Profile centroid
            cx = (root_v[:, 0].mean() + tip_v[:, 0].mean()) / 2
            cz = (root_v[:, 2].mean() + tip_v[:, 2].mean()) / 2
            cy = (y_root + y_tip) / 2
            centroid = np.array([cx, cy, cz])
            mid = (all_v[r0] + all_v[t0]) / 2
            if np.dot(norm, mid - centroid) > 0:
                faces += [[r0, r1, t0], [r1, t1, t0]]
            else:
                faces += [[r0, t0, r1], [r1, t0, t1]]

        # Uç kapaklar: Shapely polygon → earclip triangulation
        for poly, offset, flip in [(root_poly, 0, True), (tip_poly, n, False)]:
            try:
                from trimesh.creation import triangulate_polygon
                cap_verts_2d, cap_faces = triangulate_polygon(poly)
                # Map 2D → 3D index
                y_val = y_root if offset == 0 else y_tip
                # cap_verts_2d koordinatları root_xz/tip_xz ile eşleştir
                xz_section = root_xz if offset == 0 else tip_xz
                # Doğrudan face mapping yerine fan triangulation kullan
                centroid_3d = all_v[offset:offset+n].mean(axis=0)
                cid = len(all_v) + (0 if offset == 0 else 1)
                for i in range(n):
                    j = (i + 1) % n
                    a, b = i + offset, j + offset
                    v0, v1 = all_v[a], all_v[b]
                    c3d = centroid_3d
                    cross = np.cross(v1 - v0, c3d - v0)
                    # Root cap: normal in -y, Tip cap: normal in +y
                    if (offset == 0 and cross[1] < 0) or (offset == n and cross[1] > 0):
                        faces.append([a, b, cid])
                    else:
                        faces.append([b, a, cid])
            except Exception as _ce:
                # KAPAK ORULMEDI → kanat ucu/kok ACIK kalir ve STL su-gecirmez
                # olmaz. Yuzey uretimi devam eder (govde hala kullanilabilir)
                # ama sessiz kalirsa su-gecirmezlik kapisi neyin bozuldugunu
                # soyleyemez: "watertight degil" der, NEDENINI demez.
                self.gerilemeler.append(
                    f"UÇ KAPAĞI ÖRÜLEMEDİ ({'kök' if offset == 0 else 'uç'}, "
                    f"{type(_ce).__name__}: {_ce}) → yüzey AÇIK kaldı; STL "
                    "su-geçirmez olmayacak.")
                print(f"[UYARI] {self.gerilemeler[-1]}")

        root_c = root_v.mean(axis=0)
        tip_c  = tip_v.mean(axis=0)
        all_verts_final = np.vstack([all_v, root_c.reshape(1,3), tip_c.reshape(1,3)])

        mesh = trimesh.Trimesh(vertices=all_verts_final,
                               faces=np.array(faces, dtype=np.int64),
                               process=True)
        trimesh.repair.fix_normals(mesh)
        return mesh

    def generate_stl(self, output_path: str) -> str:
        """Aircraft geometrisinden watertight STL üret.
        Kanat: gerçek NACA 4-digit profil (yarı-kosinüs dağılımlı, 64 nokta).
        Gövde: ogive burun + silindir gövde.
        """
        import trimesh
        import trimesh.creation as tc

        L = self.aircraft.fuselage.length
        D = self.aircraft.fuselage.diameter
        r = D / 2

        parts = []

        # ── Gövde: silindir (X ekseni boyunca — akış yönü) ───────────────
        body_len = L * 0.70
        body = tc.cylinder(radius=r, height=body_len, sections=64)
        # trimesh cylinder varsayilan olarak Z boyunca → X'e dondur
        body.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
        )
        body.apply_translation([L * 0.15 + body_len / 2, 0, 0])
        parts.append(body)

        # ── Burun: ogive (silindir ile pürüzsüz birleşim) ─────────────────
        nose_len = L * 0.30
        # Von Kármán ogive profili (rotationally symmetric)
        n_nose = 32
        t_nose = np.linspace(0, 1, n_nose)
        x_nose = nose_len * t_nose
        # Ogive radius profile
        rho  = (r**2 + nose_len**2) / (2 * r)
        r_nose = np.sqrt(rho**2 - (nose_len - x_nose)**2) - (rho - r)
        r_nose = np.clip(r_nose, 0, r)

        # Dönel yüzey olarak ogive oluştur
        theta = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        nose_verts = []
        nose_faces = []
        for i, (xn, rn) in enumerate(zip(x_nose, r_nose)):
            ring = np.column_stack([
                np.full(len(theta), xn),
                rn * np.cos(theta),
                rn * np.sin(theta)
            ])
            nose_verts.append(ring)

        nose_verts = np.vstack(nose_verts)
        n_rings = n_nose
        n_circ  = len(theta)
        for i in range(n_rings - 1):
            for j in range(n_circ):
                jn = (j + 1) % n_circ
                a = i * n_circ + j
                b = i * n_circ + jn
                c = (i+1) * n_circ + j
                d = (i+1) * n_circ + jn
                nose_faces += [[a, b, c], [b, d, c]]

        # Burun kapağı (tip → nokta)
        tip_id = len(nose_verts)
        nose_verts = np.vstack([nose_verts, [[0, 0, 0]]])
        for j in range(n_circ):
            jn = (j + 1) % n_circ
            nose_faces.append([jn, j, tip_id])

        nose_mesh = trimesh.Trimesh(vertices=nose_verts, faces=nose_faces, process=True)
        parts.append(nose_mesh)

        # ── Kanat: gerçek NACA profil ─────────────────────────────────────
        try:
            af = self.aircraft.wing.airfoil
            m = af.camber / 100
            # NACA 4-digit: p = max camber position
            # NACA2412 → m=0.02, p=0.4, t=0.12
            p = 0.4 if m > 0 else 0.0
            t = af.thickness_ratio / 100

            profile = self._naca4_profile(m, p, t, n=48)

            chord_r = self.aircraft.wing.root_chord()
            chord_t = self.aircraft.wing.tip_chord()
            span    = self.aircraft.wing.span
            sweep   = np.tan(np.radians(self.aircraft.wing.sweep_angle))

            le_x_root = L * 0.35
            le_x_tip  = le_x_root + (span / 2) * sweep

            # Sağ yarım kanat (y > 0)
            wing_r = self._extrude_profile_to_mesh(
                profile, 0.0, span / 2, chord_r, chord_t, le_x_root, le_x_tip)
            # Sol yarım kanat (y < 0, ayna)
            wing_l = wing_r.copy()
            wing_l.vertices[:, 1] *= -1
            wing_l.invert()
            parts += [wing_r, wing_l]
        except Exception as _e:
            # SESSİZ DEĞİL: bu geri-düşüş kanadı NACA profilinden DÜZ KUTUYA çevirir ve
            # tüm aerodinamik sonucu geçersizler. `shapely` kurulu olmadığı için yıllarca
            # sessizce tetiklenmiş; ihraç edilen MiniHawk'ın kanadı 12 üçgenlik bir
            # kutuydu ve bunu hiçbir yer söylemiyordu.
            self.gerilemeler.append(
                f"KANAT PROFİLİ ÜRETİLEMEDİ → DÜZ KUTUYA düşüldü ({type(_e).__name__}: "
                f"{_e}). Aerodinamik sonuç NACA profilini TEMSİL ETMEZ; eksik bağımlılık "
                "için `python pipeline.py doctor` çalıştırın (shapely, mapbox_earcut).")
            print(f"[UYARI] {self.gerilemeler[-1]}")
            chord = self.aircraft.wing.root_chord()
            span  = self.aircraft.wing.span
            wb = tc.box([chord, span, chord * 0.10])
            wb.apply_translation([L * 0.35 + chord / 2, 0, 0])
            parts.append(wb)

        # ── Yatay kuyruk (NACA 0009) ──────────────────────────────────────
        try:
            emp = self.aircraft.empennage
            hc  = emp.horizontal_airfoil.chord
            hs  = emp.h_area / hc if hc > 0 else 0.15
            ht  = emp.horizontal_airfoil.thickness_ratio / 100
            h_profile = self._naca4_profile(0, 0, ht, n=32)
            stab_r = self._extrude_profile_to_mesh(h_profile, 0, hs/2, hc, hc*0.6, L*0.88, L*0.88)
            stab_l = stab_r.copy(); stab_l.vertices[:, 1] *= -1; stab_l.invert()
            parts += [stab_r, stab_l]
        except Exception as _e:
            # KANAT KUSURUNUN TIPATIP ESI (yukariya bak). Yatay kuyruk hic
            # eklenmezse ucak KUYRUKSUZ analiz edilir: boyuna kararlilik yok,
            # Cm anlamsiz, Cl eksik. Kanat yolunda gerileme kaydediliyor, burada
            # sessizce geciliyordu — ayni sinif, ayni kanal.
            self.gerilemeler.append(
                f"YATAY KUYRUK ÜRETİLEMEDİ → gövde KUYRUKSUZ ihraç edildi "
                f"({type(_e).__name__}: {_e}). Boyuna kararlılık ve Cm bu "
                "geometriden ÇIKARILAMAZ.")
            print(f"[UYARI] {self.gerilemeler[-1]}")

        # Boolean union → watertight STL (manifold3d gerekli)
        combined = trimesh.util.concatenate(parts)
        try:
            import manifold3d
            # Her parçayı watertight yap
            clean_parts = []
            for p in parts:
                trimesh.repair.fix_normals(p)
                trimesh.repair.fill_holes(p)
                if p.is_watertight:
                    clean_parts.append(p)
            if len(clean_parts) >= 2:
                result = clean_parts[0]
                for p in clean_parts[1:]:
                    try:
                        result = trimesh.boolean.union([result, p], engine="manifold")
                    except Exception as _be:
                        # SESSİZ DEĞİL: birleşim düşerse parçalar AYRI cisim kalır ve
                        # STL su-geçirmez olmaz; snappyHexMesh iç yüzey/kaçak görür.
                        # manifold3d kurulu olmadığı için yıllarca sessizce tetiklenmiş.
                        self.gerilemeler.append(
                            f"KATI BİRLEŞİM DÜŞTÜ → parçalar ayrı cisim kaldı "
                            f"({type(_be).__name__}: {_be}). STL su-geçirmez olmayacak; "
                            "`python pipeline.py doctor` (manifold3d) çalıştırın.")
                        result = trimesh.util.concatenate([result, p])
                combined = result
        except ImportError:
            # BIRLESIM HIC DENENMEDI. Ici bosaltilmis union hatasi zaten gerileme
            # kaydediyordu ama manifold3d KURULU DEGILSE oraya hic girilmiyordu:
            # en yaygin hal en sessiz olandi. STL su-gecirmez cikmaz, snappy ic
            # yuzey/kacak gorur ve y+ ile katman hukmu bozulur.
            self.gerilemeler.append(
                "KATI BİRLEŞİM ATLANDI → manifold3d kurulu değil; parçalar AYRI "
                "cisim kaldı ve STL su-geçirmez olmayacak. `python pipeline.py "
                "doctor` çalıştırın.")
            print(f"[UYARI] {self.gerilemeler[-1]}")

        # Son temizlik
        trimesh.repair.fix_normals(combined)
        combined = _dokuntu_temizle(combined)
        combined.export(str(output_path))
        return str(output_path)

    def generate_blockmeshdict(self) -> str:
        """Doğru aerodinamik domain boyutlarıyla blockMeshDict.
        Upstream 10L, downstream 20L, lateral 5L (aerodinamik standart).
        """
        L    = self.aircraft.fuselage.length
        span = getattr(getattr(self.aircraft, 'wing', None), 'span', L) or L
        ref  = max(L, span)

        x_min = -10 * ref
        x_max =  20 * ref
        y_ext =   5 * ref
        z_ext =   5 * ref

        # ARKA PLAN ÇÖZÜNÜRLÜĞÜ BÜTÇEDEN TÜRETİLİR, sabit tavandan değil.
        #
        # Eski kurulum `nx = min(base_cells, 150)`, `ny = nz = nx/2 ≤ 75` diyordu.
        # ÖLÇÜLDÜ (2026-08-02, kütüphanedeki BEŞ şablonun BEŞİNDE de): en ince
        # ayarda bile arka plan yalnız 453.962 hücre — 5.000.000 tavanın %9'u.
        # Domain 30L×10L×10L olduğu için arka plan hücresi 369-984 mm kalıyor ve
        # 5 iyileştirme kademesinden sonra yüzey hücresi 11.5-30.7 mm oluyor.
        # Sonuç: firar kenarı 0.05-0.65 HÜCRE — hiçbir şablonda 1'e bile ulaşmıyor.
        # Yani bütçe yetersiz değildi, KULLANILMIYORDU.
        #
        # Kanonik katmanın çözümü `arka_plan_hucre_boyu`: kutu hacmini ve hücre
        # bütçesini birlikte kullanıp küpe yakın bir taban hücre seçer.
        # ASLA ESKİSİNDEN KABA OLMAZ: eski çözünürlük taban kabul edilir, yani bu
        # değişiklik hiçbir koşuyu kötüleştiremez.
        scale = max(0.01, min(0.05, self.base_mesh_size))
        base_cells = int(60 * (0.05 / scale) ** 0.5)   # ~60 @ coarse, ~85 @ medium, ~120 @ fine
        nx_eski = min(base_cells, 150)
        ny_eski = min(int(nx_eski * 0.5), 75)
        try:
            import numpy as _np

            from analysis.openfoam_runner import arka_plan_hucre_boyu
            _dmin = _np.array([x_min, -y_ext, -z_ext], dtype=float)
            _dmax = _np.array([x_max, y_ext, z_ext], dtype=float)
            # İSTENEN HÜCRE GEOMETRİDEN TÜRETİLİR, eski çözünürlükten DEĞİL.
            # `arka_plan_hucre_boyu` yalnız KABALAŞTIRIR (bütçeye sığdırmak için);
            # ona eski hücreyi verirsek çıktı da eski hücredir — ilk denemede tam
            # bu oldu ve düzeltme beş şablonda da SIFIR kazanç verdi.
            # Kanonik katmanın ölçeği: gövde boyu / bg_div (5 kaba … 9 hassas).
            _bg_div = 5.0 if self.base_mesh_size >= 0.04 else (
                7.0 if self.base_mesh_size >= 0.02 else 9.0)
            _bg, _ = arka_plan_hucre_boyu(_dmin, _dmax, ref / _bg_div,
                                          self.max_global_cells)
            nx = max(nx_eski, int((x_max - x_min) / _bg))
            ny = max(ny_eski, int(2 * y_ext / _bg))
            nz = max(ny_eski, int(2 * z_ext / _bg))
        # sessiz-yutma: kabul — bütçe-farkındalığı bir İYİLEŞTİRMEdir; düşerse
        # eski (daha kaba ama çalışan) çözünürlüğe dönülür, koşu engellenmez
        except Exception:
            nx, ny, nz = nx_eski, ny_eski, ny_eski

        return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}}

convertToMeters 1;

vertices
(
    ({x_min:.4f} {-y_ext:.4f} {-z_ext:.4f})   // 0
    ({x_max:.4f} {-y_ext:.4f} {-z_ext:.4f})   // 1
    ({x_max:.4f}  {y_ext:.4f} {-z_ext:.4f})   // 2
    ({x_min:.4f}  {y_ext:.4f} {-z_ext:.4f})   // 3
    ({x_min:.4f} {-y_ext:.4f}  {z_ext:.4f})   // 4
    ({x_max:.4f} {-y_ext:.4f}  {z_ext:.4f})   // 5
    ({x_max:.4f}  {y_ext:.4f}  {z_ext:.4f})   // 6
    ({x_min:.4f}  {y_ext:.4f}  {z_ext:.4f})   // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

boundary
(
    inlet
    {{
        type patch;
        faces ( (0 4 7 3) );
    }}
    outlet
    {{
        type patch;
        faces ( (1 2 6 5) );
    }}
    sides
    {{
        type symmetry;
        faces
        (
            (0 1 5 4)
            (3 7 6 2)
            (0 3 2 1)
            (4 5 6 7)
        );
    }}
);
"""

    def generate_snappyhexmeshdict(self, stl_name: str = "aircraft.stl") -> str:
        """STL geometrisini referans alan snappyHexMeshDict.
        Refinement seviyeleri mesh_size'a göre otomatik ayarlanır:
        coarse(0.05): (2,3)  medium(0.025): (3,4)  fine(0.012): (4,5)
        """
        # Refinement level: mesh boyutu küçüldükçe artar
        # n_layers: y+ cozunumu icin prizmatik katman sayisi (endustri: 10-20)
        if self.base_mesh_size >= 0.04:
            ref_min, ref_max, n_layers = 2, 3, 7
        elif self.base_mesh_size >= 0.02:
            ref_min, ref_max, n_layers = 3, 4, 8
        else:
            ref_min, ref_max, n_layers = 4, 5, 10

        # y+ hedefli mutlak ilk katman yuksekligi
        first_layer = self.first_layer_thickness()
        expansion   = 1.2

        # Kanat bölgesi refinement box koordinatları
        try:
            le_x      = self.aircraft.fuselage.length * 0.30
            te_x      = self.aircraft.fuselage.length * 0.70
            span_half = self.aircraft.wing.span * 0.55
            wing_thick = self.aircraft.wing.root_chord() * 0.18
        except Exception:
            le_x, te_x, span_half, wing_thick = 0.24, 0.65, 0.70, 0.05

        # Bütçe TEK KAYNAK: arka plan çözünürlüğü de bu sayıdan türetiliyor
        # (blockMesh üretimi). Sabit yazılırsa ikisi ayrışır ve ya bütçe boş
        # kalır ya tavan aşılır.
        maks_global = int(self.max_global_cells)
        maks_yerel = max(100_000, maks_global // 5)

        return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      snappyHexMeshDict;
}}

castellatedMesh true;
snap            true;
addLayers       true;

geometry
{{
    {stl_name}
    {{
        type triSurfaceMesh;
        name aircraft;
    }}
    wing_le_box
    {{
        type searchableBox;
        min ({le_x:.4f} {-span_half:.4f} {-wing_thick:.4f});
        max ({te_x:.4f}  {span_half:.4f}  {wing_thick:.4f});
    }}
}}

castellatedMeshControls
{{
    maxLocalCells       {maks_yerel};
    maxGlobalCells      {maks_global};   // self.max_global_cells ile TEK KAYNAK
    minRefinementCells  10;
    nCellsBetweenLevels 3;
    resolveFeatureAngle 30;
    locationInMesh      (-5.0 0.0 2.0);  // Ucaktan uzak, fluid bolgesinde
    allowFreeStandingZoneFaces true;

    features
    (
        {{ file "aircraft.eMesh"; level {ref_min}; }}
    );

    refinementSurfaces
    {{
        aircraft
        {{
            level ({ref_min} {ref_max});
            patchInfo {{ type wall; }}
        }}
    }}

    refinementRegions
    {{
        aircraft
        {{
            mode inside;
            levels ((1e15 {ref_max}));
        }}
        wing_le_box
        {{
            mode inside;
            levels ((1e15 {ref_max + 1}));
        }}
    }}
}}

snapControls
{{
    nSmoothPatch        3;
    tolerance           4.0;
    nSolveIter          300;
    nRelaxIter          5;
    nFeatureSnapIter    10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}}

addLayersControls
{{
    // Goreceli boyutlandirma: snappy'nin robust ekledigi yontem.
    // final=0.3*cell, exp=1.2, n={n_layers} -> ilk katman ~cell*0.3/1.2^(n-1)
    // level-5 cell ~375um icin ilk katman ~30um => y+~1.4 (hedef: {first_layer*1e6:.0f}um)
    relativeSizes true;
    layers
    {{
        "aircraft.*"
        {{
            nSurfaceLayers {n_layers};
        }}
    }}
    expansionRatio        {expansion};
    finalLayerThickness   0.35;
    minThickness          0.02;
    nGrow                 0;
    // featureAngle yuksek: egri yuzeylerde (kanat LE/TE) layer eklenmesine izin ver
    featureAngle          130;
    slipFeatureAngle      30;
    nRelaxIter            5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals        3;
    nSmoothThickness      10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.6;
    minMedianAxisAngle    90;
    nBufferCellsNoExtrude 0;
    nLayerIter            50;
    nRelaxedIter          20;
    nMedialAxisIter       10;
}}

meshQualityControls
{{
    maxNonOrtho         70;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave          80;
    minFlatness         0.5;
    minVol              1e-13;
    minTetQuality       -1e30;
    minArea             -1;
    minTwist            0.02;
    minDeterminant      0.001;
    minFaceWeight       0.02;
    minVolRatio         0.01;
    minTriangleTwist    -1;
    nSmoothScale        4;
    errorReduction      0.75;
    // Layer eklerken kaliteyi gevsetme (aksi halde layer collapse olur)
    relaxed
    {{
        maxNonOrtho     75;
        maxBoundarySkewness 25;
        maxInternalSkewness 8;
        minVol          1e-14;
        minTetQuality   -1e30;
        minTwist        0.001;
        minDeterminant  0.0001;
        minFaceWeight   0.005;
        minVolRatio     0.001;
    }}
}}

writeFlags ( scalarLevels layerSets layerFields );
mergeTolerance 1e-6;
"""

    def generate_gmsh_script(self) -> str:
        """Gmsh .geo dosyası — FEA tetrahedral mesh için."""
        L = self.aircraft.fuselage.length
        D = self.aircraft.fuselage.diameter
        r  = max(D, L / 4) / 2

        wing_span = getattr(getattr(self.aircraft, 'wing', None), 'span', 1.0) or 1.0
        dom_x = max(5.0 * L, 3.0)
        dom_y = max(3.0 * wing_span, 3.0)
        dom_z = max(5.0 * D, 2.0)
        mesh_base = self.base_mesh_size * 20
        mesh_wall = self.base_mesh_size
        x_min = -dom_x / 3
        x_max = 2 * dom_x / 3
        y_min = -dom_y / 2
        y_max = dom_y / 2
        z_min = -dom_z / 2
        z_max = dom_z / 2
        tol = min(dom_x, dom_y, dom_z) * 0.01

        return f"""// Auto-generated GEO — CFD external flow
// Aircraft: {self.aircraft.name}
SetFactory("OpenCASCADE");
lc_far = {mesh_base};
lc_wall = {mesh_wall};
Box(1) = {{ {x_min}, {y_min}, {z_min}, {dom_x}, {dom_y}, {dom_z} }};
Sphere(2) = {{0, 0, 0, {r}}};
BooleanDifference(3) = {{ Volume{{1}}; Delete; }}{{ Volume{{2}}; Delete; }};
Mesh.CharacteristicLengthMax = lc_far;
Mesh.CharacteristicLengthMin = lc_wall;
inlet_s() = Surface In BoundingBox{{ {x_min-tol}, {y_min-tol}, {z_min-tol}, {x_min+tol}, {y_max+tol}, {z_max+tol} }};
outlet_s() = Surface In BoundingBox{{ {x_max-tol}, {y_min-tol}, {z_min-tol}, {x_max+tol}, {y_max+tol}, {z_max+tol} }};
body_s() = Surface In BoundingBox{{ {-r*1.1}, {-r*1.1}, {-r*1.1}, {r*1.1}, {r*1.1}, {r*1.1} }};
Physical Surface("inlet") = {{ inlet_s() }};
Physical Surface("outlet") = {{ outlet_s() }};
Physical Surface("body") = {{ body_s() }};
Physical Volume("fluid") = {{3}};
Mesh.Algorithm = 6;
Mesh.Algorithm3D = 1;
"""

    def _old_generate_gmsh_script_unused(self) -> str:
        """Legacy - not used"""
        script = """
// OLD
mesh_base = 0.01;
mesh_wall = 0.001;
mesh_farfield = 0.2;

// ====================================================================
// DOMAIN (Computational Box)
// ====================================================================

// Domain boyutları (uçak/roket etrafında 5x mesafe)
domain_x = 5.0;
domain_y = 5.0;
domain_z = 5.0;

aircraft_length = 0.6;   // [Parametre: fuselage.length]

Point(1) = {-domain_x, -domain_y, -domain_z, mesh_farfield};
Point(2) = { domain_x, -domain_y, -domain_z, mesh_farfield};
Point(3) = { domain_x,  domain_y, -domain_z, mesh_farfield};
Point(4) = {-domain_x,  domain_y, -domain_z, mesh_farfield};
Point(5) = {-domain_x, -domain_y,  domain_z, mesh_farfield};
Point(6) = { domain_x, -domain_y,  domain_z, mesh_farfield};
Point(7) = { domain_x,  domain_y,  domain_z, mesh_farfield};
Point(8) = {-domain_x,  domain_y,  domain_z, mesh_farfield};

// Domain Lines
Line(1) = {1, 2};
Line(2) = {2, 3};
Line(3) = {3, 4};
Line(4) = {4, 1};
Line(5) = {5, 6};
Line(6) = {6, 7};
Line(7) = {7, 8};
Line(8) = {8, 5};
Line(9) = {1, 5};
Line(10) = {2, 6};
Line(11) = {3, 7};
Line(12) = {4, 8};

// Domain Surfaces
Curve Loop(1) = {1, 2, 3, 4};
Plane Surface(1) = {1};
Curve Loop(2) = {5, 6, 7, 8};
Plane Surface(2) = {2};
Curve Loop(3) = {1, 10, -5, -9};
Plane Surface(3) = {3};
Curve Loop(4) = {3, 12, -7, -11};
Plane Surface(4) = {4};
Curve Loop(5) = {2, 11, -6, -10};
Plane Surface(5) = {5};
Curve Loop(6) = {4, 9, -8, -12};
Plane Surface(6) = {6};

// Volume
Surface Loop(1) = {1, 2, 3, 4, 5, 6};
Volume(1) = {1};

// ====================================================================
// FUSELAGE (Gövde) — Silindir
// ====================================================================

fuselage_d = 0.05;       // Çap [Parametre: fuselage.diameter]
fuselage_l = 0.6;        // Uzunluk [Parametre: fuselage.length]

// Gövde merkez ekseni
Point(101) = {0, 0, 0, mesh_wall};
Point(102) = {fuselage_l, 0, 0, mesh_wall};

// Gövde kesiti (daire)
Point(103) = {0, fuselage_d/2, 0, mesh_wall};
Point(104) = {0, 0, fuselage_d/2, mesh_wall};
Point(105) = {0, -fuselage_d/2, 0, mesh_wall};
Point(106) = {0, 0, -fuselage_d/2, mesh_wall};

Point(107) = {fuselage_l, fuselage_d/2, 0, mesh_wall};
Point(108) = {fuselage_l, 0, fuselage_d/2, mesh_wall};
Point(109) = {fuselage_l, -fuselage_d/2, 0, mesh_wall};
Point(110) = {fuselage_l, 0, -fuselage_d/2, mesh_wall};

// Gövde çevresi
Circle(101) = {103, 101, 104};
Circle(102) = {104, 101, 105};
Circle(103) = {105, 101, 106};
Circle(104) = {106, 101, 103};

Circle(105) = {107, 102, 108};
Circle(106) = {108, 102, 109};
Circle(107) = {109, 102, 110};
Circle(108) = {110, 102, 107};

// Gövde çizgileri (eksenel)
Line(111) = {103, 107};
Line(112) = {104, 108};
Line(113) = {105, 109};
Line(114) = {106, 110};

// Gövde yüzeyleri
Curve Loop(101) = {101, 102, 103, 104};
Plane Surface(101) = {101};  // İlk enine kesit

Curve Loop(102) = {105, 106, 107, 108};
Plane Surface(102) = {102};  // Son enine kesit

Curve Loop(103) = {101, 112, -105, -111};
Ruled Surface(103) = {103};  // 1. yan yüzey

Curve Loop(104) = {102, 113, -106, -112};
Ruled Surface(104) = {104};  // 2. yan yüzey

Curve Loop(105) = {103, 114, -107, -113};
Ruled Surface(105) = {105};  // 3. yan yüzey

Curve Loop(106) = {104, 111, -108, -114};
Ruled Surface(106) = {106};  // 4. yan yüzey

// Gövde hacmi
Surface Loop(2) = {101, 102, 103, 104, 105, 106};
Volume(2) = {2};

// ====================================================================
// WING (Kanat)
// ====================================================================

wing_span = 1.5;         // Açıklık [Parametre: wing.span]
wing_chord = 0.25;       // Ortalama kord [Parametre: wing.airfoil.chord]

// Kanat kök noktaları
Point(201) = {0.1, -wing_span/2, 0, mesh_wall};
Point(202) = {0.1 + wing_chord, -wing_span/2, 0, mesh_wall};
Point(203) = {0.1 + wing_chord, wing_span/2, 0, mesh_wall};
Point(204) = {0.1, wing_span/2, 0, mesh_wall};

// Kanat çizgileri (basitleştirilmiş)
Line(201) = {201, 202};
Line(202) = {202, 203};
Line(203) = {203, 204};
Line(204) = {204, 201};

// Kanat yüzeyi
Curve Loop(201) = {201, 202, 203, 204};
Plane Surface(201) = {201};

// ====================================================================
// MESH CONTROL
// ====================================================================

// Wall boundary layer (inflation)
Field[1] = BoundaryLayer;
Field[1].EdgesList = {111, 112, 113, 114};  // Gövde sınırı
Field[1].hfar = mesh_base;
Field[1].hwall_n = mesh_wall;
Field[1].ratio = 1.2;
Field[1].Quads = 1;

// Refinement bölgesi (uçak etrafı)
Field[2] = Cylinder;
Field[2].XCenter = 0.3;
Field[2].YCenter = 0;
Field[2].ZCenter = 0;
Field[2].Radius = 0.3;
Field[2].VOut = mesh_farfield;
Field[2].VIn = mesh_base * 0.5;

Mesh.MeshSizeMax = mesh_farfield;
Mesh.MeshSizeMin = mesh_wall;

// ====================================================================
// 3D MESH
// ====================================================================

Mesh 3;
OptimizeMesh("Netgen");
Mesh.Format = 1;  // MSH format
Mesh.Binary = 0;

// ====================================================================
// OUTPUT
// ====================================================================

Save "aircraft_mesh.msh";
"""
        return script

    def generate_mesh_config(self) -> dict:
        """Mesh konfigürasyonu (json)"""
        mass_props = self.aircraft.mass_properties()

        config = {
            "aircraft": self.aircraft.to_dict(),
            "mesh": {
                "base_size": self.base_mesh_size,
                "boundary_layer": {
                    "enabled": True,
                    "wall_size": self.base_mesh_size / 10,
                    "growth_ratio": 1.2,
                    "num_layers": 10
                },
                "refinement_regions": self.refinement_regions,
                "expected_elements": self._estimate_element_count(),
                "expected_nodes": self._estimate_node_count()
            },
            "solver_config": {
                "domain_size": 5.0 * self.aircraft.fuselage.length,
                "wind_speed": 15.0,  # m/s
                "mach_number": 15.0 / 343,  # V / speed_of_sound
                "reynolds": self._calculate_reynolds(),
                "turbulence_model": "kOmegaSST" if self._calculate_reynolds() > 1e5 else "laminar"
            }
        }
        return config

    def _estimate_element_count(self) -> int:
        """Element sayısını tahmin et"""
        domain_vol = (10 * self.aircraft.fuselage.length) ** 3
        element_size = self.base_mesh_size ** 3
        return int(domain_vol / element_size)

    def _estimate_node_count(self) -> int:
        """Node sayısını tahmin et"""
        return int(self._estimate_element_count() * 1.2)

    def _calculate_reynolds(self) -> float:
        """Reynolds sayısı hesapla"""
        rho = 1.225  # kg/m³ (deniz seviyesi)
        V = 15.0  # m/s
        L = self.aircraft.fuselage.length
        mu = 1.81e-5  # Pa⋅s
        return (rho * V * L) / mu


# ─────────────────────────────────────────────────────────────────────────────
# MESH CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

class MeshConverter:
    """Gmsh MSH → OpenFOAM blockMeshDict / snappyHexMesh"""

    @staticmethod
    def generate_blockmeshdict(mesh_config: dict) -> str:
        """OpenFOAM blockMeshDict oluştur"""

        script = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      blockMeshDict;
}

convertToMeters 1;

vertices
(
    (-5 -5 -5)   // 0
    (5 -5 -5)    // 1
    (5  5 -5)    // 2
    (-5  5 -5)   // 3
    (-5 -5  5)   // 4
    (5 -5  5)    // 5
    (5  5  5)    // 6
    (-5  5  5)   // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (40 40 40) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {
        type patch;
        faces
        (
            (0 4 7 3)
        );
    }
    outlet
    {
        type patch;
        faces
        (
            (1 2 6 5)
        );
    }
    sides
    {
        type patch;
        faces
        (
            (0 1 5 4)
            (3 7 6 2)
            (0 3 2 1)
            (4 5 6 7)
        );
    }
);

mergePatchPairs
(
);
"""
        return script

    @staticmethod
    def gmsh_to_openfoam(msh_file: str, case_dir: str) -> None:
        """Gmsh MSH → OpenFOAM dönüştür"""
        import subprocess

        try:
            # gmshToFoam çalıştır
            cmd = f"gmshToFoam {msh_file} -case {case_dir}"
            subprocess.run(cmd, shell=True, check=True, timeout=1800)
            print(f"✅ Mesh converted: {msh_file} → {case_dir}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Conversion error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# EXAMPLE USAGE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Turkce konsol (cp1254) Unicode cikti veremez: dogru sonuc uretilip
    # UnicodeEncodeError ile cop olmasin diye akislar utf-8'e cevrilir.
    for _akis in (sys.stdout, sys.stderr):
        if hasattr(_akis, "reconfigure"):
            _akis.reconfigure(encoding="utf-8", errors="replace")
    from aircraft_geometry import AircraftLibrary

    # Model roket mesh oluştur
    roket = AircraftLibrary.model_rocket()
    mesh_gen = MeshGenerator(roket, mesh_size=0.01)

    # Kanat bölgesini incelt
    mesh_gen.add_refinement_region(
        "wing_region",
        location=(0.2, 0, 0),
        radius=0.3,
        factor=0.5
    )

    # Gmsh script oluştur
    gmsh_script = mesh_gen.generate_gmsh_script()
    with open("roket_mesh.geo", "w") as f:
        f.write(gmsh_script)
    print("✅ Gmsh script: roket_mesh.geo")

    # Mesh konfigürasyonu
    mesh_config = mesh_gen.generate_mesh_config()
    import json
    print(json.dumps(mesh_config, indent=2))

    # blockMeshDict
    blockmesh = MeshConverter.generate_blockmeshdict(mesh_config)
    with open("blockMeshDict", "w") as f:
        f.write(blockmesh)
    print("✅ blockMeshDict created")
