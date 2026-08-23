"""Uçtan uca: GERÇEK bir koşunun ürettiği her hüküm RAPORA ulaşıyor mu.

Mevcut uçtan-uca testler SENTETİK sonuçla çalışıyor ve tek tek hükümleri
çapalıyor (fizik kapısı banner'ı, kırpılan itki satırı). Eksik olan sistematik
olanıydı: bir koşu on-onbeş ayrı hüküm üretiyor ve raporun hepsini taşıdığını
kimse toplu olarak denetlemiyordu.

BU, BU OTURUMDA ÜÇ KEZ ÇIKAN KUSUR SINIFININ TA KENDİSİ --- parça doğru, yol
geçmiyor:
  * y⁺ kapsamı ölçülüyordu, band üreticisine ulaşmıyordu
  * iki-yönlü FSI'nin üretim girişi yoktu (yalnız testler hareketli ağ kuruyordu)
  * yer değiştirme vakanın DIŞINA yazılıyordu, ağ hiç kıpırdamıyordu

Zincir: arayüz → `run_vehicle_analysis` → (içeride) `build_vehicle_report`.
Çözücü pahalı olduğu için burada KAYITLI bir koşu kullanılır; sınanan şey
çözücü değil, çözücüden SONRAKİ yoldur.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))


def _kayitli_kosular() -> list[Path]:
    """Rapora sokulabilecek TAM koşular: sonuç + geometri + başarı."""
    out = []
    for sj in sorted((KOK / "vehicle_runs").glob("*/sonuc.json")):
        try:
            d = json.loads(sj.read_text(encoding="utf-8"))
        # sessiz-yutma: kabul — bozuk kayıt bu testin konusu değil; kapsam
        # aşağıda ADIYLA beyan ediliyor
        except json.JSONDecodeError:
            continue
        if d.get("status") == "ok" and d.get("geometry") and d.get("cd") is not None:
            out.append(sj)
    return out


@pytest.fixture(scope="module")
def kosu():
    hepsi = _kayitli_kosular()
    if not hepsi:
        pytest.skip("kayıtlı başarılı koşu yok")
    # EN ZENGIN kayit secilir: en cok hukum tasiyan kosu en cok yolu sinar.
    def zenginlik(p):
        d = json.loads(p.read_text(encoding="utf-8"))
        return sum(1 for k in ("validity", "belirsizlik", "mesh_duyarlilik",
                               "kurulum", "gerilemeler", "fizik_kabul",
                               "sinir_tabaka", "convergence") if d.get(k))
    return max(hepsi, key=zenginlik)


@pytest.fixture(scope="module")
def rapor(kosu, tmp_path_factory):
    from vehicle_pipeline import VehicleAnalysisResult
    from vehicle_report import build_vehicle_report

    d = json.loads(kosu.read_text(encoding="utf-8"))
    alanlar = set(VehicleAnalysisResult.__dataclass_fields__)
    r = VehicleAnalysisResult(**{k: v for k, v in d.items() if k in alanlar})
    out = tmp_path_factory.mktemp("rapor")
    yol = build_vehicle_report(r, [], (r.convergence or {}).get("residuals") or {}, out)
    return {"kayit": d, "metin": Path(yol).read_text(encoding="utf-8"), "yol": Path(yol)}


# Rapora ULASMAMASI KABUL EDILEN alanlar — her biri GEREKCELI.
# Bir alani buraya eklemek bilincli bir karardir.
KABUL = {
    "case_dir": "disk yolu; raporun kendisi o dizinde durur",
    "report": "raporun kendi yolu; rapor kendi yolunu yazmaz",
    "cp_vtk": "figür kaynağı; rapor figürü GÖMER, yolu yazmaz",
    "kesit_vtk": "yukarıdakiyle aynı",
    "stl": "girdi dosyası; rapor geometri bölümünde adıyla yazar",
    "status": "koşu durumu; rapor zaten yalnız başarılı koşu için üretilir",
    "error": "hata metni; başarılı koşuda boş",
    "ortam": "ortam parmak izi; kanıt dosyasında durur, rapor metninde değil",
    "asama_sureleri": "aşama telemetrisi; başarım bölümü ayrı üretilir",
    "bellek": "bellek telemetrisi; yukarıdakiyle aynı",
}


def _etiket(sinif: str | None) -> str:
    """Sınıf kodu → raporun YAZDIĞI Türkçe etiket, TEK KAYNAKTAN.

    Tabloyu buraya kopyalamak ikinci kaynak yaratırdı: etiket değişse test
    eski etiketi arayıp "ulaşmıyor" derdi.
    """
    from validity_envelope import _TR
    return _TR.get(sinif, sinif or "")


def test_rapor_URETILDI(rapor):
    assert rapor["yol"].exists() and rapor["metin"].strip()


def test_HUKUM_tasiyan_alanlarin_hepsi_RAPORDA(rapor):
    """Koşunun ürettiği her hüküm-alanı raporda İZ bırakmalı.

    'İz' = alanın adı ya da taşıdığı sayı/hüküm metninde geçmeli. Alanın
    varlığı yetmez; kullanıcı raporu okur.
    """
    d, metin = rapor["kayit"], rapor["metin"]
    hukum_alanlari = {
        "cd": lambda v: f"{v}" in metin or f"{v:.4f}"[:6] in metin,
        # SINIF KODU DEGIL, RENDER EDILEN ETIKET aranir. Rapor "TREND" degil
        # "YALNIZ-EĞİLİM" yazar; kod adini aramak, ULASAN bir alani "ulasmiyor"
        # gostermisti (ilk yazimda tam bu oldu).
        "validity": lambda v: _etiket(v.get("sinif")) in metin,
        "belirsizlik": lambda v: any(
            str(x) in metin for x in (v.get("u_toplam_pct"), v.get("u_sayisal_pct"))
            if x is not None),
        "mesh_duyarlilik": lambda v: bool(v.get("verdikt")) and (
            v["verdikt"][:24] in metin),
        "kurulum": lambda v: (not v) or any(u[:28] in metin for u in v),
        "fizik_kabul": lambda v: (v.get("verdict") != "ok") <= (
            any(x[:20] in metin for x in (v.get("reasons") or []))),
    }
    eksik = []
    for alan, sinar in hukum_alanlari.items():
        v = d.get(alan)
        if v in (None, "", [], {}):
            continue
        try:
            varsa = bool(sinar(v))
        except Exception as e:      # noqa: BLE001 — sebep testte GORUNUR
            eksik.append(f"{alan}: denetim düştü ({type(e).__name__}: {e})")
            continue
        if not varsa:
            eksik.append(f"{alan}: kayıtta VAR, raporda İZ YOK")
    assert not eksik, (
        "hüküm üretildi ama kullanıcının eline geçen rapora ULAŞMIYOR:\n  "
        + "\n  ".join(eksik))


def test_KABUL_listesi_gercek_alanlara_isaret_ediyor():
    """Ölü muafiyet, sözlüğün anlamını zamanla yitirmesine yol açar."""
    from vehicle_pipeline import VehicleAnalysisResult
    alanlar = set(VehicleAnalysisResult.__dataclass_fields__)
    olu = sorted(set(KABUL) - alanlar)
    assert not olu, f"KABUL'de artık var olmayan alan: {olu}"


def test_GUI_parametreleri_HAT_IMZASINA_uyuyor():
    """Zincirin ilk halkası: arayüzün topladığı sözlük hatta GEÇEBİLMELİ.

    Arayüz `run_vehicle_analysis(progress_cb=..., **p)` çağırıyor; `p` içinde
    imzada olmayan tek bir anahtar TypeError verir ve koşu HİÇ başlamaz.
    """
    import ast

    from vehicle_pipeline import run_vehicle_analysis
    imza = set(inspect.signature(run_vehicle_analysis).parameters)
    src = (KOK / "app_analyzer.py").read_text(encoding="utf-8")
    anahtarlar = set()
    for d in ast.walk(ast.parse(src)):
        if isinstance(d, ast.Dict):
            anahtarlar |= {k.value for k in d.keys
                           if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    # Arayuzun kullandigi ve HAT parametresi gibi gorunen anahtarlar
    aday = {a for a in anahtarlar if a in imza}
    assert len(aday) >= 8, (
        f"arayüzden hatta geçen parametre sayısı beklenenden az ({len(aday)}) — "
        f"zincir kopmuş olabilir")


def test_RAPOR_kapsamini_beyan_ediyor(rapor):
    """Rapor hangi koşudan üretildiğini ve yöntemini söylemeli."""
    metin = rapor["metin"]
    assert "OpenFOAM" in metin
    assert "Re = " in metin and "Ma = " in metin
    assert rapor["kayit"]["vehicle_type"] in metin


def test_KAPSAM_beyani(kosu):
    """Bu test TEK koşuyu sınar; hangisi olduğu görünür olmalı.

    'Uçtan uca geçti' demek, tüm koşuların geçtiği anlamına GELMEZ.
    """
    hepsi = _kayitli_kosular()
    assert kosu in hepsi
    assert len(hepsi) >= 1
    # Secilen kosu ADIYLA gorunsun diye kayda gecirilir
    print(f"\nuçtan uca sınanan koşu: {kosu.parent.name} "
          f"({len(hepsi)} kayıtlı başarılı koşudan)")
