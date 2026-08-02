"""Eski yolun KURULUMU da iyileştirildi — kapılar yargılıyordu, kurulum değişmiyordu.

ÖLÇÜLDÜ (2026-08-02, kütüphanedeki BEŞ şablonun BEŞİNDE, üç mesh ayarının
ÜÇÜNDE): firar kenarı 0.05–0.65 hücre. Sebep bütçe değildi — en ince ayar
5.000.000 tavanın yalnız 453.962'sini kullanıyordu. `nx = min(base, 150)` sabit
tavanı, 30L×10L×10L domainde arka plan hücresini 369–984 mm'de tutuyordu.

Bütçe-farkındalıklı arka planla yüzey hücresi 1.8–2.5 kat inceldi ve TE
0.80–1.19 hücreye çıktı — ama hedef ≥6, yani BU YOL İNCE KENARI ÇÖZEMİYOR.
Söylenmesi gereken şey budur; test hem iyileştirmeyi hem SINIRIN kabulünü bağlar.
"""
import re

from aircraft_geometry import AircraftLibrary
from mesh_generator import MeshGenerator

LIB = AircraftLibrary()


def _nx(ac, ms):
    bm = MeshGenerator(ac, mesh_size=ms).generate_blockmeshdict()
    m = re.search(r"hex \(0 1 2 3 4 5 6 7\) \((\d+) (\d+) (\d+)\)", bm)
    return tuple(int(x) for x in m.groups())


def _eski_nx(ms):
    scale = max(0.01, min(0.05, ms))
    return min(int(60 * (0.05 / scale) ** 0.5), 150)


def test_arka_plan_ESKISINDEN_KABA_olamaz():
    """Değişiklik hiçbir koşuyu kötüleştirmemeli."""
    for ad in LIB.template_adlari():
        ac = LIB.get_template(ad)()
        for ms in (0.05, 0.025, 0.012):
            nx, ny, nz = _nx(ac, ms)
            assert nx >= _eski_nx(ms), (ad, ms)
            assert ny >= min(int(_eski_nx(ms) * 0.5), 75)


def test_arka_plan_GERCEKTEN_incelesti():
    """İlk denemede istenen hücre ESKİ hücreden türetilmişti ve
    `arka_plan_hucre_boyu` yalnız kabalaştırdığı için kazanç SIFIR çıkmıştı."""
    ac = LIB.get_template("mini_hawk")()
    nx, _, _ = _nx(ac, 0.012)
    assert nx > _eski_nx(0.012) * 1.5, "geometriden türetme yapılmamış"


def test_butce_TEK_KAYNAK():
    """blockMesh çözünürlüğü ile snappy tavanı aynı sayıdan gelmeli."""
    g = MeshGenerator(LIB.get_template("mini_hawk")(), mesh_size=0.012)
    snappy = g.generate_snappyhexmeshdict()
    assert f"maxGlobalCells      {int(g.max_global_cells)};" in snappy


def test_arka_plan_butceyi_TASMIYOR():
    ac = LIB.get_template("high_altitude_platform")()
    g = MeshGenerator(ac, mesh_size=0.012)
    nx, ny, nz = _nx(ac, 0.012)
    assert nx * ny * nz < g.max_global_cells


def test_UYGULANAMAZ_tavsiye_verilmiyor():
    """Kanonik hüküm 'ref_bump=N ile ulaşılır' der; ref_bump bu yolda YOK.
    Uygulanamayan tavsiye, hiç vermemekten kötüdür."""
    import inspect

    import simulation_runner as sr
    src = inspect.getsource(sr._ince_ozellik_onhukmu)
    assert "bu_yolda_uygulanabilir" in src
    assert "ULAŞAMAZ" in src and "app_analyzer.py" in src


def test_on_hukum_SONUCA_giriyor():
    """Terminale basılan uyarı kaybolur; Cl/L-D okuyan onu görmeli."""
    import inspect

    import simulation_runner as sr
    src = inspect.getsource(sr.SimulationRunner._extract_results)
    assert '"ince_ozellik"' in src
    calis = inspect.getsource(sr.SimulationRunner.run_simulation)
    assert "_ince_ozellik_onhukmu(" in calis
    assert calis.index("_ince_ozellik_onhukmu(") < calis.index("blockMesh")
