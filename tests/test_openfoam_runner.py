"""openfoam_runner orphan-önleme + diverjans bekçisi — saf-mantık (WSL çağırmadan)."""
import trimesh

from analysis.openfoam_runner import (
    _OF_BINS,
    CFDCase,
    _wrap_timeout,
    _wsl_kill,
    build_case,
    divergence_in_log,
)


def test_divergence_detector_catches_nan():
    assert divergence_in_log("Solving for Ux, Initial residual = nan, Final") is not None
    assert divergence_in_log("Initial residual = inf") is not None
    assert "exception" in (divergence_in_log("forrtl: Floating point exception") or "")
    assert divergence_in_log("#0  Foam::error::printStack") is not None


def test_divergence_detector_ignores_normal_log():
    # 'bounding' normal mesajdir; saglikli yakinsama diverjans DEGIL → yanlis-pozitif yok
    ok = ("bounding k, min: 0 max: 12 average: 3\n"
          "Solving for Ux, Initial residual = 0.0012, Final residual = 1e-7\n"
          "Solving for omega, Initial residual = 3.4e-05\n")
    assert divergence_in_log(ok) is None


def test_wrap_timeout_wraps_solver():
    # foamRun → WSL-içi GNU timeout ile sarılır (orphan-önleme), binary listelenir
    wrapped, bins = _wrap_timeout("mpirun -np 4 foamRun -parallel", 600)
    assert wrapped.startswith("timeout -k 10 -s TERM 580 ")
    assert "foamRun" in bins and "mpirun" in bins


def test_wrap_timeout_skips_short_cmds():
    # kısa yardımcı (OF binary değil) sarılmaz (komut log-redirect içermez; _step sonra ekler)
    wrapped, bins = _wrap_timeout("checkMesh -allTopology", 120)
    assert wrapped == "checkMesh -allTopology" and bins == []


def test_wrap_timeout_floor():
    # çok küçük tmo'da iç süre tabanı 30 s
    wrapped, _ = _wrap_timeout("blockMesh", 25)
    assert "timeout -k 10 -s TERM 30 " in wrapped


def test_wsl_kill_safe_on_empty():
    # boş liste no-op; istisna fırlatmaz
    assert _wsl_kill([]) is None
    assert "mpirun" in _OF_BINS and "foamRun" in _OF_BINS


def _box_case(tmp_path, **kw):
    stl = tmp_path / "kutu.stl"
    trimesh.creation.box(extents=(0.2, 0.1, 0.1)).export(stl)
    return CFDCase(name="kutu", stl_path=stl, n_processors=1, **kw)


def test_build_case_free_air_bottom_slip(tmp_path):
    case_dir = build_case(_box_case(tmp_path), tmp_path / "out")
    assert "bottom    { type patch;" in (case_dir / "system" / "blockMeshDict").read_text()
    assert "bottom  { type slip; }" in (case_dir / "0" / "U").read_text()


def test_build_case_refinement_regions(tmp_path):
    # Hedefli bölge-refinement: searchableBox geometry'ye + inside-mode refinementRegions'a
    rr = [{"ad": "izBolgesi", "min": (0.1, -0.05, -0.05), "max": (0.4, 0.05, 0.05), "level": 3}]
    case_dir = build_case(_box_case(tmp_path, refinement_regions=rr), tmp_path / "out")
    snappy = (case_dir / "system" / "snappyHexMeshDict").read_text()
    assert "izBolgesi { type searchableBox; min (0.100000 -0.050000 -0.050000)" in snappy
    assert "izBolgesi { mode inside; levels ((1e15 3)); }" in snappy


def test_build_case_no_regions_writes_empty_block(tmp_path):
    snappy = (build_case(_box_case(tmp_path), tmp_path / "out2")
              / "system" / "snappyHexMeshDict").read_text()
    assert "refinementRegions" in snappy and "searchableBox" not in snappy


def test_build_case_ground_plane(tmp_path):
    # Ahmed-tipi zemin: taban wall + noSlip + duvar fonksiyonları; domain tabanı clearance'ta
    case_dir = build_case(_box_case(tmp_path, ground_clearance=0.02), tmp_path / "out")
    bm = (case_dir / "system" / "blockMeshDict").read_text()
    assert "bottom    { type wall;" in bm
    import re
    zs = [float(m.split()[2]) for m in
          re.findall(r"\(\s*([-\d.eE+]+\s+[-\d.eE+]+\s+[-\d.eE+]+)\s*\)", bm)]
    assert abs(min(zs) - (-0.05 - 0.02)) < 1e-6   # gövde zmin=-0.05, clearance 0.02
    assert "bottom  { type noSlip; }" in (case_dir / "0" / "U").read_text()
    assert "kqRWallFunction" in (case_dir / "0" / "k").read_text().split("bottom")[1][:60]
    assert "omegaWallFunction" in (case_dir / "0" / "omega").read_text().split("bottom")[1][:60]
    assert "nutUSpaldingWallFunction" in (case_dir / "0" / "nut").read_text().split("bottom")[1][:60]
    assert "zeroGradient" in (case_dir / "0" / "p").read_text().split("bottom")[1][:60]


def test_katmanli_kosuda_kalite_olcutu_GEVSETILIYOR(tmp_path):
    """Katman istendiğinde tet-ayrışım ölçütü kapatılır ve `relaxed` yazılır.

    ÖLÇÜLDÜ (2026-08-19, küre çapası — log.snappyHexMesh):
      istenen 10 katman → ortalama 0,535 örüldü, hedef kalınlığın %13,9'u
      ekstrüzyon 1360 → 600 / 1728 yüze çürüdü (yalnız %34,7 kapsama)
    Her yinelemede aynı satır: "faces with face-decomposition tet quality
    < 1e-15 : 472". Yani katman eklenince ölçüt düşüyor ve snappy katmanı
    SİLİYOR. `relaxed` alt-sözlüğü hiç olmadığı için gevşetip yeniden deneme
    yolu da kapalıydı.
    """
    case_dir = build_case(_box_case(tmp_path, n_layers=10,
                                    first_layer_thickness=2e-5),
                          tmp_path / "out")
    s = (case_dir / "system" / "snappyHexMeshDict").read_text()
    assert "minTetQuality -1e30;" in s, (
        "tet-ayrışım ölçütü hâlâ sıkı — katman ekleme yanlış pozitifle silinir")
    assert "relaxed" in s and "maxNonOrtho 75;" in s, (
        "`relaxed` alt-sözlüğü yok — snappy gevşetip yeniden deneyemez")
    assert "nRelaxedIter" in s, "`relaxed` bloğu nRelaxedIter olmadan devreye girmez"
    assert "addLayers       true;" in s


def test_katmansiz_kosuda_olcut_SIKI_kaliyor(tmp_path):
    """Gevşetme yalnız katmanlı koşuya ait; katmansız koşular değişmemeli.

    Katmansız koşular bugüne dek sıkı ölçütle sorunsuz üretti; onları da
    gevşetmek, çözülmemiş bir soruna karşılık gerçek bir kalite tavizi olurdu.
    """
    s = (build_case(_box_case(tmp_path), tmp_path / "out")
         / "system" / "snappyHexMeshDict").read_text()
    assert "minTetQuality 1e-15;" in s
    assert "relaxed" not in s
    assert "addLayers       false;" in s


def test_ag_hareketi_ISTENMEDEN_yazilmiyor(tmp_path):
    """Varsayılan kapalı — mevcut koşuların hiçbiri etkilenmemeli."""
    case_dir = build_case(_box_case(tmp_path), tmp_path / "out")
    assert not (case_dir / "constant" / "dynamicMeshDict").exists()
    assert not (case_dir / "0" / "pointDisplacement").exists()


def test_ag_hareketi_2YONLU_FSI_nin_EKSIK_HALKASI(tmp_path):
    """Yapı deformasyonunu akışkan ağına taşıyan dosyalar.

    ÖLÇÜLDÜ (2026-08-19): 2-yönlü FSI'nin eksiği ne çözücü ne kuplaj şemasıydı.
      · `fsi_twoway.partitioned_fsi` (Aitken) DOĞRULANMIŞ ama üretimde tek
        çağıranı YOK — yalnız testlerden çağrılıyor.
      · `coupling_fsi.cfd_pressure_to_fea_loads` (1-yönlü) pipeline.py'de
        ÇALIŞIYOR ama dönüşü yok.
      · Depoda `dynamicMotionSolver` / `pointDisplacement` HİÇ GEÇMİYORDU —
        yani yapının deformasyonu akışkan ağına aktarılamıyordu.
    preCICE eklemek bu parçayı çözmez (onun OpenFOAM adaptörü de hareketli-ağ
    kurulumunu çağırandan ister) ve zaten doğrulanmış kuplaj şemasını
    değiştirirdi.
    """
    case_dir = build_case(_box_case(tmp_path, mesh_motion=True), tmp_path / "out")
    dm = (case_dir / "constant" / "dynamicMeshDict").read_text()
    assert "dynamicMotionSolverFvMesh" in dm
    assert "displacementLaplacian" in dm
    # Ters-mesafe yayilimi hareketi cisme yakin tutar; uzak alan ag kalitesi korunur.
    assert "inverseDistance" in dm

    pd = (case_dir / "0" / "pointDisplacement").read_text()
    assert "dimensions      [0 1 0 0 0 0 0];" in pd, "yer değiştirme boyutu yanlış"
    # UZAK ALAN SABIT: deformasyon disari tasmamali.
    for yama in ("inlet", "outlet", "top", "front", "back"):
        assert yama in pd, f"{yama} sınır koşulu yazılmamış"
    # GOVDE fixedValue: degeri DISARIDAN (FEA'dan) yazilacak.
    assert "kutu" in pd, "gövde yaması pointDisplacement'ta yok"
    assert pd.count("fixedValue") >= 7


def test_ag_hareketi_dosyalari_OpenFOAM_basligi_tasiyor(tmp_path):
    """Başlıksız dosya OpenFOAM tarafından ayrıştırılamaz — sessizce düşer."""
    case_dir = build_case(_box_case(tmp_path, mesh_motion=True), tmp_path / "out")
    for p in (case_dir / "constant" / "dynamicMeshDict",
              case_dir / "0" / "pointDisplacement"):
        t = p.read_text()
        assert "FoamFile" in t and "version" in t, f"{p.name} başlıksız"
