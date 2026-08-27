"""CSM1: yapısal zincir YAYIMLANMIŞ bir değere karşı doğrulandı (%0,2).

Bu deponun FSI tarafındaki en güçlü çapası budur ve akış hiç işin içine
girmez. İki-yönlü FSI1'de yapısal model DOLAYLI elenmişti: ux referansı
%1,3 bandında tutturuyor, ux ise EA'ya bağlı. Doğru bir çıkarım ama
EĞİLME rijitliğini sınamıyordu. CSM1 onu doğrudan sınar --- aynı bayrak,
aynı malzeme, tek yük yerçekimi --- ve sehim/uzunluk %19 olduğu için
NLGEOM'u da zorlar.

BU ÖLÇÜM BİR YAZIM KUSURUNU DA AÇIĞA ÇIKARDI. FSI1'de düzlem-gerinim
kısıtını .inp METNİNE ELLE enjekte etmiştim. Burada `*STATIC`'in artım
satırı (``0.1, 1.0'') vardı ve eklenen blok onu `*BOUNDARY` verisi hâline
getirdi; CalculiX girdiyi reddetti. Lineer adımda o satır olmadığı için
FSI1'de sessizce çalışıyordu. `FixedBC` zaten `dof_start`/`dof_end`
taşıyor --- elle düzenlemeye hiç gerek yoktu ve yazıcının kendi yolu
kullanıldı.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

KANIT = KOK / "turek_hron_csm1.json"


@pytest.fixture(scope="module")
def kanit():
    if not KANIT.exists():
        pytest.skip("turek_hron_csm1.json yok "
                    "(python experiments/turek_hron_csm1.py)")
    return json.loads(KANIT.read_text(encoding="utf-8"))


def test_NLGEOM_REFERANSI_YUZDE_BES_BANDINDA(kanit):
    """Asıl iddia. Düşerse yapısal zincirin doğrulanmışlığı düşer ve
    FSI1'de yapılan eleme geçersiz olur."""
    nl, s = kanit["nlgeom"], kanit["sapma_nlgeom"]
    assert nl.get("kosdu"), f"NLGEOM koşmadı: {nl.get('neden')}"
    assert abs(s["uy_pct"]) < 5.0, f"uy sapması %{s['uy_pct']}"
    assert abs(s["ux_pct"]) < 10.0, f"ux sapması %{s['ux_pct']}"


def test_LINEER_COZUM_de_KOSTU_ve_FARKLI(kanit):
    """Lineer koşu bir kontroldür: NLGEOM'un GERÇEKTEN devrede olduğunu
    gösterir. İkisi aynı çıkıyorsa NLGEOM âtıldır --- bu depo o dersi
    C3D4'ün kayma kilitlenmesinde ödedi."""
    li, nl = kanit["lineer"], kanit["nlgeom"]
    if not li.get("kosdu"):
        pytest.skip("lineer koşu düştü")
    assert li["uy_mm"] != nl["uy_mm"]
    fark = abs(100 * (li["uy_mm"] - nl["uy_mm"]) / nl["uy_mm"])
    assert fark > 0.5, (
        f"lineer ve NLGEOM yalnız %{fark:.2f} ayrışıyor --- bu sehimde "
        "geometrik katkı görünmelidir, NLGEOM devrede olmayabilir")


def test_BUYUK_YER_DEGISTIRME_REJIMINDE(kanit):
    """Vakanın değeri büyük sehimde olmasıdır. Küçülürse NLGEOM'u
    sınamıyordur ve bu testin gerekçesi düşer."""
    L = kanit["geometri"]["L_m"] * 1000.0
    oran = abs(kanit["referans"]["uy_mm"]) / L
    assert oran > 0.10, f"sehim/uzunluk yalnız {oran:.3f}"


def test_REFERANS_CIFTI_KENDI_ICINDE_TUTARLI(kanit):
    """FSI1'de bu formülü bir kapı olarak yazmış ve YANLIŞ uygulamıştım
    (akışkan kayma çekmesi orada eksenel yükü baskın kılıyordu). Akışın
    olmadığı CSM1'de formülün KENDİSİ sınanabilir."""
    k = kanit["referans_kinematigi"]
    assert 0.7 < k["oran"] < 1.4, (
        f"kinematik kısalma {k['ux_kinematik_mm']} mm, referans ux "
        f"{k['ux_referans_mm']} mm --- oran {k['oran']}")


def test_DUZLEM_GERINIM_YAZICININ_YOLUYLA(kanit):
    """Kısıt .inp metnine elle enjekte edilirse `*STATIC` artım satırını
    bozar. Bu test o yolun geri gelmesini engeller."""
    import ast
    yol = KOK / "experiments" / "turek_hron_csm1.py"
    src = yol.read_text(encoding="utf-8")
    assert 'dof_start=3' in src and 'name="ZDUZLEM"' in src
    # OLCUT MEKANIZMAYA BAGLANIR, METNE DEGIL. Ilk surum `"*BOUNDARY"
    # kaynakta gecmesin` diyordu ve KENDI ACIKLAMA SATIRIMI yakaladi ---
    # bu deponun tekrar eden kusuru. Elle duzenlemenin imzasi bir dize
    # degil, uretilen .inp'ye GERI YAZMAKTIR; AST onu kesin gorur.
    # ... ve olcut IKINCI kez de fazla genisti: "hic write_text olmasin"
    # kaydin KENDI dosyasini yazan satiri suclads. Yasak olan yazmak degil
    # NEREYE yazildigi --- yalniz `write_inp`'ten dogan yola.
    agac = ast.parse(src)
    inp_adlari = {
        t.id for n in ast.walk(agac) if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)
        if isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "")
        == "write_inp"}
    kirli = [n for n in ast.walk(agac)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr in ("write_text", "read_text")
             and getattr(n.func.value, "id", None) in inp_adlari]
    assert not kirli, (
        "üretilen .inp'ye geri yazılıyor/okunuyor; bu `*STATIC` artım "
        "satırını bozar --- FixedBC yolu kullanılmalı")
    assert kanit["geometri"]["duzlem_gerinim"] is True


def test_GEOMETRI_VE_MALZEME_KAYNAKLA_AYNI(kanit):
    """Yanlış geometriyle tutturulan bir referans hiçbir şey doğrulamaz."""
    g, k = kanit["geometri"], kanit["kati"]
    assert abs(g["L_m"] - 0.35) < 0.005, f"L={g['L_m']}, kaynak 0,35"
    assert k["h_m"] == 0.02 if "h_m" in k else g["h_m"] == 0.02
    assert k["E_Pa"] == pytest.approx(1.4e6)
    assert k["nu_s"] == 0.4 and k["rho"] == 1000.0 and k["g_m_s2"] == 2.0


def test_A_NOKTASI_gercekten_UC_ORTASI(kanit):
    nl = kanit["nlgeom"]
    if not nl.get("kosdu"):
        pytest.skip("NLGEOM koşmadı")
    assert nl["A_uzaklik_m"] < 1e-9


def test_KISIT_agin_ve_MALZEME_MODELININ_sinirini_soyluyor(kanit):
    k = kanit["_kisit"]
    assert "AG-BAGIMSIZLIGI SINANMADI" in k
    assert "St. Venant-Kirchhoff DEGIL" in k
    assert "Artim sayisi" in k


def test_HUKUM_FSI1_ELEMESINI_BAGLIYOR(kanit):
    """Bu ölçümün amacı FSI1'deki dolaylı elemeyi doğrudan hale
    getirmekti; hüküm bunu söylemezse bağlantı kaybolur."""
    v = kanit["verdikt"]
    assert "FSI1" in v
    if abs(kanit["sapma_nlgeom"]["uy_pct"]) < 5.0:
        assert "yapıda DEĞİLDİR" in v


def test_RAPOR_kanittan_sapmiyor(kanit):
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not tex.exists():
        pytest.skip("rapor yok")
    t = tex.read_text(encoding="utf-8")
    if "CSM1" not in t:
        pytest.skip("rapor bu ölçümü henüz taşımıyor")
    nl = kanit["nlgeom"]
    for deger in (round(nl["uy_mm"], 3), round(nl["ux_mm"], 3)):
        s = f"{deger}".replace(".", "{,}").replace("-", "")
        assert s in t, f"{s} raporda yok"
