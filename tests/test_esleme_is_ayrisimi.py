"""Arayüz işi: ÜRETİMDEKİ eşleme mi kaybediyor, terk edilmiş şema mı?

DIŞ HAKEM BU DEPONUN EN CİDDİ FSI PROBLEMİ OLARAK ``arayüz işi korunumu''nu
işaretledi ve haklı bir sayıya dayandı: kayıtta en kötü iş artığı %102,64.
Kayıt bunu ``izdüşüm kaymasına'' bağlıyordu.

ÖLÇÜLDÜ VE ATIF YANLIŞTI. `arayuz_isi_hatasi` iki tensörü kıyaslıyor:
düğüm momenti (ÜRETİMDEKİ korunumlu şema, CFD yüzlerinden) ve yüz momenti
(TERK EDİLMİŞ tutarlı şema, FEA yüzünde yeniden integre edilmiş). Yani
metrik şemaları kıyaslıyor, eşlemeyi ölçmüyor. Aynı vakada terk edilmiş
şemanın toplam kuvvetinin İŞARETİ bile ters çıkabiliyor.

Doğru referans CFD tarafıdır ve orada bir KİMLİK var. Baryentrik ağırlıklar
doğrusal alanları birebir ürettiği için:

    T_düğüm - T_cfd  ==  Σ_f dF_f ⊗ δ_f ,    δ_f = Σ_k w_k x_k - x_cfd,f

yani eşlemenin iş kaybı TAM OLARAK izdüşüm sapmasıdır. Turek--Hron FSI1'de
ölçüldü: eşleme payı %0,000000, yüzey payı %0,6457 --- toplamın tamamı
terk edilmiş şemadan geliyor.

BUNUN SONUCU BİR TASARIM KURALIDIR, ARAŞTIRMA KONUSU DEĞİL: eşlemenin iş
kaybını azaltmak için mortar/RBF'ye geçmek gerekmez; alıcı yüzeyin verici
yüzeyi çözmesi yeter. δ ölçülebilir ve kuplaj koşulmadan önce bakılabilir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

VTK = KOK / "turek_hron_cfd1_case" / "VTK" / "bayrak" / "bayrak_445.vtk"


def _kos(stl: Path):
    from coupling_fsi import cfd_pressure_to_fea_loads
    return cfd_pressure_to_fea_loads(str(VTK), str(stl), rho=1000.0,
                                     p_is_kinematic=True)


@pytest.fixture(scope="module")
def ince(tmp_path_factory):
    """İNCE alıcı yüzey: CFD'yi rahatça çözüyor (9140 üçgen / 292 yüz)."""
    if not VTK.exists():
        pytest.skip("CFD1 VTK'sı yok (python experiments/turek_hron_cfd1.py)")
    from turek_hron_fsi1 import _bayrak_stl
    yol = tmp_path_factory.mktemp("ince") / "bayrak.stl"
    _bayrak_stl(yol, 160)
    return _kos(yol)


@pytest.fixture(scope="module")
def kaba(tmp_path_factory):
    """KABA alıcı yüzey: CFD'den çok daha az üçgen --- δ'nın büyümesi
    BEKLENİR ve ölçütün yanlış-negatif kapısı budur."""
    if not VTK.exists():
        pytest.skip("CFD1 VTK'sı yok")
    from turek_hron_fsi1 import _bayrak_stl
    yol = tmp_path_factory.mktemp("kaba") / "bayrak.stl"
    _bayrak_stl(yol, 2)
    return _kos(yol)


def test_KIMLIK_TUTUYOR(ince):
    """Açıklamanın kendisi sınanır. Kimlik tutmuyorsa 'iş kaybı izdüşüm
    sapmasıdır' cümlesi bir iddia olarak kalır ve kullanılamaz."""
    s = ince["esleme_sapmasi"]
    assert s is not None, "korunumlu şemada sapma kaydı üretilmemiş"
    assert s["kimlik_artigi"] < 1e-12, (
        f"kimlik artığı {s['kimlik_artigi']:.2e} --- 'iş kaybı = izdüşüm "
        "sapması' açıklaması bu veriyle desteklenmiyor. Bu bir CEBIRSEL "
        "ozdesliktir; artik makine hassasiyetinde olmali, 1e-6 gibi gevsek "
        "bir band gercek bir ihlali gizlerdi.")


def test_INCE_YUZEYDE_ESLEME_PAYI_IHMAL_EDILEBILIR(ince):
    """Asıl düzeltme. Kayıttaki iş artığının tamamı yüzey payından
    geliyorsa, üretimdeki eşleme suçlanamaz."""
    s = ince["esleme_sapmasi"]
    assert s["esleme_isi_artigi"] < 1e-4, (
        f"eşleme payı %{100 * s['esleme_isi_artigi']:.4f}")
    # Ve toplam artik GERCEKTEN sifir degil --- yoksa test hicbir sey
    # ayirt etmez; ayrisimin anlami toplamin BASKA bir yerden gelmesidir.
    assert ince["arayuz_isi_hatasi"] > 10 * s["esleme_isi_artigi"], (
        "toplam iş artığı da sıfıra yakın; bu vaka ayrışımı göstermiyor")
    assert s["yuzey_isi_artigi"] > 0.9 * ince["arayuz_isi_hatasi"]


def test_KABA_YUZEYDE_ESLEME_PAYI_BUYUYOR(kaba, ince):
    """YANLIŞ-NEGATİF KAPISI. 'Eşleme payı ihmal edilebilir' cümlesi
    KOŞULLUDUR: alıcı yüzey vericiyi çözdüğünde. Çözmediğinde δ büyür ve
    ölçüt bunu GÖRMELİDİR --- görmezse ölçüt kör demektir."""
    sk, si = kaba["esleme_sapmasi"], ince["esleme_sapmasi"]
    assert sk["en_buyuk_olcekli"] > si["en_buyuk_olcekli"], (
        "kaba yüzeyde izdüşüm sapması büyümüyor; ölçüt çözünürlüğe "
        "duyarsız")
    assert sk["esleme_isi_artigi"] > 100 * max(si["esleme_isi_artigi"], 1e-12)


def test_KIMLIK_KABA_YUZEYDE_de_TUTUYOR(kaba):
    """Kimlik bir cebirsel özdeşliktir; yalnız iyi vakada tutuyorsa
    tesadüftür."""
    assert kaba["esleme_sapmasi"]["kimlik_artigi"] < 1e-12


def test_DELTA_OLCEKLI_OLARAK_RAPORLANIYOR(ince):
    """Mutlak δ [m] geometri boyutuna bağlıdır ve vakalar arası
    kıyaslanamaz; FEA yüz ölçeğine bölünmüş hâli kıyaslanabilir."""
    s = ince["esleme_sapmasi"]
    for alan in ("ortalama_m", "en_buyuk_m", "fea_yuz_olcegi_m",
                 "ortalama_olcekli", "en_buyuk_olcekli"):
        assert alan in s
    assert s["fea_yuz_olcegi_m"] > 0
    assert s["en_buyuk_olcekli"] == pytest.approx(
        s["en_buyuk_m"] / s["fea_yuz_olcegi_m"], rel=1e-3, abs=1e-4)


def test_AYRISIM_KAYITTA_ACIKLANIYOR(ince):
    """Sayı doğru olsa bile, hangi payın üretimi ilgilendirdiği yazılı
    olmazsa okur yine toplamı üretime yazar --- hakemin yaptığı buydu."""
    s = ince["esleme_sapmasi"]
    assert "ESKI semanin" in s["_ayrisim"]
    assert "uretim yolunda" in s["_ayrisim"]
    assert "inceltmek" in s["_kimlik"]


def test_TOPLAM_ESLEME_ARTI_YUZEY_ile_TUTARLI(ince):
    """Ayrışım bir toplam iddiasıdır ve üçgen eşitsizliğine uymalı;
    uymuyorsa parçalar aynı büyüklüğün parçaları değildir."""
    s = ince["esleme_sapmasi"]
    toplam = ince["arayuz_isi_hatasi"]
    assert toplam <= s["esleme_isi_artigi"] + s["yuzey_isi_artigi"] + 1e-9
    assert np.isfinite(toplam)


# ─────────────────────────────────────────────────────────────────────────
# SENTETIK KAPSAM: bu dosya bir kez SESSIZCE devre disi kaldi
# ─────────────────────────────────────────────────────────────────────────
# Yukaridaki testlerin hepsi CFD1 vakasinin VTK'sina bagli ve o dosya
# BASKA bir betigin (turek_hron_fsi1) yan urunu. CFD1 yeniden kosulunca
# vaka dizini sifirdan kuruldu, VTK silindi ve YEDI test birden sessizce
# atlandi --- suit "hepsi gecti" dedi, hicbir sey sinanmadi.
#
# Kimlik ise SAF CEBIRDIR: baryentrik agirliklar dogrusal alanlari birebir
# uretir. Onu sinamak icin Turek-Hron'a gerek yok. Asagidaki testler
# sentetik girdiyle KOSAR ve hicbir kosulda atlanmaz.

def _sentetik_vtk(yol: Path, n: int = 12) -> Path:
    """n x n dortgenden olusan duz bir yama --- basinc dogrusal degisir."""
    import numpy as np
    xs = np.linspace(0.0, 1.0, n + 1)
    ys = np.linspace(0.0, 1.0, n + 1)
    P = [(x, y, 0.0) for x in xs for y in ys]
    idx = lambda i, j: i * (n + 1) + j          # noqa: E731
    poly = [(idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1))
            for i in range(n) for j in range(n)]
    p = [0.5 + 0.3 * (i + 0.5) / n for i in range(n) for _ in range(n)]
    s = ["# vtk DataFile Version 2.0", "sentetik", "ASCII",
         "DATASET POLYDATA", f"POINTS {len(P)} float"]
    s += [f"{a} {b} {c}" for a, b, c in P]
    s.append(f"POLYGONS {len(poly)} {5 * len(poly)}")
    s += ["4 " + " ".join(str(k) for k in q) for q in poly]
    s += [f"CELL_DATA {len(poly)}", "FIELD attributes 1",
          f"p 1 {len(poly)} float"] + [f"{v}" for v in p]
    yol.write_text("\n".join(s) + "\n", encoding="utf-8")
    return yol


def _sentetik_stl(yol: Path, n: int) -> Path:
    """Aynı düzlemi n x n karede üçgenleyen alıcı yüzey."""
    import numpy as np
    import trimesh
    xs = np.linspace(0.0, 1.0, n + 1)
    V, F = [], []
    for i in range(n + 1):
        for j in range(n + 1):
            V.append((xs[i], xs[j], 0.0))
    for i in range(n):
        for j in range(n):
            a, b = i * (n + 1) + j, (i + 1) * (n + 1) + j
            F += [[a, b, b + 1], [a, b + 1, a + 1]]
    trimesh.Trimesh(vertices=np.array(V, float), faces=np.array(F, int),
                    process=False).export(yol)
    return yol


def _sentetik_kos(tmp: Path, n_cfd: int, n_fea: int):
    from coupling_fsi import cfd_pressure_to_fea_loads
    v = _sentetik_vtk(tmp / f"p{n_cfd}.vtk", n_cfd)
    s = _sentetik_stl(tmp / f"s{n_fea}.stl", n_fea)
    return cfd_pressure_to_fea_loads(str(v), str(s), rho=1.0,
                                     p_is_kinematic=False)


def test_SENTETIK_KIMLIK_TUTUYOR(tmp_path):
    """Dış artefakta bağlı DEĞİL --- her koşuda çalışır."""
    r = _sentetik_kos(tmp_path, 12, 24)
    assert r["status"] == "SUCCESS", r.get("error")
    s = r["esleme_sapmasi"]
    assert s is not None
    assert s["kimlik_artigi"] < 1e-12, (
        f"kimlik artığı {s['kimlik_artigi']:.2e} --- 'iş kaybı = izdüşüm "
        "sapması' özdeşliği sentetik girdide bile tutmuyor")


def test_SENTETIK_KABA_ALICI_ESLEME_PAYINI_BUYUTUYOR(tmp_path):
    """Yanlış-negatif kapısı, dış artefakt olmadan. Alıcı yüzey vericiden
    KABA olduğunda eşleme payı büyümeli; büyümüyorsa ölçüt kördür."""
    ince = _sentetik_kos(tmp_path, 12, 24)["esleme_sapmasi"]
    kaba = _sentetik_kos(tmp_path, 12, 2)["esleme_sapmasi"]
    assert kaba["en_buyuk_olcekli"] > ince["en_buyuk_olcekli"]
    assert kaba["esleme_isi_artigi"] > ince["esleme_isi_artigi"]


def test_BU_DOSYA_SESSIZCE_DEVRE_DISI_KALAMAZ():
    """Yedi testin birden atlandığı hâl bir kez yaşandı ve suit yeşil
    kaldı. En az bir test HER koşuda çalışmalı --- bu test onu bağlar:
    sentetik testler `pytest.skip` içermemeli."""
    import ast
    src = Path(__file__).read_text(encoding="utf-8")
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef) and n.name.startswith(
                "test_SENTETIK"):
            cagri = [c for c in ast.walk(n) if isinstance(c, ast.Call)
                     and getattr(c.func, "attr", "") == "skip"]
            assert not cagri, (
                f"{n.name} atlanabilir; sentetik testler dış artefakta "
                "bağlı olmamalı")
