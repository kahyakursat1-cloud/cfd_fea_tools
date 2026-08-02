"""Eski Parametrik GUI SONUÇ ÜRETMİYOR — ürettiğini sandırması geri gelmesin.

ÖLÇÜLDÜ (2026-08-02): `app_parametric._start_simulation` bir SimulationJob
kuruyor ama çözücü çağrısı YORUMDA bırakılmıştı; ardından 101 adımlık uyku
döngüsü koşup tamamlandı mesajı yazıyordu. Çözücü hiç çağrılmıyordu.

`_run_fea_analysis` daha ağırdı: gerilmeyi yükten uydurup ondan emniyet faktörü
çıkarıyor ve güvenlik hükmü veriyordu; doğal frekanslar aritmetik bir diziydi.

Bu, depodaki diğer kusurların TERSİ: orada hüküm hesaplanıp tüketicisine
ulaşmıyordu, burada hesap yapılmadan hüküm veriliyordu.

TEST METNE DEĞİL YAPIYA BAKAR: kusurun ne olduğunu kodda ve burada AÇIKÇA
yazmak istiyoruz; metin taraması o belgelemeyi ihlal sayardı.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGAC = ast.parse((ROOT / "app_parametric.py").read_text(encoding="utf-8"))


def _fn(ad: str) -> ast.FunctionDef:
    for d in ast.walk(AGAC):
        if isinstance(d, ast.FunctionDef) and d.name == ad:
            return d
    raise AssertionError(f"{ad} yok")


def _cagrilar(fn) -> set:
    out = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            out.add(f.attr if isinstance(f, ast.Attribute) else
                    getattr(f, "id", ""))
    return out


def _adlar(fn) -> set:
    return {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)} | \
           {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}


def _metinler(fn, docstring_haric: bool = True) -> list:
    """Fonksiyon gövdesindeki dizgi sabitleri. Docstring HARİÇ: kusurun ne
    olduğunu kodda açıkça yazmak istiyoruz, tarama onu ihlal saymamalı.
    `ast.get_docstring` TEMİZLENMİŞ metin döndürür, yani kimlik karşılaştırması
    tutmaz — düğümün kendisi dışlanır."""
    ds = None
    if (docstring_haric and fn.body and isinstance(fn.body[0], ast.Expr)
            and isinstance(fn.body[0].value, ast.Constant)
            and isinstance(fn.body[0].value.value, str)):
        ds = fn.body[0].value
    return [n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n is not ds]


def test_SAHTE_ilerleme_dongusu_yok():
    fn = _fn("_start_simulation")
    assert "sleep" not in _cagrilar(fn)
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.For)]


def test_UYDURMA_gerilme_hesabi_yok():
    """`yük/100*2.5` ile gerilme uydurup ondan SF çıkarmak."""
    fn = _fn("_run_fea_analysis")
    assert "yield_strength" not in _adlar(fn)
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.BinOp)]


def test_analiz_govdeleri_TAMAMLANDI_iddia_etmiyor():
    """Koşu yokken 'tamamlandı/güvenli' demek en yanıltıcı çıktıydı."""
    for ad in ("_start_simulation", "_run_fea_analysis"):
        for m in _metinler(_fn(ad)):
            d = m.lower()
            assert "tamamland" not in d and "güvenl" not in d, (ad, m)


def test_analiz_dugmeleri_GEREKCELI_ret_veriyor():
    import app_parametric as ap
    for ad in ("_start_simulation", "_run_fea_analysis", "_generate_report"):
        assert "_demo_reddi" in _cagrilar(_fn(ad)), ad
    assert "app_analyzer.py" in ap.DEMO_RET_METNI
    assert "ÜRETMEZ" in ap.DEMO_RET_METNI


def test_GERCEK_yola_yonlendiriyor():
    """Kullanıcı reddedilip ortada bırakılmamalı."""
    assert (ROOT / "app_analyzer.py").exists()


def test_MOTOR_gercek_kaldi():
    """Sahte olan GUI katmanıydı; simulation_runner'a dokunulmadı."""
    rs = (ROOT / "simulation_runner.py").read_text(encoding="utf-8")
    assert "def run_simulation" in rs and "force_admissibility" in rs
