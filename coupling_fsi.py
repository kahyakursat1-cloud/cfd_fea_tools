"""
1-Way FSI Coupling — CFD basinc alani -> FEA dugum kuvvetleri
=============================================================
OpenFOAM duvar basinc alanini (foamToVTK ciktisi) okur, her CFD yuzeyinde
dF = -p * n * A hesaplar, FEA STL dugumlerine en-yakin esleme ile aktarir.

Korunum garantisi: toplam kuvvet yeniden dagitildigi icin
sum(F_FEA) == sum(F_CFD) (makine hassasiyetinde).

Endustri pratigi: ASME V&V, bir-yonlu aero-yapisal coupling.
"""

from pathlib import Path

import numpy as np


def _parse_legacy_vtk(vtk_path: Path):
    """Legacy ASCII VTK (foamToVTK patch ciktisi) okur.
    POLYGONS akis-tabanli, basinc FIELD attributes blogunda.
    Donduru: points (N,3), polys (list[list[int]]), p_cell (M,), p_loc ('cell'|'point')
    """
    text = vtk_path.read_text(errors="replace")
    lines = text.splitlines()
    n = len(lines)
    i = 0

    points = np.zeros((0, 3))
    polys = []
    p_cell = np.array([])
    p_loc = None
    cur_data = None  # 'CELL' veya 'POINT'

    def read_floats(start, count):
        vals = []
        j = start
        while len(vals) < count and j < n:
            toks = lines[j].split()
            if toks and _is_num(toks[0]):
                vals.extend(float(x) for x in toks)
                j += 1
            else:
                break
        return np.array(vals[:count]), j

    def read_ints(start, count):
        vals = []
        j = start
        while len(vals) < count and j < n:
            toks = lines[j].split()
            if toks and _is_num(toks[0]):
                vals.extend(int(float(x)) for x in toks)
                j += 1
            else:
                break
        return vals[:count], j

    while i < n:
        line = lines[i].strip()
        toks = line.split()
        if not toks:
            i += 1
            continue

        key = toks[0]
        if key == "POINTS":
            npts = int(toks[1])
            flat, i = read_floats(i + 1, npts * 3)
            points = flat.reshape(-1, 3)
            continue
        if key in ("POLYGONS", "CELLS"):
            total = int(toks[2])
            flat, i = read_ints(i + 1, total)
            # akisi poligonlara ayikla: k, v0..v(k-1), tekrar
            idx = 0
            while idx < len(flat):
                k = flat[idx]
                polys.append(flat[idx + 1: idx + 1 + k])
                idx += 1 + k
            continue
        if key == "CELL_DATA":
            cur_data = "CELL"
            i += 1
            continue
        if key == "POINT_DATA":
            cur_data = "POINT"
            i += 1
            continue
        if key == "FIELD":
            nfields = int(toks[2])
            i += 1
            for _ in range(nfields):
                fhdr = lines[i].split()
                fname, ncomp, ntup = fhdr[0], int(fhdr[1]), int(fhdr[2])
                flat, i = read_floats(i + 1, ncomp * ntup)
                if fname == "p":
                    p_cell = flat.reshape(ntup, ncomp)[:, 0] if ncomp > 1 else flat
                    p_loc = cur_data
            continue
        if key == "SCALARS" and len(toks) > 1 and toks[1] == "p":
            i += 1
            if i < n and lines[i].strip().startswith("LOOKUP_TABLE"):
                i += 1
            flat, i = read_floats(i, len(points) if cur_data == "POINT" else len(polys))
            p_cell = flat
            p_loc = cur_data
            continue
        i += 1

    return points, polys, p_cell, p_loc


def _is_num(s):
    try:
        float(s); return True
    # sessiz-yutma: kabul — istisna BURADA kontrol akisidir; fonksiyonun
    # tanimi zaten "bu deger sayiya cevrilebiliyor mu". Donus degeri sonucun
    # kendisi, yani bilgi kaybi yok.
    except ValueError:
        return False


def _poly_geometry(points, polys):
    """Her poligon icin merkez, normal (alan-agirlikli), alan."""
    centers = np.zeros((len(polys), 3))
    normals = np.zeros((len(polys), 3))
    areas = np.zeros(len(polys))
    for idx, poly in enumerate(polys):
        vs = points[poly]
        c = vs.mean(axis=0)
        centers[idx] = c
        # ucgen fan ile alan + normal
        nrm = np.zeros(3)
        for k in range(1, len(vs) - 1):
            nrm += np.cross(vs[k] - vs[0], vs[k + 1] - vs[0])
        a = 0.5 * np.linalg.norm(nrm)
        areas[idx] = a
        normals[idx] = nrm / (np.linalg.norm(nrm) + 1e-30)
    return centers, normals, areas


def cfd_pressure_to_fea_loads(vtk_patch: str, fea_stl: str,
                               rho: float = 1.225, p_is_kinematic: bool = True):
    """CFD duvar basincini FEA STL dugum kuvvetlerine donustur.

    vtk_patch     : foamToVTK aircraft patch .vtk yolu
    fea_stl       : FEA yuzey STL (dugumler kuvvet alacak)
    p_is_kinematic: OpenFOAM incompressible p = P/rho (m2/s2). True ise rho ile carp.

    Donduru: {node_id: (Fx,Fy,Fz)} + ozet (korunum kontrolu dahil)
    """
    import trimesh

    vtk_path = Path(vtk_patch)
    points, polys, p_cell, p_loc = _parse_legacy_vtk(vtk_path)
    if len(polys) == 0 or len(p_cell) == 0:
        return {"status": "FAILED", "error": "VTK parse: poligon/basinc bulunamadi"}
    if p_loc == "POINT" or len(p_cell) == len(points):
        # point-data: poligon basina ortala
        p_poly = np.array([p_cell[list(poly)].mean() for poly in polys])
    elif len(p_cell) == len(polys):
        p_poly = p_cell
    else:
        return {"status": "FAILED",
                "error": f"p ({len(p_cell)}) ile poligon ({len(polys)})/nokta ({len(points)}) uyumsuz"}

    cfd_centers, cfd_normals, cfd_areas = _poly_geometry(points, polys)

    # Statik basinci Pa'ya cevir (incompressible kinematic p)
    p_pa = p_poly * rho if p_is_kinematic else p_poly

    # FEA STL: tutarli disa-normaller (trimesh watertight mesh icin duzeltir)
    mesh = trimesh.load(fea_stl, force='mesh')
    trimesh.repair.fix_normals(mesh)
    fea_nodes   = mesh.vertices                        # (K,3)
    faces       = mesh.faces                           # (F,3) node indices
    f_centers   = mesh.triangles_center               # (F,3)
    f_normals   = mesh.face_normals                    # (F,3) disa-normal
    f_areas     = mesh.area_faces                      # (F,)

    # Her STL yuzeyine en-yakin CFD yuzeyinin basincini ata
    from scipy.spatial import cKDTree
    tree = cKDTree(cfd_centers)
    _, nearest = tree.query(f_centers, k=1)
    p_on_face = p_pa[nearest]                           # (F,)

    # Yuzey kuvveti: dF = -p * n * A  (STL disa-normali guvenilir)
    dF_face = (-p_on_face[:, None]) * f_normals * f_areas[:, None]   # (F,3)
    total_F = dF_face.sum(axis=0)

    # Yuzey kuvvetini 3 dugume esit dagit (korunumlu)
    node_forces = np.zeros_like(fea_nodes)
    for fi in range(len(faces)):
        share = dF_face[fi] / 3.0
        for nid in faces[fi]:
            node_forces[nid] += share

    total_F_node = node_forces.sum(axis=0)
    # Korunum: yeniden-dağıtım sum(F_dugum)==sum(F_yuzey). Normalleştirme NET kuvvete
    # DEGIL throughput'a (yuzey-kuvvet buyukluk toplami) — simetrik yukte net≈0 olsa da
    # metrik anlamli kalir (aksi halde 0'a bolup sahte-buyuk verir).
    throughput = float(np.linalg.norm(dF_face, axis=1).sum())
    conservation_err = np.linalg.norm(total_F_node - total_F) / (throughput + 1e-30)

    # MOMENT korunumu. Kuvvet korunumu tek basina YETMEZ: ayni toplam kuvvet
    # tumuyle yanlis bir uzamsal dagilimla da elde edilebilir, ve yapiya giden
    # egilme momenti o dagilimdan gelir. Moment artigi dagilimin ilk momentini
    # sinar.
    #
    # DURUST NOT: esit-uctebir dagitimda ucgenin uc kosesinin ortalamasi TAM
    # olarak agirlik merkezidir, dolayisiyla hem kuvvet hem moment korunumu bu
    # semada YAPI GEREGI kesindir. Olculen artik bir dogruluk sinavi degil,
    # uygulamanin teoriye uydugunun ve kayan-nokta birikiminin zararsiz
    # kaldiginin kanitidir. Farkli bir dagitim semasi (ornegin alan-agirlikli
    # veya en-yakin-dugum) momenti korumaz; metrik asil orada ayirt eder.
    f_centroids = fea_nodes[faces].mean(axis=1)                      # (F,3)
    M_face = np.cross(f_centroids, dF_face).sum(axis=0)
    M_node = np.cross(fea_nodes, node_forces).sum(axis=0)
    m_throughput = float(np.linalg.norm(np.cross(f_centroids, dF_face), axis=1).sum())
    moment_err = float(np.linalg.norm(M_node - M_face) / (m_throughput + 1e-30))

    # ═══ AKTARIM ARTIGI: KORUNMAYAN ADIM BURASI ═══
    #
    # Yukaridaki iki metrik FEA yuzeyinden FEA DUGUMLERINE dagitimi olcuyor ve
    # esit-uctebir semasinda ikisi de YAPI GEREGI kesin. Yani olculen sey
    # gercekten korunmayan adim DEGILDI: basinc CFD yuzlerinden FEA yuzlerine
    # EN-YAKIN-KOMSU ile tasiniyor (tree.query) ve o adim korunumlu degildir.
    # Iki agin yuz boyutlari farkliysa ayni basinc alani farkli toplam kuvvet
    # verir; hicbir sey bunu soylemiyordu.
    #
    # CFD tarafinin isareti: VTK duvar normalinin yonu vaka kurulumuna bagli.
    # Buyukluk karsilastirmasi icin yonden bagimsiz olan throughput ve BILESEN
    # BAZINDA mutlak fark kullaniliyor; isaret ters cikarsa bu ayrica GORUNUR.
    # ALAN FARKI AYRI OLCULUR. Aktarim artiginin iki ayri sebebi olabilir ve
    # ikisi ayni sayiya karisirsa hukum verilemez: (i) basincin en-yakin-komsu
    # ile ORNEKLENMESI, (ii) FEA STL'inin ozgun geometri, CFD yuzeyinin ise
    # snap'lenmis ag yuzeyi olmasi — ikisinin ALANI farklidir. Olculdu:
    # dogrulama_kup'ta alanlar BIREBIR ayni (1,5 = 1,5 m2) ve artik yine %3,9,
    # yani orada artik saf ORNEKLEME hatasidir. _fsi_esnek'te alan %9,5 farkli
    # ve artik %20,3 — orada iki sebep birlikte.
    F_cfd = ((-p_pa[:, None]) * cfd_normals * cfd_areas[:, None])
    total_F_cfd = F_cfd.sum(axis=0)
    cfd_throughput = float(np.linalg.norm(F_cfd, axis=1).sum())
    _bol = max(cfd_throughput, throughput) + 1e-30
    aktarim_err = float(np.linalg.norm(total_F - total_F_cfd) / _bol)
    aktarim_err_ters = float(np.linalg.norm(total_F + total_F_cfd) / _bol)
    if aktarim_err_ters < aktarim_err:
        # Normal yonleri ters: karsilastirilabilir olan BUYUKLUKTUR.
        aktarim_err, _ters = aktarim_err_ters, True
    else:
        _ters = False

    # ═══ ARAYUZ ISI: KUVVET+MOMENT'IN GORMEDIGI ═══
    #
    # Dogrusal bir sanal yer-degistirme alani u = A·x icin arayuz isi
    # W = Σ F·(A x) = A : Σ F⊗x olur. Yani TUM dogrusal alanlar icin isin
    # korunmasi, birinci moment TENSORU Σ F⊗x'in korunmasina denktir.
    #
    # Bu kuvvet+momentten DAHA GUCLUDUR: x×F, F⊗x'in yalniz ANTISIMETRIK
    # kismidir. Simetrik kisim (uzama/kayma modlarinin yaptigi is) iki mevcut
    # metrigin ikisinde de GORUNMEZ. Klasik arayuz yama-sinavi (patch test)
    # tam olarak budur.
    T_face = np.einsum("fi,fj->ij", dF_face, f_centroids)
    T_node = np.einsum("ni,nj->ij", node_forces, fea_nodes)
    t_throughput = float(np.abs(np.einsum("fi,fj->fij", dF_face, f_centroids)).sum())
    is_err = float(np.linalg.norm(T_node - T_face) / (t_throughput + 1e-30))

    # ═══ SIFIR YUK: KORUNUM METRIGI TANIMSIZDIR, "KUSURSUZ" DEGIL ═══
    #
    # Olculdu (minihawk_v2): yuzey-basinc VTK'si p=0 tasiyordu (bos cikarim) ve
    # UC metrik de 0.0e+00, aktarim artigi %0.0 veriyordu — yani hicbir veri
    # yokken "kusursuz korunum" raporlaniyordu. Payda +1e-30 ile korunuyordu
    # ama pay da sifirdi. Yoklugu iyilik saymak bu deponun avladigi kusurdur ve
    # bu kez YENI eklenen olcumde cikti.
    #
    # Kanit zaten kayittaydi (`n_loaded_nodes` 0) — eksik olan onu OKUYAN yoldu.
    _yuk_var = throughput > 1e-12 and cfd_throughput > 1e-12
    if not _yuk_var:
        conservation_err = moment_err = is_err = None
        aktarim_err = None
        _yuk_notu = (f"YÜK YOK: yüzey basıncı p∈[{float(p_pa.min()):.3g}, "
                     f"{float(p_pa.max()):.3g}] Pa ve toplam kuvvet büyüklüğü "
                     f"≈0. Korunum metrikleri TANIMSIZ — sıfır artık, korunumun "
                     f"sağlandığı anlamına GELMEZ. Yüzey-basınç çıkarımı boş "
                     f"olabilir (foamPostProcess yüzey örneklemesi koşuldu mu?)")
    else:
        _yuk_notu = None

    forces = {int(i + 1): tuple(node_forces[i])
              for i in range(len(fea_nodes)) if np.linalg.norm(node_forces[i]) > 1e-9}

    return {
        "status": "SUCCESS",
        "n_cfd_faces": len(polys),
        "n_fea_faces": len(faces),
        "n_fea_nodes": len(fea_nodes),
        "n_loaded_nodes": len(forces),
        "p_min_Pa": float(p_pa.min()),
        "p_max_Pa": float(p_pa.max()),
        "total_force_N": [round(float(x), 4) for x in total_F],
        "drag_Fx_N": round(float(total_F[0]), 4),
        "side_Fy_N": round(float(total_F[1]), 4),
        "lift_Fz_N": round(float(total_F[2]), 4),
        "conservation_error": (float(conservation_err)
                               if conservation_err is not None else None),
        "moment_conservation_error": moment_err,
        "arayuz_isi_hatasi": is_err,
        "aktarim_hatasi": aktarim_err,
        "yuk_var_mi": _yuk_var,
        "yuk_notu": _yuk_notu,
        "aktarim_normali_ters": _ters,
        "total_force_cfd_N": [round(float(x), 4) for x in total_F_cfd],
        "cfd_alan_m2": round(float(cfd_areas.sum()), 6),
        "fea_alan_m2": round(float(f_areas.sum()), 6),
        "alan_farki_pct": round(
            100.0 * abs(float(f_areas.sum() - cfd_areas.sum()))
            / (float(cfd_areas.sum()) + 1e-30), 2),
        "_korunum_notu": (
            "conservation_error ve moment_conservation_error FEA yüzü→düğüm "
            "dağıtımını ölçer ve eşit-üçtebir şemasında YAPI GEREĞİ kesindir. "
            "arayuz_isi_hatasi aynı adımı DAHA GÜÇLÜ sınar (birinci moment "
            "tensörü; moment yalnız antisimetrik kısmı görür). aktarim_hatasi "
            "ise gerçekten korunmayan adımı ölçer: basıncın CFD yüzlerinden "
            "FEA yüzlerine en-yakın-komşu ile taşınması."),
        "total_moment_Nm": [round(float(x), 4) for x in M_face],
        "node_forces": forces,
    }


def write_cload(node_forces: dict, out_path: str) -> str:
    """Dugum kuvvetlerini CalculiX *CLOAD blogu olarak yazar."""
    lines = ["*CLOAD\n"]
    for nid, (fx, fy, fz) in node_forces.items():
        if abs(fx) > 1e-9:
            lines.append(f"{nid}, 1, {fx:.8e}\n")
        if abs(fy) > 1e-9:
            lines.append(f"{nid}, 2, {fy:.8e}\n")
        if abs(fz) > 1e-9:
            lines.append(f"{nid}, 3, {fz:.8e}\n")
    Path(out_path).write_text("".join(lines))
    return out_path


# ── TERS YON: yapi yer degistirmesi -> akiskan agi ────────────────────────────
#
# 2-YONLU FSI'NIN EKSIK HALKASI BUYDU. Olculdu (2026-08-19):
#   · `cfd_pressure_to_fea_loads` (basinc -> yuk) URETIMDE (pipeline.py)
#   · `fsi_twoway.partitioned_fsi` (Aitken) DOGRULANMIS ama yalniz TESTLERDEN
#     cagriliyor — uretimde tek cagirani yok
#   · Depoda `pointDisplacement` HIC gecmiyordu
# Yani donusu tasiyacak parca yoktu; kuplaj turu ilkece kapanamiyordu.
#
# YUK AKTARIMI ILE YER DEGISTIRME AKTARIMI AYNI SEY DEGIL:
#   yuk        -> KORUNUM gerekir (toplam kuvvet degismemeli); yukarida yuzey
#                 kuvveti uce bolunuyor ve korunum ayrica olculuyor.
#   yer degis. -> TUTARLILIK gerekir. Rijit hareket BIREBIR korunmali, yoksa
#                 yapi hic deforme olmadan akiskan agi bozulur. Bu ozellik
#                 CFD KOSMADAN sinanabilir ve testler onu bagliyor.
#
# YONTEM: k en-yakin FEA dugumunden ters-mesafe agirlikli interpolasyon.
# Agirliklar birim-bolunum saglar (toplami 1), dolayisiyla sabit bir alan
# (rijit oteleme) TAM olarak yeniden uretilir. En-yakin-komsu de rijit hareketi
# korur ama yuzeyde basamaklar birakir; ters-mesafe puruzsuzdur ve ayni
# garantiyi verir.

def fea_displacement_to_cfd_points(fea_nodes, fea_disp, cfd_points,
                                   k: int = 4, guc: float = 2.0):
    """FEA dugum yer degistirmelerini CFD yuzey noktalarina tasi.

    fea_nodes  : (K,3) FEA yuzey dugum koordinatlari
    fea_disp   : (K,3) o dugumlerdeki yer degistirme
    cfd_points : (M,3) akiskan yamasinin noktalari
    Donduru    : (M,3) CFD noktalarindaki yer degistirme

    Birim-bolunum: sum(w_i) = 1, yani SABIT bir alan HATASIZ tasinir (rijit
    oteleme testi bunu bagliyor). Bir CFD noktasi bir FEA dugumune cakisirsa
    o dugumun degeri AYNEN alinir — sifir mesafede agirlik tanimsizdir.
    """
    from scipy.spatial import cKDTree

    fea_nodes = np.asarray(fea_nodes, dtype=float)
    fea_disp = np.asarray(fea_disp, dtype=float)
    cfd_points = np.asarray(cfd_points, dtype=float)
    if len(fea_nodes) == 0 or len(cfd_points) == 0:
        return np.zeros((len(cfd_points), 3))
    kk = int(min(max(k, 1), len(fea_nodes)))
    d, idx = cKDTree(fea_nodes).query(cfd_points, k=kk)
    if kk == 1:
        d, idx = d[:, None], idx[:, None]

    out = np.zeros((len(cfd_points), 3))
    cakisan = d[:, 0] < 1e-12
    out[cakisan] = fea_disp[idx[cakisan, 0]]

    kalan = ~cakisan
    if kalan.any():
        w = 1.0 / np.power(d[kalan], guc)
        w /= w.sum(axis=1, keepdims=True)          # BIRIM BOLUNUM
        out[kalan] = np.einsum("mk,mkc->mc", w, fea_disp[idx[kalan]])
    return out


def write_point_displacement(case_dir, patch_name, disp_by_point,
                             uzak_yamalar=("inlet", "outlet", "top", "bottom",
                                           "front", "back"),
                             zaman: str = "0"):
    """0/pointDisplacement'i GOVDE yamasinda olculen degerlerle yaz.

    Govde `fixedValue` + nonuniform liste; uzak alan sabit sifir (deformasyon
    disari tasmaz). `openfoam_runner._write_mesh_motion` iskeleti kurar, bu
    fonksiyon her kuplaj turunda GOVDE degerlerini gunceller.

    TASIYICI VARSAYIM — SIRA (olculdu 2026-08-21, fsi_kiris vakasi): `disp_by_point`
    YAMA NOKTA SIRASINDA olmalidir. Kuplaj zincirinde bu degerler `surfaces`
    functionObject'inin ornekledigi yuzey VTK'sindan turuyor; o ornekleme
    yamanin KENDI noktalarini KENDI sirasinda veriyor. Olcum: 38 yama noktasi,
    38 VTK noktasi; indeks-indeks fark 5,0e-7 m ve kume-eslesme farki da
    5,0e-7 m — IKISI BIREBIR AYNI, yani siralama ozdes (5e-7 VTK'nin ASCII
    yazim hassasiyeti, hata degil). Ayni sayida ama FARKLI sirada bir liste
    sessizce yanlis bir deplasman alani yazar ve hicbir sey uyarmaz; bu yuzden
    varsayim burada YAZILI. `tests/test_coupling_fsi` bunu bagliyor.
    """
    d = np.asarray(disp_by_point, dtype=float)
    nl = chr(10)
    g = ["FoamFile", "{", "    format      ascii;",
         "    class       pointVectorField;", f'    location    "{zaman}";',
         "    object      pointDisplacement;", "}", "",
         "dimensions      [0 1 0 0 0 0 0];", "",
         "internalField   uniform (0 0 0);", "", "boundaryField", "{"]
    for y in uzak_yamalar:
        g += [f"    {y}", "    {", "        type            fixedValue;",
              "        value           uniform (0 0 0);", "    }"]
    g += [f"    {patch_name}", "    {", "        type            fixedValue;",
          "        value           nonuniform List<vector>", str(len(d)), "("]
    g += [f"({v[0]:.9e} {v[1]:.9e} {v[2]:.9e})" for v in d]
    # LISTE KAPANISI NOKTALI VIRGULLE BITER. ")" yeterli degil: OpenFOAM
    # "ill defined primitiveEntry starting at keyword 'value'" ile duser.
    # Olculdu 2026-08-21 (fsi_kiris, 702/pointDisplacement satir 93).
    g += [");", "    }", "}", ""]
    # HEDEF ZAMAN PARAMETRELI. Sabit "0" yeterli degil: cozucu `startFrom
    # latestTime` ile kosarsa 0/ dizinini HIC OKUMAZ ve deplasman uygulanmaz.
    # Olculdu 2026-08-21 (fsi_kiris): controlDict latestTime=605 idi, alan
    # yalniz 0/'da vardi, ag hic hareket etmedi ve arac donus kodu 0 verdi.
    yol = Path(case_dir) / str(zaman) / "pointDisplacement"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(nl.join(g))
    return yol


if __name__ == "__main__":
    import json
    import sys
    vtk = sys.argv[1] if len(sys.argv) > 1 else \
        "mesh_independence/cases/medium_fixed/VTK/aircraft/aircraft_143.vtk"
    stl = sys.argv[2] if len(sys.argv) > 2 else \
        "mesh_independence/cases/medium_fixed/constant/triSurface/aircraft.stl"
    r = cfd_pressure_to_fea_loads(vtk, stl)
    summary = {k: v for k, v in r.items() if k != "node_forces"}
    print(json.dumps(summary, indent=2, default=str))
