"""Yer değiştirme VAKANIN İÇİNE yazılıyor mu — sessiz kayma en pahalı kusurdu.

ÖLÇÜLDÜ 2026-08-22 (fsi_tahrikH): `map_fn`, `write_point_displacement`'a
`vaka.run_dir` veriyordu. O fonksiyon `<dizin>/<zaman>/pointDisplacement`
yazar, yani alan `vehicle_runs/X/0/`'a düştü --- OpenFOAM vakası ise
`vehicle_runs/X/X/` idi. Çözücü onu HİÇ OKUMADI: yedi zaman dizininin
yedisinde de gövde yaması `uniform (0 0 0)` kaldı ve ağ hiç kıpırdamadı.

Kuplaj bunun üzerine `sabit-harita` imzası verdi. İMZA DOĞRUYDU ama teşhis
yanlış olurdu: "fizik kuplajı sürmüyor" değil, "yer değiştirme ağa
ulaşmıyor". İkisi aynı belirtiyi verir ve biri donanım/vaka seçimini, öbürü
bir satırlık düzeltmeyi gerektirir.

İKİNCİ KUSUR AYNI KOŞUDA: çağıran `yama='fsi_tahrikH'` verdi, ağdaki yama
`fsi_tahrikH_prep`. Yanlış ada yazılan sınır koşulu da sessizce hiçbir şey
yapmaz. `_fsi_esnek` vakasında gerçek yama `kanatcik`; orada da aynı kayma
mümkündü.

NEDEN TESTLER KAÇIRDI: ağ hareketi daha önce doğrulanmıştı (3,000 mm istendi,
3,0000 mm ölçüldü) ama o doğrulama `write_point_displacement`'ı DOĞRUDAN
çağırıyordu. Sürücünün çağrı yeri hiç koşulmamıştı --- deponun kendi dersi:
dış araç süren kod gerçekten koşulmadan doğrulanmış sayılmaz.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))


def _sahte_vaka(tmp_path: Path, vaka_adi="X", yamalar=("inlet", "govde")):
    from fsi_surucu import KuplajVakasi
    run = tmp_path / "kosu"
    case = run / vaka_adi
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text("application foamRun;\n")
    pm = case / "constant" / "polyMesh"
    pm.mkdir(parents=True)
    govde = "\n".join(f"    {y}\n    {{\n        type patch;\n    }}" for y in yamalar)
    (pm / "boundary").write_text(f"{len(yamalar)}\n(\n{govde}\n)\n")
    return KuplajVakasi(run_dir=run, yama="govde"), case


def test_VAKA_dizini_kosu_dizininden_AYIRT_ediliyor(tmp_path):
    from fsi_surucu import _vaka_dizini
    vaka, case = _sahte_vaka(tmp_path)
    assert _vaka_dizini(vaka) == case
    assert _vaka_dizini(vaka) != vaka.run_dir, (
        "koşu dizini vaka dizini sanılırsa yer değiştirme vakanın DIŞINA yazılır")


def test_IKI_vaka_dizini_varsa_TAHMIN_edilmiyor(tmp_path):
    """Belirsizlikte sessizce birini seçmek, ağı hareketsiz bırakabilir."""
    from fsi_surucu import _vaka_dizini
    vaka, _ = _sahte_vaka(tmp_path)
    ikinci = vaka.run_dir / "Y" / "system"
    ikinci.mkdir(parents=True)
    (ikinci / "controlDict").write_text("application foamRun;\n")
    with pytest.raises(FileNotFoundError, match="BELİRSİZ|tek-anlamlı"):
        _vaka_dizini(vaka)


def test_YAMA_adi_agdan_DOGRULANIYOR(tmp_path):
    """Çağıranın verdiği ad ağda yoksa tek gövde yamasına düşülür."""
    from fsi_surucu import _govde_yamasi
    vaka, _ = _sahte_vaka(tmp_path, yamalar=("inlet", "outlet", "govde_prep"))
    vaka.yama = "govde"                      # AGDA YOK
    assert _govde_yamasi(vaka) == "govde_prep", (
        "yanlış yama adı sessizce kabul edilirse sınır koşulu hiçbir şey yapmaz")


def test_yama_BELIRSIZSE_hata(tmp_path):
    from fsi_surucu import _govde_yamasi
    vaka, _ = _sahte_vaka(tmp_path, yamalar=("inlet", "kanat", "govde_prep"))
    vaka.yama = "yok_boyle"
    with pytest.raises(ValueError, match="belirsiz"):
        _govde_yamasi(vaka)


def test_map_fn_VAKA_dizinine_yaziyor_ve_DENETLIYOR():
    """AST: `write_point_displacement` çağrısının ilk argümanı `run_dir` OLAMAZ.

    Metin araması yapılmıyor --- `vaka.run_dir` dizisi bu dosyanın kendi
    açıklayıcı yorumlarında da geçiyor ve bu depoda tam o kusur (kendi
    yorumuyla eşleşen test) daha önce yaşandı.
    """
    src = (KOK / "fsi_surucu.py").read_text(encoding="utf-8")
    cagrilar = [d for d in ast.walk(ast.parse(src))
                if isinstance(d, ast.Call)
                and getattr(d.func, "id", None) == "write_point_displacement"]
    assert cagrilar, "sürücü write_point_displacement çağırmıyor"
    for c in cagrilar:
        ilk = c.args[0]
        kotu = (isinstance(ilk, ast.Attribute) and ilk.attr == "run_dir")
        assert not kotu, (
            "yer değiştirme KOŞU dizinine yazılıyor — vaka bir alt seviyede ve "
            "çözücü dosyayı hiç okumaz; ilmek sessizce tek-yönlü olur")
    # Yazilan yolun vaka icinde OLDUGU ayrica denetlenmeli
    assert "vaka dizininin DIŞINA yazıldı" in src, (
        "yazılan yolun vaka içinde kaldığı doğrulanmıyor")
