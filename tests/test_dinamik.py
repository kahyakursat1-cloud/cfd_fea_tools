"""`*DYNAMIC`: kart doğru mu, ve kart GERÇEKTEN çalışıyor mu?

NLGEOM'daki disiplin aynen uygulandı ve burada da bir kusur yakaladı ---
aslında üç:

  1. `.dat` frekans SÜTUNU yanlış okundu (5. alan = sanal kısım) ve modal
     çözücü 0,0 Hz döndürdü. Sıfır bir sayı değil bir HÜKÜMDÜR ve artık
     öyle ele alınıyor.
  2. İlk kurulum ``yükle sonra ANİDEN kaldır'' için `write_inp` çıktısına
     ikinci bir adımı ELLE ekliyordu. CalculiX reddetti --- ama asıl kusur
     başkaydı: elle düzenlenmiş bir dosyayı koşurup ``yazıcı çalışıyor''
     demek, yazıcıyı HİÇ sınamamaktır. Basamak yük aynı frekansı verir ve
     tek adımdır; yazıcının kendi çıktısı olduğu gibi koşuluyor.
  3. Artım tavanı: CalculiX varsayılanı 100 ve 240 adımlık koşu
     ``max. # of increments reached'' ile düştü. Tavan artık İSTENEN ADIM
     SAYISINDAN türetiliyor, sabit yazılmıyor.

ÇAPA BİR İÇ ÇAPRAZ-DOĞRULAMADIR: aynı ağ ve aynı sınır koşulları AYRI bir
çözücü yolundan (`*FREQUENCY`, özdeğer) geçirilir ve iki bağımsız yol aynı
frekansı vermelidir.
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

KANIT = KOK / "dinamik_dogrulama.json"


def _case(tip="DYNAMIC", **kw):
    from analysis.calculix_writer import FEACase, FEAMaterial, FixedBC
    from analysis.tet_mesher import TetMesh
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    mesh = TetMesh(points=P, tets=np.array([[0, 1, 2, 3]], int),
                   surface_tris=np.empty((0, 3), int),
                   msh_path=Path("x.msh"), element_type="C3D4")
    return FEACase(name="t", mesh=mesh,
                   material=FEAMaterial(name="m", youngs_modulus_pa=70e9,
                                        poisson_ratio=0.33,
                                        density_kg_m3=2700.0),
                   fixed_bcs=[FixedBC(node_ids=np.array([1]))],
                   analysis_type=tip, **kw)


def test_DYNAMIC_karti_ve_ZAMAN_satiri(tmp_path):
    from analysis.calculix_writer import write_inp
    t = write_inp(_case(dinamik_dt=1e-3, dinamik_sure=0.5),
                  tmp_path / "a").read_text(encoding="utf-8")
    assert "*DYNAMIC" in t
    satirlar = t.splitlines()
    i = next(k for k, ln in enumerate(satirlar) if ln.startswith("*DYNAMIC"))
    assert satirlar[i + 1].replace(" ", "") == "0.001,0.5"


def test_ARTIM_TAVANI_istenen_adimdan_TURETILIYOR(tmp_path):
    """CalculiX varsayılanı 100; 240 adımlık koşu onunla düşer (ölçüldü)."""
    from analysis.calculix_writer import write_inp
    t = write_inp(_case(dinamik_dt=1e-3, dinamik_sure=1.0),
                  tmp_path / "b").read_text(encoding="utf-8")
    adim = next(ln for ln in t.splitlines() if ln.startswith("*STEP"))
    assert "INC=" in adim
    inc = int(adim.split("INC=")[1].split(",")[0])
    assert inc >= 1000, f"tavan istenen 1000 adımdan küçük: {inc}"


def test_SONUM_degeri_DOSYAYA_yaziliyor(tmp_path):
    """Bırakılan sayısal sönüm bir çözümdeki genlik düşüşünü 'fizik'
    gösterir; değeri görünmezse okuyucu bunu bilemez."""
    from analysis.calculix_writer import write_inp
    t = write_inp(_case(dinamik_alpha=-0.05), tmp_path / "c").read_text(
        encoding="utf-8")
    assert "sayısal sönüm" in t and "ALPHA=-0.05" in t


def test_DIRECT_varsayilan_KAPALI_ama_ACILABILIYOR(tmp_path):
    """Varsayılan CalculiX'in kendi davranışı (otomatik adım) --- doğruluk
    için iyidir. Kuplajda dt'yi akış dayatır ve çağıran açıkça açar."""
    from analysis.calculix_writer import write_inp
    kapali = write_inp(_case(), tmp_path / "d").read_text(encoding="utf-8")
    acik = write_inp(_case(dinamik_direct=True), tmp_path / "e").read_text(
        encoding="utf-8")
    assert "DIRECT" not in kapali and "DIRECT" in acik


def test_DINAMIKTE_YUKLER_de_yaziliyor(tmp_path):
    """Yük yazılmazsa koşu düşmez --- sessizce sıfır yükle salınım arar."""
    from analysis.calculix_writer import ForceLoad, GravityLoad, write_inp
    c = _case()
    c.force_loads = [ForceLoad(node_ids=np.array([2]), direction=(0, 0, -1),
                               total_force_n=1.0)]
    c.gravity_loads = [GravityLoad(accel_m_s2=9.81)]
    t = write_inp(c, tmp_path / "f").read_text(encoding="utf-8")
    assert "*CLOAD" in t and "GRAV" in t


def test_FRD_COK_ADIMLI_dosyada_SESSIZ_kalmiyor(tmp_path, capsys):
    """`parse_frd` her bloğu aynı anahtara yazar --- çok adımlı dosyada
    yalnız SON adım kalır. Statikte doğru, geçicide SESSİZ VERİ KAYBI."""
    from analysis.frd_parser import parse_frd
    frd = tmp_path / "c.frd"
    bas = ("    2C" + " " * 20 + "\n"
           " -1         1 0.00000e+00 0.00000e+00 0.00000e+00\n"
           " -3\n")
    blok = ("  100CL  101 {t}         1                     1    {i}     1\n"
            " -4  DISP        4    1\n"
            " -1         1 1.00000e-03 0.00000e+00 2.00000e-03\n"
            " -3\n")
    frd.write_text(bas + blok.format(t="1.0E-03", i=1)
                   + blok.format(t="2.0E-03", i=2), encoding="utf-8")
    r = parse_frd(frd)
    assert r.adim_sayaci.get("DISP", 1) == 2, "çok adımlılık sayılmıyor"
    assert "COK ADIMLI" in capsys.readouterr().out


def test_ZAMAN_SERISI_butun_adimlari_okuyor(tmp_path):
    from analysis.frd_parser import parse_frd_zaman_serisi
    frd = tmp_path / "c.frd"
    blok = ("  100CL  101 {t}         1                     1    {i}     1\n"
            " -4  DISP        4    1\n"
            " -1         1 1.00000e-03 0.00000e+00 {z}\n"
            " -3\n")
    frd.write_text(blok.format(t="1.0E-03", i=1, z="2.00000e-03")
                   + blok.format(t="2.0E-03", i=2, z="4.00000e-03"),
                   encoding="utf-8")
    s = parse_frd_zaman_serisi(frd)
    assert s["DISP"].shape == (2, 1, 3)
    assert np.allclose(s["zamanlar"], [1e-3, 2e-3])
    assert np.allclose(s["DISP"][:, 0, 2], [2e-3, 4e-3])


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("dinamik_dogrulama.json yok (python experiments/dinamik_dogrulama.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_UC_OLCUT_de_saglandi(kanit):
    assert kanit["frekans_MODALLE_uyusuyor"] is True
    assert kanit["genlik_KORUNUYOR"] is True
    assert kanit["dt_BAGIMSIZ"] is True
    assert "DOĞRULANDI" in kanit["verdikt"]


def test_MODAL_SIFIR_FREKANS_bir_HUKUM(kanit):
    """`.dat` sütunu yanlış okununca modal 0,0 Hz döndü ve bu SESSİZDİ.
    Sıfır bir sayı değil bir hükümdür."""
    import inspect

    from dinamik_dogrulama import modal_f1
    src = inspect.getsource(modal_f1)
    assert "yanlış sütun" in src, "sıfır frekans hâlâ sessizce dönüyor olabilir"
    assert kanit["modal"]["f1_hz"] > 0


def test_CAPA_BAGIMSIZ_iki_YOLDAN_geciyor(kanit):
    """Doğrulamanın gücü buradan gelir: modal ve geçici AYRI çözücü
    yollarıdır. Analitikle karşılaştırma yardımcıdır, ASIL ölçüt değil."""
    assert kanit["modal"]["kosdu"] is True
    assert kanit["gecici_kaba"]["kosdu"] is True
    assert abs(kanit["frekans_farki_pct"]) < 3.0
    # OLCUT HARF DURUMUNA BAGLANMAZ. Kayit vurgu icin "EULER-BERNOULLI"
    # yaziyor; ilk surum "Euler-Bernoulli" ariyordu ve DOGRU bir kisit
    # cumlesinde dustu. Sinanan sey KISITIN VARLIGI, yazimi degil.
    k = kanit["_kisit"].lower()
    assert "modal" in k, "asıl ölçütün modal karşılaştırma olduğu yazılmıyor"
    assert "euler-bernoulli" in k, "analitik referansın kısıtı yazılmıyor"


def test_RAPOR_kanittan_sapmiyor(kanit):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "*DYNAMIC" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    for deger in (round(kanit["modal"]["f1_hz"], 3),
                  round(kanit["gecici_kaba"]["f_hz"], 3),
                  kanit["frekans_farki_pct"],
                  kanit["f1_analitik_hz"]):
        s = f"{deger}".replace(".", "{,}")
        assert s in t, f"{s} raporda yok"
    # UC KUSUR DERSI rapordan sessizce dusmemeli
    assert "sanal" in t, "yanlış sütun bulgusu raporda yok"
    assert "elle düzenlenmiş" in t, "yazıcıyı sınamama kusuru raporda yok"
    # ULASILABILIR != KOSULDU
    assert "koşuldu" in t.lower()
