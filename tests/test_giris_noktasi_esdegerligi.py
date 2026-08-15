"""Giriş noktaları aynı niyeti aynı parametreye çeviriyor mu?

Bir mühendislik yazılımındaki en sinsi hata sınıfı: aynı fiziksel işlemin iki
kod yolundan yapılması ve zamanla ayrışması — "GUI sonucu ≠ CLI sonucu".
Bu depoda ÜÇ giriş noktası var (arayüz, `vehicle_pipeline` CLI, `kuyruk` CLI)
ve üçü de `run_vehicle_analysis` çağrısını KENDİ kuruyor.

ÖLÇÜLDÜ (2026-08-07), iki gerçek sapma:
  - `kuyruk.py ekle` CLI'si `ref_bump` GÖNDERMİYORDU. Arayüzün "Kuyruğa Ekle"
    düğmesi "oto" gönderiyordu. Aynı kuyruk, aynı worker, işin NASIL
    eklendiğine göre farklı y⁺ davranışı.
  - Arayüz `mesh_levels` göndermiyordu, yani hep 3 seviye. LSR (Eça–Hoekstra)
    EN AZ 4 grid ister — arayüz kullanıcısı LSR bandını HİÇ alamıyordu.

Bu test bir parametrenin bazı yollarda AÇIK, bazılarında SESSİZCE varsayılan
kalmasını yakalar. Kasıtlı varsayılanlar aşağıda LİSTELİDİR: karar kayda
geçmiş olur, unutulmuş olmaz.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from vehicle_pipeline import run_vehicle_analysis  # noqa: E402

# Cagri mekanigine ait, kullanici niyeti DEGIL.
MEKANIK = {"progress_cb", "out_root", "stl_path"}

# KASITLI olarak varsayilanda birakilanlar — bilincli tasarim karari.
KASITLI_VARSAYILAN = {
    "rho": "hava yoğunluğu; deniz seviyesi 1.225 dışına çıkmak uzman işi",
    "turbulence_model": "kOmegaSST varsayılan; model değişimi V&V bandını "
                        "geçersizleştirir, uzman yolundan yapılmalı",
    "max_cells": "kalite preset'i belirler; elle ezmek bütçe kapısını atlar",
    "ground_clearance": "yalnız zemin-etkili araçlar (araba preset'i kendi verir)",
    "refinement_regions": "elle iyileştirme bölgesi — uzman/deneysel yol",
}

# BILINEN BOSLUK — kasitli degil, henuz yapilmadi. Bu ayrim onemli: birincisi
# bir karar, bu bir BORC. Ayni torbaya konursa borç karar gibi gorunur ve
# kimse kapatmaz.
BILINEN_BOSLUK = {
    "pervane_itki_n": "CFD aktüatör-disk kaynağı yalnız CLI'de; arayüzde YOK. "
                      "Arayüzdeki 'Motor itkisi' YAPISAL yüktür (FEA), akış "
                      "modeli değildir — ikisi karıştırılmamalı.",
    "pervane_cap_m": "aktüatör-disk çapı; yukarıdakiyle birlikte gelir. "
                     "Arayüze eklemek ayrı iş: itki kapısının (thrust cap) ve "
                     "bu modelin doğrulama durumunun ayrıca ele alınması gerekir.",
}


def _param_sozlukleri(dosya: str) -> dict[str, set[str]]:
    """Dosyadaki `run_vehicle_analysis` parametre sözlüklerini fonksiyon adıyla."""
    src = (KOK / dosya).read_text(encoding="utf-8")
    out: dict[str, set[str]] = {}
    for fn in ast.walk(ast.parse(src)):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for d in ast.walk(fn):
            if not isinstance(d, ast.Dict):
                continue
            k = {x.value for x in d.keys if isinstance(x, ast.Constant)}
            if {"stl_path", "vehicle_type", "velocity"} <= k:
                out[f"{dosya}:{fn.name}"] = k
    return out


def _cli_parametreleri() -> set[str]:
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    i = src.index("r = run_vehicle_analysis(args.model")
    j = src.index("\n    if r.status", i)
    cagri = ast.parse(src[i + 4:j]).body[0].value
    return ({kw.arg for kw in cagri.keywords}
            | {"stl_path", "vehicle_type", "velocity", "alpha_deg", "quality"})


def _tum_yollar() -> dict[str, set[str]]:
    yollar = {}
    yollar.update(_param_sozlukleri("app_analyzer.py"))
    yollar.update(_param_sozlukleri("kuyruk.py"))
    # DÖRDÜNCÜ GİRİŞ NOKTASI (2026-08-15): Parametrik arayüz `hizmet.analiz_et`
    # üzerinden hatta bağlandı. Kapsama alınmadığı ilk sürümde DOKUZ parametre
    # sessizce varsayılana düşüyordu ve bu ölçülebilir bir sonuç doğurdu:
    # `ref_bump` geçilmediği için y⁺ 803 ölçüldü (duvar-fonksiyonu bandı 30-300),
    # `mesh_levels` geçilmediği için LSR bandı hiç üretilemezdi. Testin var oluş
    # sebebi olan kusur, testin GÖRMEDİĞİ bir yolda tekrarlandı --- kapsam
    # dışında kalan yol, korunmayan yoldur.
    yollar.update(_param_sozlukleri("app_parametric.py"))
    yollar["vehicle_pipeline.py:CLI"] = _cli_parametreleri()
    return yollar


def test_hicbir_yol_SESSIZCE_parametre_dusurmuyor():
    """Bir parametre ya tüm RANS yollarında geçilir ya da KASITLI listede olur."""
    imza = set(inspect.signature(run_vehicle_analysis).parameters) - MEKANIK
    beklenen = imza - set(KASITLI_VARSAYILAN) - set(BILINEN_BOSLUK)
    sorunlu = {}
    for ad, k in _tum_yollar().items():
        if "polar" in ad:          # polar kendi imzasını kullanır (run_polar)
            continue
        eksik = sorted(beklenen - k)
        if eksik:
            sorunlu[ad] = eksik
    assert not sorunlu, (
        "giriş noktaları ayrışıyor — bu parametreler bazı yollarda sessizce "
        f"varsayılana düşüyor: {sorunlu}. Ya geçirin ya KASITLI_VARSAYILAN'a "
        "gerekçesiyle ekleyin.")


def test_kasitli_varsayilanlarin_GEREKCESI_var():
    for ad, gerekce in {**KASITLI_VARSAYILAN, **BILINEN_BOSLUK}.items():
        assert len(gerekce) > 20, f"{ad}: gerekçe yetersiz"


def test_KARAR_ile_BORC_ayri_tutuluyor():
    """Kasıtlı varsayılan bir KARARDIR; bilinen boşluk bir BORÇTUR. Aynı
    torbaya konursa borç karar gibi görünür ve kimse kapatmaz."""
    assert not (set(KASITLI_VARSAYILAN) & set(BILINEN_BOSLUK))
    assert BILINEN_BOSLUK, "boşluk kalmadıysa liste boşaltılmalı"
    for gerekce in BILINEN_BOSLUK.values():
        assert "YOK" in gerekce or "ayrı iş" in gerekce


def test_CFD_pervanesi_ile_YAPISAL_itki_karistirilmiyor():
    """Arayüzdeki 'Motor itkisi' FEA yüküdür; CFD aktüatör diski değildir.
    İkisi aynı ada sahip olduğu için karışmaya açık."""
    src = (KOK / "app_analyzer.py").read_text(encoding="utf-8")
    assert '"itki_n": self.spn_itki.value()' in src        # FEA yolu
    assert '"pervane_itki_n"' not in src                   # CFD yolu henüz yok


def test_kasitli_liste_imzayla_tutarli():
    """Listede olmayan bir parametre kalmamalı; imzadan kalkan da listede
    kalmamalı (ölü gerekçe)."""
    imza = set(inspect.signature(run_vehicle_analysis).parameters)
    olu = set(KASITLI_VARSAYILAN) - imza
    assert not olu, f"imzada olmayan parametre listede: {olu}"


def test_kuyruk_CLI_ref_bump_gonderiyor():
    """Ölçülen sapma: GUI 'oto' gönderiyordu, kuyruk CLI'si hiç göndermiyordu."""
    src = (KOK / "kuyruk.py").read_text(encoding="utf-8")
    i = src.index("is_ = ekle({")
    assert '"ref_bump"' in src[i:i + 500]
    assert "--ref-bump" in src


def test_arayuz_mesh_levels_gonderiyor():
    """Ölçülen sapma: GUI hep 3 seviye koşuyordu, yani LSR bandı imkânsızdı."""
    src = (KOK / "app_analyzer.py").read_text(encoding="utf-8")
    assert src.count('"mesh_levels": self.spn_seviye.value()') >= 2
    assert "self.spn_seviye.setRange(3, 4)" in src


def test_dort_seviye_LSR_icin_gerekli():
    """Arayüzdeki seçeneğin NEDEN olduğunu bağlar: LSR ≥4 grid ister."""
    src = (KOK / "report_generator.py").read_text(encoding="utf-8")
    i = src.index("def least_squares_gci(")
    assert "4" in src[i:i + 800], "LSR'nin asgari grid sayısı kodda yazılı olmalı"


def test_ayni_niyet_ayni_parametreyi_uretir():
    """GUI ve kuyruk yolu, aynı formdan aynı sözlüğü kurmalı (ref_bump hariç —
    o fark KASITLI: etkileşimli kullanıcı 'oto', betik açık sayı ister)."""
    yollar = _tum_yollar()
    gui = yollar["app_analyzer.py:_run"]
    kuy = yollar["app_analyzer.py:_kuyruga_ekle"]
    fark = gui.symmetric_difference(kuy)
    assert not fark, f"arayüzün iki yolu ayrışıyor: {fark}"
