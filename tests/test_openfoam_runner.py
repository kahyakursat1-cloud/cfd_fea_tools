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
    # BU TEST ESKI SOZDIZIMINI PINLIYORDU ve gecerken OZELLIK CALISMIYORDU:
    # `dynamicMotionSolverFvMesh` OF 9/.com bicimidir, OF 11 onu SESSIZCE yok
    # sayar (hata yok, ag statik kurulur, arac donus kodu 0 verir). Test yesil,
    # ag hareketsizdi. Olculdu 2026-08-21; artik OF 11 bicimi araniyor.
    assert "mover" in dm and "motionSolver" in dm
    assert "dynamicFvMesh" not in dm, "OF 9 bicimi geri geldi"
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


def test_controldict_yamasi_SUTUN_HIZALI_bicimde_de_uygulaniyor(tmp_path):
    r"""KURAL: yama, OpenFOAM'ın KENDİ yazdığı biçimde uygulanmalı.

    Eski desenler TEK boşluk varsayıyordu (r"startFrom \w+;") ama OpenFOAM
    sözlükleri SÜTUN HİZALI yazılır ("startFrom       startTime;"). Sonuç:
    yama deponun kendi ürettiği controlDict'lerde HİÇ TUTMUYOR, sessizce
    hiçbir şey yapmıyor ve çağıran yamandığını sanıyordu.

    ÖLÇÜLDÜ (2026-08-21, fsi_kiris): `start_from="latestTime"` istendi, dosya
    `startTime` kaldı, foamRun hareketli ağı ATIP sıfırdan koştu (log: "Time =
    1s") ve dönüş kodu 0 verdi. Kuplaj turunun tüm amacı sessizce boşa gitti.
    """
    import re

    import pytest

    from analysis.openfoam_runner import controldict_yamala

    case = tmp_path / "vaka"
    (case / "system").mkdir(parents=True)
    cd = case / "system" / "controlDict"
    # OpenFOAM'in gercek bicimi: sutun hizali
    cd.write_text("application     foamRun;\n"
                  "startFrom       startTime;\n"
                  "startTime       0;\n"
                  "stopAt          endTime;\n"
                  "endTime         300;\n", encoding="utf-8")

    controldict_yamala(case, start_from="latestTime", end_time=420)
    t = cd.read_text(encoding="utf-8")
    assert re.search(r"startFrom\s+latestTime;", t), "startFrom yamanmadı"
    assert re.search(r"endTime\s+420;", t), "endTime yamanmadı"

    # DOGRULAMA da baglanir: desen tutmazsa SESSIZCE gecmemeli
    bozuk = tmp_path / "bozuk"
    (bozuk / "system").mkdir(parents=True)
    (bozuk / "system" / "controlDict").write_text("bosluk yok\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="YAZILAMADI"):
        controldict_yamala(bozuk, start_from="latestTime")


def test_yeniden_cozum_ILERLEMEYI_denetliyor():
    # Donus kodu 0 yetmez: cozum ilerlemediyse "ok" DENMEZ. Ilk surum tam da
    # bunu yapti ve hareketli ag atilmis bir kosuyu basarili raporladi.
    import inspect

    from analysis.openfoam_runner import run_cfd_yeniden
    src = inspect.getsource(run_cfd_yeniden)
    assert "COZUM ILERLEMEDI" in src
    assert "sonra <= son" in src


def test_hareket_adimi_YAZMA_ARALIGINI_da_yamaliyor(tmp_path):
    """KURAL: hareket adımı writeInterval'ı 1'e çekmeli.

    ÖLÇÜLDÜ (2026-08-21): movingMesh çözücüsü bir adım koştu (Time = 701) ama
    `writeInterval 100` olduğu için HİÇBİR ŞEY yazmadı — ağ hareket etse bile
    sonuç diske düşmez ve kapı haklı olarak "AG HAREKET ETMEDI" der. Hareket
    adımı tek adımdır; yazma aralığı 1 olmak zorunda.
    """
    import re

    from analysis.openfoam_runner import controldict_yamala

    case = tmp_path / "vaka"
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text(
        "startFrom       startTime;\nendTime         300;\n"
        "writeInterval   100;\n", encoding="utf-8")
    controldict_yamala(case, write_interval=1)
    assert re.search(r"writeInterval\s+1;",
                     (case / "system" / "controlDict").read_text(encoding="utf-8"))


def test_hareket_adimi_KULLANIMDAN_KALKMIS_araci_kullanmiyor():
    # moveDynamicMesh bu OpenFOAM surumunde superseded: log'un kendisi
    # "replaced by the more general movingMesh solver module executed by the
    # foamRun application" diyor. Eski cagri donus kodu 0 verip HICBIR SEY
    # yapmiyordu — sessiz basarisizligin ders kitabi ornegi.
    import inspect

    from analysis.openfoam_runner import run_cfd_yeniden
    src = inspect.getsource(run_cfd_yeniden)
    assert "foamRun -solver movingMesh" in src
    assert "-noFunctionObjects" in src, "forceCoeffs U/p isteyip dusuruyor"


def test_ag_hareketi_OF11_sozdizimi_ve_COZUCU_girdileri(tmp_path):
    """KURAL: ağ hareketi kurulumu OF 11 biçiminde olmalı ve gerekli lineer
    çözücüleri de kurmalı.

    ÖLÇÜLDÜ (2026-08-21, fsi_kiris — dokuz engel elendikten sonra):
      * `dynamicFvMesh dynamicMotionSolverFvMesh;` OF 9/.com biçimidir ve OF 11
        onu SESSİZCE YOK SAYAR: hata yok, uyarı yok, ağ statik kurulur, araç
        dönüş kodu 0 verir. Log'da "Selecting solver movingMesh" görünür ama
        hareket çözücüsünün seçildiğine dair TEK SATIR yoktur.
      * `displacementLaplacian` fvSolution'da `cellDisplacement` ister
        ("keyword cellDisplacement is undefined").
      * Hareketli ağda çözüm ayrıca `pcorr` ister (süreklilikle tutarlı ağ
        akısı için basınç düzeltmesi).
    Üçü de aynı kurulumun parçası; birini yazıp ötekini unutmak bir sonraki
    koşuda düşürür — bu yüzden hepsi TEK yerde kurulur ve burada bağlanır.
    """
    from analysis.openfoam_runner import _write_mesh_motion

    case = tmp_path / "vaka"
    (case / "constant").mkdir(parents=True)
    (case / "0").mkdir()
    (case / "system").mkdir()
    (case / "system" / "fvSolution").write_text(
        "solvers\n{\n    p\n    {\n        solver PCG;\n    }\n}\n",
        encoding="utf-8")

    _write_mesh_motion(case, "kiris")

    dmd = (case / "constant" / "dynamicMeshDict").read_text(encoding="utf-8")
    assert "mover" in dmd and "type            motionSolver;" in dmd
    assert "dynamicFvMesh" not in dmd, "OF 9 biçimi geri geldi (OF 11 yok sayar)"
    assert "libfvMeshMovers.so" in dmd
    assert "1(kiris)" in dmd, "yama listesi OF 11'de sayı-önekli olmalı"

    fv = (case / "system" / "fvSolution").read_text(encoding="utf-8")
    assert "cellDisplacement" in fv
    assert "pcorr" in fv


def test_build_case_ag_hareketini_TEK_SEFERDE_dogru_kuruyor(tmp_path):
    """KURAL: `mesh_motion=True` ile kurulan vaka, EK MÜDAHALE OLMADAN çözülebilir
    olmalı.

    İki kusur bu özelliği bugüne kadar tümüyle çalışmaz halde tutmuştu ve ikisi
    de ancak ağ-hareketli bir vaka GERÇEKTEN çözülünce göründü (2026-08-21):

      * `pointDisplacement` `volVectorField` olarak yazılıyordu; alan ağ
        NOKTALARINDA tanımlıdır, çözücü "unexpected class name volVectorField
        expected pointVectorField" ile düşer. Kusur gizliydi çünkü kuplaj
        yolunda `write_point_displacement` dosyayı doğru sınıfla üzerine
        yazıyordu.
      * `_write_mesh_motion` fvSolution'a `cellDisplacement`/`pcorr` ekliyor
        ama `_write_fv_solution`'DAN ÖNCE çağrılıyordu; ekleme hemen ardından
        ÜZERİNE YAZILIYORDU ("keyword cellDisplacement is undefined"). Yama
        doğruydu, SIRASI yanlıştı.
    """
    import numpy as np

    from analysis.openfoam_runner import CFDCase, build_case

    stl = tmp_path / "levha.stl"
    trimesh.creation.box(extents=[0.3, 0.04, 0.0025]).export(stl)
    a = np.deg2rad(10.0)
    case = CFDCase(name="hareketli", stl_path=stl, velocity=30.0,
                   flow_direction=(float(np.cos(a)), 0.0, float(np.sin(a))),
                   refinement_min=1, refinement_max=2,
                   max_global_cells=50_000, n_layers=0, mesh_motion=True)
    cd = build_case(case, tmp_path / "out")

    pd = (cd / "0" / "pointDisplacement").read_text(encoding="utf-8")
    assert "pointVectorField" in pd
    assert "volVectorField" not in pd, "yanlış alan sınıfı geri geldi"

    fv = (cd / "system" / "fvSolution").read_text(encoding="utf-8")
    assert "cellDisplacement" in fv, "ağ hareketi çözücüsü fvSolution'da yok"
    assert "pcorr" in fv, "hareketli ağ basınç düzeltmesi yok"

    dmd = (cd / "constant" / "dynamicMeshDict").read_text(encoding="utf-8")
    assert "mover" in dmd and "dynamicFvMesh" not in dmd
