"""1-way FSI coupling birim testleri — KORUNUM garantisi (sum F_FEA==sum F_CFD) kalbi,
VTK parse, poligon-geometri, CLOAD yazımı. Sentetik girdi (gerçek CFD/STL fixture gerekmez)."""
import numpy as np
import pytest

from coupling_fsi import (
    _parse_legacy_vtk,
    _poly_geometry,
    cfd_pressure_to_fea_loads,
    write_cload,
)

trimesh = pytest.importorskip("trimesh")


def test_poly_geometry_unit_square():
    """Birim kare poligonu → alan=1, normal=±z, merkez=(0.5,0.5,0)."""
    pts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    c, n, a = _poly_geometry(pts, [[0, 1, 2, 3]])
    assert a[0] == pytest.approx(1.0)
    assert abs(n[0, 2]) == pytest.approx(1.0)            # normal z-yönünde
    assert c[0] == pytest.approx([0.5, 0.5, 0.0])


def test_write_cload_format(tmp_path):
    out = write_cload({5: (1.0, 0.0, -2.0)}, str(tmp_path / "cl.inp"))
    txt = open(out).read()
    assert txt.startswith("*CLOAD")
    assert "5, 1, 1.00000000e+00" in txt          # Fx
    assert "5, 3, -2.00000000e+00" in txt         # Fz
    assert "5, 2," not in txt                      # Fy=0 → yazılmaz


def _write_vtk(path, p_val=100.0):
    """Tek birim-kare poligonlu minimal legacy VTK (CELL_DATA FIELD p)."""
    path.write_text(
        "# vtk DataFile Version 3.0\ntest\nASCII\nDATASET POLYDATA\n"
        "POINTS 4 float\n0 0 0\n1 0 0\n1 1 0\n0 1 0\n"
        "POLYGONS 1 5\n4 0 1 2 3\n"
        f"CELL_DATA 1\nFIELD attributes 1\np 1 1 float\n{p_val}\n")


def test_parse_legacy_vtk(tmp_path):
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 50.0)
    points, polys, p_cell, p_loc = _parse_legacy_vtk(v)
    assert points.shape == (4, 3)
    assert len(polys) == 1 and list(polys[0]) == [0, 1, 2, 3]
    assert p_cell[0] == pytest.approx(50.0) and p_loc == "CELL"


def test_conservation_machine_precision(tmp_path):
    """KALP: yüzey kuvveti 3 düğüme dağıtılır → sum(F_düğüm)==sum(F_yüzey) makine-hassas.
    Korunum eşleme/basınçtan BAĞIMSIZ (yeniden-dağıtım kimliği)."""
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 100.0)
    stl = tmp_path / "box.stl"
    trimesh.creation.box(extents=(1, 1, 1)).export(str(stl))
    r = cfd_pressure_to_fea_loads(str(v), str(stl), rho=1.225)
    assert r["status"] == "SUCCESS"
    assert r["conservation_error"] < 1e-10        # korunum garantisi
    # düğüm-kuvvet toplamı = yüzey-kuvvet toplamı (her bileşen)
    fn = np.array([list(f) for f in r["node_forces"].values()]).sum(axis=0)
    assert fn == pytest.approx(r["total_force_N"], abs=1e-6)


def test_pressure_sign_and_kinematic_scale(tmp_path):
    """p_kinematic=True → p Pa'ya ρ ile ölçeklenir; dF=-p·n·A işareti tutarlı."""
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 10.0)
    stl = tmp_path / "box.stl"
    trimesh.creation.box(extents=(1, 1, 1)).export(str(stl))
    r = cfd_pressure_to_fea_loads(str(v), str(stl), rho=2.0, p_is_kinematic=True)
    assert r["p_max_Pa"] == pytest.approx(20.0)   # 10 * rho(2.0)


def test_moment_conservation_machine_precision(tmp_path):
    """Kuvvet korunumu tek başına YETMEZ: aynı toplam kuvvet yanlış uzamsal
    dağılımla da elde edilebilir ve yapıya giden eğilme momenti o dağılımdan gelir.
    Eşit-üçtebir dağıtımda üç köşenin ortalaması tam olarak ağırlık merkezi
    olduğundan moment de yapı gereği korunmalı; bu test onu ölçer."""
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 100.0)
    stl = tmp_path / "box.stl"
    trimesh.creation.box(extents=(1, 1, 1)).export(str(stl))
    r = cfd_pressure_to_fea_loads(str(v), str(stl), rho=1.225)
    assert r["status"] == "SUCCESS"
    assert r["moment_conservation_error"] < 1e-10, r["moment_conservation_error"]
    assert len(r["total_moment_Nm"]) == 3


def test_moment_metric_ASIMETRIK_yukte_de_anlamli(tmp_path):
    """Simetrik kutuda net moment ≈0 olabilir; metrik throughput'a normalize
    edildiği için o durumda bile sahte-büyük değer vermemeli."""
    v = tmp_path / "patch.vtk"
    _write_vtk(v, 250.0)
    stl = tmp_path / "wedge.stl"
    trimesh.creation.box(extents=(2, 1, 0.5)).export(str(stl))
    r = cfd_pressure_to_fea_loads(str(v), str(stl), rho=1.0)
    assert r["status"] == "SUCCESS"
    assert 0.0 <= r["moment_conservation_error"] < 1e-10


# ── TERS YÖN: yapı yer değiştirmesi → akışkan ağı ─────────────────────────

def test_rijit_hareket_BIREBIR_tasiniyor():
    """Yük aktarımı KORUNUM ister, yer değiştirme aktarımı TUTARLILIK.

    Yapı rijit ötelenirse akışkan ağı da aynen ötelenmeli. Aksi halde yapı
    HİÇ DEFORME OLMADAN ağ bozulur — 2-yönlü FSI'de bu, ilk turda çözümü
    kirletir ve hata her turda birikir.

    Ters-mesafe ağırlıkları birim-bölünüm sağlar (toplamı 1), o yüzden sabit
    bir alan hatasız taşınır. Bu özellik CFD KOŞMADAN sınanabilir.
    """
    import numpy as np

    from coupling_fsi import fea_displacement_to_cfd_points as tasi
    rng = np.random.default_rng(0)
    fea, cfd = rng.random((40, 3)), rng.random((25, 3))
    t = np.array([0.3, -0.7, 1.1])
    out = tasi(fea, np.tile(t, (40, 1)), cfd)
    assert np.abs(out - t).max() < 1e-12, "rijit öteleme bozuluyor"


def test_cakisan_nokta_AYNEN_aliniyor():
    """Sıfır mesafede ağırlık tanımsız; değer doğrudan atanmalı."""
    import numpy as np

    from coupling_fsi import fea_displacement_to_cfd_points as tasi
    rng = np.random.default_rng(1)
    fea, d = rng.random((30, 3)), rng.random((30, 3))
    out = tasi(fea, d, fea[:8])
    assert np.abs(out - d[:8]).max() == 0.0


def test_sifir_yer_degistirme_SIFIR_kaliyor():
    import numpy as np

    from coupling_fsi import fea_displacement_to_cfd_points as tasi
    rng = np.random.default_rng(2)
    fea, cfd = rng.random((20, 3)), rng.random((15, 3))
    assert np.abs(tasi(fea, np.zeros((20, 3)), cfd)).max() == 0.0


def test_pointDisplacement_OpenFOAM_ayristirabilir(tmp_path):
    """Bozuk sözlük çözücüyü açıklamasız düşürür."""
    import numpy as np

    from coupling_fsi import write_point_displacement as yaz
    d = np.array([[1e-3, 0, 0], [0, 2e-3, 0], [0, 0, 3e-3]])
    s = yaz(tmp_path, "govde", d).read_text()
    assert "FoamFile" in s and "pointVectorField" in s
    assert "dimensions      [0 1 0 0 0 0 0];" in s, "yer değiştirme boyutu yanlış"
    assert "nonuniform List<vector>" in s
    # Uzak alan SABIT: deformasyon disari tasmamali.
    for y in ("inlet", "outlet", "top", "bottom", "front", "back"):
        assert y in s
    # Liste uzunlugu nokta sayisiyla ESLESMELI (OpenFOAM sikica denetler).
    satir = s.splitlines()
    i = satir.index("nonuniform List<vector>".join(["        value           ", ""]).rstrip()) \
        if False else next(j for j, L in enumerate(satir) if "nonuniform" in L)
    assert satir[i + 1].strip() == "3", "liste uzunluğu nokta sayısıyla uyuşmuyor"
    assert satir[i + 2].strip() == "("


def test_YENIDEN_COZUM_ag_hareketi_yokken_SESSIZCE_kosmaz(tmp_path):
    """KURAL: kuplaj turu hareketsiz bir ağda sessizce koşamaz.

    `run_cfd_yeniden` ağı KORUR ve yalnız hareket ettirir — her turda yeniden
    örmek hem pahalıdır hem de yüzey düğüm numaralandırmasını değiştirip
    taşıma operatörünü geçersiz kılar. Ama ön koşul (dynamicMeshDict +
    0/pointDisplacement) yoksa sessizce hareketsiz çözmek, kuplaj turunu fark
    edilmeden TEK YÖNLÜ yapar: sonuç "yakınsadı" der ve yanlıştır.
    """
    import pytest

    from analysis.openfoam_runner import run_cfd_yeniden

    case = tmp_path / "vaka"
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text("startFrom latestTime;\n")
    with pytest.raises(FileNotFoundError) as e:
        run_cfd_yeniden(case)
    assert "dynamicMeshDict" in str(e.value)
    assert "pointDisplacement" in str(e.value)
    assert "tek-yönlü" in str(e.value), "gerekçe eylem planı üretmiyor"


def test_FSI_surucusu_eksik_parcayi_ADIYLA_soyluyor():
    # map_fn, CFD yeniden-cozumu olmadan donerse "yakinsadi" der ve bu sahte
    # kesinliktir. Eksik varsa ACIKCA dusmeli.
    import fsi_surucu
    src = __import__("pathlib").Path(fsi_surucu.__file__).read_text(encoding="utf-8")
    assert "NotImplementedError" in src
    assert "run_cfd_yeniden" in src


def test_SABIT_HARITA_yakinsamasi_yakalaniyor():
    """KURAL: "yakınsadı" tek başına iki-yönlü kuplajın KANITI DEĞİLDİR.

    map_fn girdiden BAĞIMSIZ aynı değeri döndürüyorsa (kuplaj fiilen tek
    yönlüyse) artık dizisi cebirsel olarak ZORUNLU şu şekli alır:
        ω₀ = 0,5           → r₁ = 0,5·r₀   (tam yarılanma)
        Aitken sabit haritada ω₁ = 1,0 → r₂ = 0 (TAM sıfır)

    ÖLÇÜLDÜ (2026-08-21, fsi_kiris — ilk gerçek kuplaj turu):
        r = 5,761e-06 → 2,880e-06 → 0,000e+00 ,  ω = 0,500 → 1,000
    İmzanın birebir kendisi. Fiziksel sebep meşruydu (6 mm alüminyum kiriş
    20 m/s'de 3 µm sehim yapıyor, basınç alanı ölçülebilir biçimde
    değişmiyor) ama o koşu iki-yönlü kuplajı SINAMAZ — yalnızca çökmediğini
    gösterir. "✅ YAKINSADI" demek tek-yönlü bir hesabı iki-yönlü gibi
    göstermek olurdu.
    """
    import numpy as np

    from fsi_twoway import partitioned_fsi

    hedef = np.array([1e-3, -2e-3, 5e-4])

    def sabit_map(_x):
        return hedef            # girdiye YANIT VERMIYOR

    _x, bilgi = partitioned_fsi(sabit_map, np.zeros(3), tol=1e-12,
                                max_iter=10, aitken=True)
    r = bilgi["res_history"]
    # Imzanin gercekten olustugunu once DOGRULA, sonra dedektoru sina
    assert abs(r[1] - 0.5 * r[0]) < 1e-9 * r[0], "yarilanma imzasi olusmadi"
    assert r[-1] == 0.0
    assert bilgi["omega_history"][:2] == [0.5, 1.0]

    # Ve surucudeki dedektor bu imzayi taniyor olmali
    src = __import__("pathlib").Path("fsi_surucu.py").read_text(encoding="utf-8")
    assert "_sabit_harita" in src and "SAHTE YAKINSAMA" in src
    assert "yakinsadi and not _sabit_harita" in src, (
        "sahte yakinsama 'yakinsadi' alanini hala True birakiyor")


def test_sabit_harita_dedektoru_TAM_ESITLIGE_dayanmiyor():
    """KURAL: imza denetimi sonlu-hassasiyet gerçeğine dayanmalı.

    İlk sürüm iki TAM EŞİTLİK kullanıyordu ve ikisi de GERÇEK veride yanlış
    negatif verdi (ölçüldü 2026-08-21, fsi_esnek):
      * `r[-1] == 0.0` — gerçek artık 2,5005e-09 çıktı (başlangıcın 6,7e-06
        katı, yani yanıt fiilen yok) ama tam sıfır değildi.
      * `omega[:2] == [0.5, 1.0]` — Aitken 0,9999973 üretti, tam 1,0 değil.
    Kırılgan karşılaştırma dedektörün kendisini körleştiriyordu.
    """
    # AST ile denetlenir, METINLE degil: ilk surum kaynak metninde
    # "== [0.5, 1.0]" ariyordu ve bunu DUZELTMEYI ACIKLAYAN YORUMDA buldu —
    # yanlis pozitif. Yorum kod degildir; karsilastirma dugumlerine bakilir.
    import ast
    from pathlib import Path as _P

    src = _P("fsi_surucu.py").read_text(encoding="utf-8")
    agac = ast.parse(src)
    _atama = next(n for n in ast.walk(agac)
                  if isinstance(n, ast.Assign)
                  and any(getattr(t, "id", "") == "_sabit_harita" for t in n.targets))
    for c in ast.walk(_atama):
        if isinstance(c, ast.Compare) and any(isinstance(o, ast.Eq) for o in c.ops):
            raise AssertionError(
                f"imza denetiminde TAM ESITLIK var: {ast.unparse(c)}")
    # SAYI BICIMI PINLENMEZ: ast.unparse `1e-4`'u `0.0001` yazar; metinde
    # "1e-4" aramak ucuncu kirilganlik olurdu. Aranan YAPI: son artigin
    # BASLANGICA GORELI karsilastirilmasi ve omega'nin TOLERANSLA denetlenmesi.
    _kod = ast.unparse(_atama)
    assert "_r[-1] <" in _kod and "_r[0]" in _kod, "göreli artık eşiği yok"
    assert "omega_history" in _kod and "abs(" in _kod, "omega toleransı yok"

    # GERCEK olculen dizi imzayi TASIYOR olmali
    r = [3.710978243208484e-04, 1.855484116744775e-04, 2.5005072972108066e-09]
    om = [0.5, 0.9999973026483958]
    assert abs(r[1] - 0.5 * r[0]) < 1e-3 * r[0]
    assert r[-1] < 1e-4 * r[0]
    assert abs(om[0] - 0.5) < 1e-9 and abs(om[1] - 1.0) < 1e-3
