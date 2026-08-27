"""
1-Way FSI Coupling — CFD basinc alani -> FEA dugum kuvvetleri
=============================================================
OpenFOAM duvar basinc alanini (foamToVTK ciktisi) okur, her CFD yuzeyinde
dF = -p * n * A hesaplar, FEA STL dugumlerine en-yakin esleme ile aktarir.

Korunum garantisi: toplam kuvvet yeniden dagitildigi icin
sum(F_FEA) == sum(F_CFD) (makine hassasiyetinde).

VARSAYILAN BASINC-YALNIZDIR ve bu, adin gizledigi bir KAPSAM SINIRIYDI.
Bedeli 2026-08-27'de Turek-Hron FSI1 bayraginda OLCULDU
(`experiments/turek_hron_fsi1.py`, cozucunun kendi forces fonksiyonuyla):

    bayrak eksenel kuvvet   basinc  -3,017e-03 N
                            viskoz  +2,887e-02 N   -> viskoz 9,6 KAT buyuk

Yani ince, akisa PARALEL bir yuzeyde basinc-yalniz aktarim eksenel yukun
ancak ~%10'unu tasir. Enine (basinc-baskin) yonde ayni vakada aktarim
cozucunun integraliyle %0,03 icinde ortustu --- yani kusur aktarimda
DEGIL, kapsamdaydi.

`kayma=True` (ve `mu_pa_s`) ile viskoz cekme de tasinir; grad(U) alanindan
kurulur ve toplami cozucunun `forces` ciktisiyla %1 icinde ortusur. Kanat/
bayrak gibi narin yuzeylerde eksenel gerilme ya da uzama onemliyse bu
secenek ZORUNLUDUR. Varsayilan KAPALI birakildi cunku ek bir
son-islem adimi (grad(U) uretimi) ve dinamik viskozite ister; sessizce
acilsaydi alan bulunamayan her cagri duserdi.

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
    # BINARY KAPISI: bu ayristirici SATIR-TABANLIdir ve yalniz ASCII okur.
    # BINARY bir dosyada okuma sessizce YANLIS olabilir --- ikili baytlarin
    # cogu sayisal jeton vermez, read_floats erken durur ve GERCEKTEN OLANDAN
    # AZ nokta dondurur. Cokme garanti degildir; bu yuzden bicim burada
    # acikca reddedilir. Cozum cagiranda: foamToVTK -ascii.
    if any(s.strip().upper() == "BINARY" for s in lines[:6]):
        raise ValueError(
            f"{vtk_path.name} BINARY biciminde; bu ayristirici yalniz ASCII "
            "legacy VTK okur. foamToVTK'yi -ascii ile calistirin.")
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


def _vtk_vektor_alani(vtk_path: Path, ad: str):
    """Ayni legacy VTK'dan ADI VERILEN vektor alanini oku -> ((N,3), 'CELL'|'POINT').

    AYRI FONKSIYON, cunku `_parse_legacy_vtk`'nin dondurdugu 4'lu dokuz yerde
    aciliyor; arite degistirmek dokuzunu birden kirardi. Tarama ucuz (tek
    dosya, tek gecis) ve kirilma riski sifir.
    """
    lines = vtk_path.read_text(errors="replace").splitlines()
    if any(s.strip().upper() == "BINARY" for s in lines[:6]):
        raise ValueError(f"{vtk_path.name} BINARY; foamToVTK -ascii gerekir.")
    yer, i, n = None, 0, len(lines)
    while i < n:
        t = lines[i].split()
        if t and t[0] in ("CELL_DATA", "POINT_DATA"):
            yer = t[0].split("_")[0]
        elif t and t[0] == ad and len(t) >= 4:
            ncomp, ntup = int(t[1]), int(t[2])
            vals: list[float] = []
            j = i + 1
            while len(vals) < ncomp * ntup and j < n:
                tok = lines[j].split()
                if not tok or not _is_num(tok[0]):
                    break
                vals.extend(float(x) for x in tok)
                j += 1
            if len(vals) < ncomp * ntup:
                return None, None
            return np.array(vals[:ncomp * ntup]).reshape(ntup, ncomp), yer
        i += 1
    return None, None


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
                               rho: float = 1.225, p_is_kinematic: bool = True,
                               sema: str = "korunumlu", esleme: dict | None = None,
                               kayma: bool = False,
                               mu_pa_s: float | None = None):
    """CFD duvar basincini FEA STL dugum kuvvetlerine donustur.

    vtk_patch     : foamToVTK aircraft patch .vtk yolu
    fea_stl       : FEA yuzey STL (dugumler kuvvet alacak)
    p_is_kinematic: OpenFOAM incompressible p = P/rho (m2/s2). True ise rho ile carp.
    sema          : "korunumlu" (VARSAYILAN) ya da "tutarli" (eski)
    esleme        : `fsi_korunumlu_esleme.esleme_kur` ciktisi. Verilirse
                    YENIDEN KURULMAZ --- 2-yonlu kuplajda esleme REFERANS
                    konfigurasyonda bir kez kurulup tasinir.

    VARSAYILAN SEMA DEGISTI (2026-08-26) ve bu UC BAGIMSIZ OLCUME dayanir:

      KUVVET (24 vaka)     tutarli en kotu %72,04  ->  korunumlu %0,0000
      MOMENT (24 vaka)     tutarli ortalama %11,06 ->  korunumlu %1,66
                           korunumlu 24/24 vakada daha iyi
      DEFORME (25 vaka)    her tur yeniden arama dugum yukunun %123,8'ini
                           yalnizca deformasyondan dolayi yeniden dagitiyor;
                           sabit eslemede kayma %0,0000

    Eski sema NEDEN korunumsuzdu: basinci tasiyip kuvveti FEA aginda YENIDEN
    INTEGRE ediyordu (F = -p_interp * n_FEA * A_FEA). Iki yuzeyin alani
    farkliysa toplam kuvvet de farkli cikar. `_fsi_sinama`da (alan farki
    %41,3) net kuvvetin ISARETI bile ters cikiyordu.

    ESKI SEMA SILINMEDI: `sema="tutarli"` ile hala kosulur. Yayimlanmis bir
    sonucu yeniden uretmek ya da iki semayi kiyaslamak icin gerekir.

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

    # ── VISKOZ DUVAR CEKMESI (istege bagli) ──────────────────────────────
    # BASINC-YALNIZ AKTARIM AKISA PARALEL YUZEYLERDE YUKUN COGUNU KACIRIR:
    # Turek-Hron bayraginda olculdu, viskoz eksenel kuvvet basincinkinin
    # 9,6 kati (`experiments/turek_hron_fsi1.py`).
    #
    # NEDEN wallShearStress DEGIL: OpenFOAM 11'in o fonksiyon nesnesi bu
    # laminer vakada HER YUZDE TAM SIFIR yaziyor --- hem foamPostProcess
    # hem cozucu-ici kosuda denendi, ikisinde de uniform (0 0 0). Ayni
    # kosuda `forces` viskoz kuvveti dogru veriyor, yani viskozite orada
    # var. Alan yolu kapali oldugu icin cekme grad(U)'dan KURULUR:
    #     t_visc = mu (grad U + grad U^T) . n_disa
    # n_disa KATIDAN disari bakar --- yani BASINC terimiyle AYNI normal.
    # Cauchy cekmesi t = sigma . n_s katiya etkiyen kuvveti verir; basinc
    # icin t = -p n_s (kodda oyle) ve viskoz icin t = +mu (...) n_s. Ilk
    # yazimda buraya fazladan bir eksi koydum ve dogrulama isareti ANINDA
    # dusurdu: -2,859e-02 yerine cozucu +2,887e-02 diyordu.
    #
    # ISARET VE BUYUKLUK UYDURULMADI, OLCULDU: bu ifade bayrakta
    # 2,859e-02 N verdi, cozucunun kendi `forces` fonksiyonu 2,887e-02 N
    # --- %0,96 fark, grad(U)'nun sinira BIRINCI MERTEBEDEN
    # ekstrapolasyonundan. Dogrulama `kayma_kuvveti_N` alaninda her kosuda
    # raporlanir ki isaret sessizce donmesin.
    gradU = None
    if kayma:
        if mu_pa_s is None:
            return {"status": "FAILED",
                    "error": "kayma=True ama mu_pa_s verilmedi; dinamik "
                             "viskozite TAHMIN EDILMEZ"}
        G, g_yer = _vtk_vektor_alani(vtk_path, "grad(U)")
        if G is None or G.shape[1] != 9:
            return {"status": "FAILED",
                    "error": "kayma=True ama VTK'da grad(U) yok "
                             "(foamPostProcess -solver ... -func gradU)"}
        if g_yer == "POINT" or len(G) == len(points):
            G = np.array([G[list(p)].mean(axis=0) for p in polys])
        elif len(G) != len(polys):
            return {"status": "FAILED",
                    "error": f"grad(U) ({len(G)}) poligon ({len(polys)}) "
                             f"ile uyumsuz"}
        gradU = G.reshape(-1, 3, 3)
        gradU = gradU + np.transpose(gradU, (0, 2, 1))

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
    if gradU is not None:
        t_face = mu_pa_s * np.einsum("kij,kj->ki", gradU[nearest], f_normals)
        dF_face = dF_face + t_face * f_areas[:, None]
    total_F = dF_face.sum(axis=0)

    _kayma_F = None
    _esleme = esleme
    if sema == "korunumlu":
        from fsi_korunumlu_esleme import (
            disa_yonlendir,
            esleme_kur,
            esleme_uygula,
        )
        # NORMAL YONU FEA'NIN DIS-NORMALIYLE ESITLENIR. VTK poligon normali
        # sarim yonunden gelir; OLCULDU ki butun vakalarda ICERI bakiyor.
        # Esitlenmezse kuvvetin ISARETI ters cikar ve sonuc MAKUL GORUNUR.
        _n_cfd, _ = disa_yonlendir(cfd_centers, cfd_normals,
                                   f_centers, f_normals)
        dF_cfd_yuz = (-p_pa[:, None]) * _n_cfd * cfd_areas[:, None]
        if gradU is not None:
            # AYNI _n_cfd KULLANILIR: cekme de normal yonune bagli oldugu
            # icin isaret duzeltmesi ONA DA uygulanmali. Ayri isaret
            # kullanmak, basinc ve kayma bilesenlerini ters yonlerde
            # toplamak olurdu.
            _kayma = mu_pa_s * np.einsum("kij,kj->ki", gradU, _n_cfd)
            _kayma_F = (_kayma * cfd_areas[:, None]).sum(axis=0)
            dF_cfd_yuz = dF_cfd_yuz + _kayma * cfd_areas[:, None]
        if _esleme is None:
            _esleme = esleme_kur(cfd_centers, fea_nodes, faces, f_centers)
        node_forces = esleme_uygula(_esleme, dF_cfd_yuz, fea_nodes)
    else:
        # ESKI SEMA — yuzey kuvvetini 3 dugume esit dagit. Bu adim korunumlu
        # ama ONCESI degil: kuvvet FEA aginda YENIDEN INTEGRE edilmisti.
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
    # KORUNUM METRIGI KENDI KAYNAGIYLA KIYASLANIR. "Yeniden dagitim bir sey
    # kaybetti mi" sorusu, dagitilan seye baglidir: tutarli semada FEA yuz
    # kuvveti, korunumlu semada CFD yuz kuvveti. Sema degistigi halde olcut
    # eski kaynagi okumaya devam etseydi, %16,7 gibi anlamsiz bir "korunum
    # hatasi" cikardi --- olculen sey korunum degil IKI SEMA ARASINDAKI FARK
    # olurdu.
    _kaynak = (dF_cfd_yuz.sum(axis=0) if sema == "korunumlu" else total_F)
    _kaynak_tp = (float(np.linalg.norm(dF_cfd_yuz, axis=1).sum())
                  if sema == "korunumlu" else throughput)
    conservation_err = (np.linalg.norm(total_F_node - _kaynak)
                        / (_kaynak_tp + 1e-30))

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
    # MOMENT DE KENDI KAYNAGIYLA KIYASLANIR --- kuvvet gibi. Tutarli semada
    # kaynak FEA yuz kuvvetinin agirlik merkezindeki momenti; korunumlu semada
    # CFD yuz kuvvetinin CFD merkezindeki momenti.
    f_centroids = fea_nodes[faces].mean(axis=1)                      # (F,3)
    if sema == "korunumlu":
        _M_kaynak = np.cross(cfd_centers, dF_cfd_yuz).sum(axis=0)
        m_throughput = float(
            np.linalg.norm(np.cross(cfd_centers, dF_cfd_yuz), axis=1).sum())
    else:
        _M_kaynak = np.cross(f_centroids, dF_face).sum(axis=0)
        m_throughput = float(
            np.linalg.norm(np.cross(f_centroids, dF_face), axis=1).sum())
    M_face = _M_kaynak
    M_node = np.cross(fea_nodes, node_forces).sum(axis=0)
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
    # KORUNUMLU SEMADA CFD NORMALI YONLENDIRILIR ve karsilastirilan nicelik
    # DUGUMLERE GERCEKTEN GIDEN yuktur. Ilk surumde bu yapilmamisti ve iki
    # sema AYNI aktarim hatasini veriyordu (%13,4455) — cunku olcut hala eski
    # semanin YUZ kuvvetini okuyordu. Semayi degistirip olcutu degistirmemek,
    # degisikligi GORUNMEZ kilar.
    _n_olcut = cfd_normals
    if sema == "korunumlu":
        from fsi_korunumlu_esleme import disa_yonlendir
        _n_olcut, _ = disa_yonlendir(cfd_centers, cfd_normals,
                                     f_centers, f_normals)
    F_cfd = ((-p_pa[:, None]) * _n_olcut * cfd_areas[:, None])
    total_F_cfd = F_cfd.sum(axis=0)
    cfd_throughput = float(np.linalg.norm(F_cfd, axis=1).sum())
    _bol = max(cfd_throughput, throughput) + 1e-30
    _teslim = total_F_node if sema == "korunumlu" else total_F
    aktarim_err = float(np.linalg.norm(_teslim - total_F_cfd) / _bol)
    aktarim_err_ters = float(np.linalg.norm(_teslim + total_F_cfd) / _bol)
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
        # ESLEME CAGIRANA DONER: 2-yonlu kuplajda REFERANS
        # konfigurasyonda kurulup turlar boyunca TASINMALI.
        "esleme": _esleme,
        "sema": sema,
        # DUGUM KONUMLARI CAGIRANA GEREKLI: CalculiX dugum numarasi
        # KONUMA gore baglanir, STL indisine gore degil.
        "fea_nodes": fea_nodes,
        "n_loaded_nodes": len(forces),
        "p_min_Pa": float(p_pa.min()),
        "p_max_Pa": float(p_pa.max()),
        # TESLIM EDILEN YUK. Tutarli semada yuz-integrali ile ayni;
        # korunumlu semada dugum toplami ASILDIR.
        "total_force_N": [round(float(x), 4) for x in
                          (total_F_node if sema == "korunumlu" else total_F)],
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
        # KAYMA KANALI AYRI RAPORLANIR. Toplama gomulseydi isaret hatasi
        # gorunmezdi: yanlis isaretli bir kayma da "bir kuvvet" olarak
        # makul gorunur. Cagiran bunu cozucunun kendi viskoz kuvvetiyle
        # karsilastirabilsin diye yalniz kayma toplami da doner.
        "kayma_tasindi": bool(gradU is not None),
        "kayma_kuvveti_N": (None if _kayma_F is None else
                            [float(x) for x in _kayma_F]),
        "node_forces": forces,
    }


def dugum_eslemesi(fea_nodes, inp_path: str) -> dict:
    r"""STL köşesi → CalculiX düğüm numarası, KONUMA göre.

    ÖLÇÜLEN KUSUR: `cfd_pressure_to_fea_loads` düğüm anahtarını STL köşe
    İNDİSİNDEN üretiyor (`i+1`) ve `write_cload` onu doğrudan CalculiX düğüm
    numarası olarak yazıyordu. Bu, iki ağın düğümleri AYNI SIRADA yazdığını
    varsayar. Varsaymamalı: `_fsi_esnek` vakasında ilk 8 düğüm STL'in 8
    köşesinin ta kendisi ama SIRALARI FARKLI --- köşe 4 ile 7 yer değişmiş.
    Yani iki köşenin yükü yanlış konuma biniyordu.

    Ölçülen etki o vakada küçüktü (moment hatası %0,010; iki köşe birbirine
    yakın ve yükleri benzer). Ama bu bir tesadüftür, güvence değil: köşe
    sayısı arttıkça permütasyon keyfîleşir ve etki ölçülmemiştir. Bağlama
    KONUMA göre yapılırsa sıralama varsayımı tümüyle ortadan kalkar.

    Eşleşmeyen köşe SESSİZCE atlanmaz: sözlükte yoksa çağıran görür.
    """
    import re as _re

    import numpy as _np
    from scipy.spatial import cKDTree as _KD

    metin = Path(inp_path).read_text(errors="replace")
    i = metin.find("*NODE")
    j = metin.find("*ELEMENT", i)
    if i < 0 or j < 0:
        return {}
    koor, no = [], []
    for satir in metin[i:j].splitlines()[1:]:
        q = satir.split(",")
        if len(q) < 4:
            continue
        try:
            no.append(int(q[0]))
            koor.append([float(x) for x in q[1:4]])
        # sessiz-yutma: kabul — istisna BURADA eleme kriterinin kendisidir.
        # `*NODE` blogunda sayisal olmayan satir (yorum, devam isareti, ikinci
        # bir anahtar) DUGUM DEGILDIR; "ayristirilamadi" diye kaydetmek olmayan
        # bir kusuru rapor etmek olurdu. Bilgi kaybi yok: esleme sonucu
        # `dugum_eslemesi`nin donusunde SAYILABILIR --- kac kose eslesti,
        # cagiran gorur ve eslesmeyen kose sozlukte YOKTUR.
        except ValueError:
            no.pop() if len(no) > len(koor) else None
            continue
    if not koor:
        return {}
    d, idx = _KD(_np.asarray(koor)).query(_np.asarray(fea_nodes, float), k=1)
    # TOLERANS AGIN KENDI OLCEGINDEN: mutlak bir metre degeri, milimetrik bir
    # modelde her seyi eslestirir, metrelik bir modelde hicbir seyi.
    kk = _np.asarray(koor)
    olcek = float(_np.linalg.norm(kk.max(0) - kk.min(0))) + 1e-30
    tol = 1e-6 * olcek
    return {int(s + 1): int(no[t]) for s, (t, dd) in enumerate(zip(idx, d))
            if dd <= tol}


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
