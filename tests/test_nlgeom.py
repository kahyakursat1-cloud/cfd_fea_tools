"""NLGEOM: yazıcı doğru kart basıyor mu, ve kart GERÇEKTEN çalışıyor mu?

Bu iki soru AYRIDIR ve ikisi de sorulmalı. Bir bayrağı yazmak kolaydır ve
sessizce hiçbir şey yapmayabilir: CalculiX kartı kabul eder, koşu düşmez,
sonuç lineer kalır. Bu depoda ``eklendi'' ile ``çalışıyor'' aynı şey
değildir.

DOĞRULAMA ÜÇ AYAKLIDIR (`experiments/nlgeom_dogrulama.py`) --- biri eksikse
doğrulama değildir:
  1. Küçük yükte lineere İNDİRGENİYOR mu? (indirgenmiyorsa yetenek değil
     kusur eklenmiştir)
  2. Büyük yükte ayrışıyor mu ve DOĞRU YÖNDE mi?
  3. Ayrışma bir REFERANSA yaklaşıyor mu? (yalnız ``farklı çıktı'' demek,
     yanlış bir farkı doğrulama sayardı)

BİR KUSUR ÖLÇÜM SIRASINDA ÇIKTI ve doğrulamayı geçersiz kılacaktı: ilk
sürüm C3D4 (lineer tet) ağı kullandı ve α=1'de sehim 0,041 verdi --- beklenen
0,30. Sekiz kat sapma NLGEOM'dan değil, LİNEER TETİN EĞİLMEDE
KİLİTLENMESİNDEN geliyordu. O ağla ``NLGEOM neredeyse hiçbir şey
değiştirmiyor'' diye yanlış bir doğrulama üretilirdi.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "nlgeom_dogrulama.json"


def _kucuk_case(nlgeom: bool, tip: str = "STATIC"):
    from analysis.calculix_writer import FEACase, FEAMaterial, FixedBC
    from analysis.tet_mesher import TetMesh
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    mesh = TetMesh(points=P, tets=np.array([[0, 1, 2, 3]], int),
                   surface_tris=np.empty((0, 3), int),
                   msh_path=Path("x.msh"), element_type="C3D4")
    return FEACase(
        name="t", mesh=mesh,
        material=FEAMaterial(name="m", youngs_modulus_pa=70e9,
                             poisson_ratio=0.33, density_kg_m3=2700.0),
        fixed_bcs=[FixedBC(node_ids=np.array([1]))],
        analysis_type=tip, nlgeom=nlgeom)


def test_VARSAYILAN_KAPALI_ve_inp_degismiyor(tmp_path):
    """Varsayılan açık olsaydı yayımlanmış her yapısal sonuç sessizce
    değişirdi --- yetenek eklemek, sonucu değiştirmek demek değildir."""
    from analysis.calculix_writer import write_inp
    assert _kucuk_case(False).nlgeom is False
    t = write_inp(_kucuk_case(False), tmp_path / "a").read_text(encoding="utf-8")
    assert "*STEP\n" in t and "NLGEOM" not in t


def test_ACIKKEN_kart_yaziliyor_ve_YUK_ARTIMLI(tmp_path):
    from analysis.calculix_writer import write_inp
    t = write_inp(_kucuk_case(True), tmp_path / "b").read_text(encoding="utf-8")
    assert "*STEP, NLGEOM" in t
    # Buyuk yer-degistirmede denge tek adimda yakinsamak zorunda degil;
    # artim satiri OLMAZSA CalculiX tek adim dener.
    satirlar = t.splitlines()
    i = satirlar.index("*STATIC")
    assert "," in satirlar[i + 1], "yük artım satırı yok"


def test_FREQUENCY_ve_BUCKLE_da_SESSIZCE_gecilmiyor(tmp_path):
    """NLGEOM yalnız STATIC'te anlamlıdır. İstenip uygulanamıyorsa DOSYAYA
    yazılmalı --- sessiz geçiş, okuyucuya yapılmayan bir şeyi yapılmış gibi
    gösterir."""
    from analysis.calculix_writer import write_inp
    for tip in ("FREQUENCY", "BUCKLE"):
        t = write_inp(_kucuk_case(True, tip),
                      tmp_path / tip).read_text(encoding="utf-8")
        assert "*STEP, NLGEOM" not in t
        assert "NLGEOM İSTENDİ" in t and "UYGULANMAZ" in t


def test_ELASTIKA_REFERANSI_kendi_icinde_DOGRULANDI():
    """Referans yanlışsa doğrulama da yanlış olur --- referans önce sınanır."""
    from nlgeom_dogrulama import elastika, lineer_sehim
    # (i) KUCUK-ALFA LIMITI lineere inmeli
    a = 0.001
    e = elastika(a)["delta_y_bolu_L"]
    assert abs(e - lineer_sehim(a)) / lineer_sehim(a) < 1e-4
    # (ii) ADIM SAYISINDAN BAGIMSIZ olmali
    kaba = elastika(3.0, n=2000)["delta_y_bolu_L"]
    ince = elastika(3.0, n=20000)["delta_y_bolu_L"]
    assert abs(kaba - ince) / ince < 1e-5, "elastika çözücüsü yakınsamamış"
    # (iii) BUYUK ALFA'da lineerden AZ sehim vermeli (kiris kisalir)
    assert elastika(3.0)["delta_y_bolu_L"] < lineer_sehim(3.0)


def test_C3D10_KULLANILIYOR_C3D4_DEGIL():
    """C3D4 eğilmede kilitlenir ve doğrulamayı geçersiz kılar (ölçüldü:
    α=1'de 0,041 vs beklenen 0,30)."""
    from nlgeom_dogrulama import _kiris_agi
    m = _kiris_agi()
    assert m.element_type == "C3D10"
    assert m.tets.shape[1] == 10


def test_KENAR_ORTA_DUGUMLERI_gercekten_ORTADA():
    """C3D10 yükseltmesi sessizce yanlış olabilir; geometri denetlenir."""
    from nlgeom_dogrulama import _KENARLAR, _kiris_agi
    m = _kiris_agi()
    P, T = m.points, m.tets
    for t in T[:200]:
        for k, (a, b) in enumerate(_KENARLAR):
            orta = (P[t[a]] + P[t[b]]) / 2.0
            assert np.allclose(P[t[4 + k]], orta, atol=1e-12), \
                f"kenar {k} orta düğümü yerinde değil"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("nlgeom_dogrulama.json yok (python experiments/nlgeom_dogrulama.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_UC_OLCUT_de_saglandi(kanit):
    assert kanit["kucuk_yukte_lineere_INDIRGENIYOR"] is True
    assert kanit["buyuk_yukte_AYRISIYOR"] is True
    assert kanit["ayrisma_REFERANSA_yaklasiyor"] is True
    assert kanit["dogrulandi"] is True


def test_BUYUK_YUKTE_lineer_GERCEKTEN_yaniliyor(kanit):
    """Doğrulamanın anlamı, lineerin yanıldığı bir rejimde ölçülmesidir.
    Lineer de doğru olsaydı NLGEOM'un çalıştığı gösterilmiş olmazdı."""
    son = [k for k in kanit["seviyeler"] if "lin_vs_elastika_pct" in k][-1]
    assert abs(son["lin_vs_elastika_pct"]) > 10.0, \
        "lineer bu yükte zaten doğru — rejim NLGEOM'u sınamıyor"
    assert abs(son["nl_vs_elastika_pct"]) < 2.0, \
        "NLGEOM referansa yaklaşmıyor"


def test_KISIT_referansin_SAYISAL_oldugunu_soyluyor(kanit):
    """Elastika burada ANALİTİK değil sayısal çözüldü; kapalı form elde
    doğrulanmadı ve bu yazılmalı."""
    assert "SAYISALDIR" in kanit["_kisit"]
    assert "Euler-Bernoulli" in kanit["_kisit"]
    assert "SINANMADI" in kanit["_kisit"], "ağ bağımsızlığı kısıtı yazılmıyor"


def test_RAPOR_kanittan_sapmiyor(kanit):
    """Rapor NLGEOM sayılarını taşıyorsa kanıtla aynı olmalı."""
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "NLGEOM" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    son = [k for k in kanit["seviyeler"] if "lin_vs_elastika_pct" in k][-1]
    for deger in (round(son["nlgeom_fea"]["delta_z_bolu_L"], 4),
                  son["elastika_ref"],
                  round(son["lin_vs_elastika_pct"], 1)):
        s = f"{deger}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"
    # C3D4 KILITLENME DERSI rapordan sessizce dusmemeli
    assert "kilitlen" in t, "C3D4 kilitlenme bulgusu raporda yok"
    # REFERANSIN SAYISAL oldugu ve kapali formun DOGRULANMADIGI yazmali
    assert "doğrulanmadı" in t
