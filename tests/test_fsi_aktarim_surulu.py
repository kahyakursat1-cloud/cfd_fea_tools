"""Kuplajın yanıtı FİZİKTEN mi AKTARIMDAN mı geliyor.

`sabit_harita` kapısı haritanın yanıt VERMEDİĞİ durumu yakalar. Ters durum
yakalanmıyordu: harita yanıt veriyor ama sebep aerodinamik yükün değişmesi
değil, yük aktarımının BOZULMASI.

ÖLÇÜLDÜ 2026-08-22 (fsi_tahrikH, ağ hareketi onarıldıktan SONRA):

    tur   FEA'ya taşınan Fz   CFD yüzeyindeki Fz   aktarım artığı
      1        0,6615 N            0,6058 N            %8,4
      2        0,4405 N            0,6065 N           %27,4
      3        0,4405 N            0,6070 N           %27,4

İlmek yakınsadı ve `sabit_harita_suphesi` FALSE dedi --- teknik olarak doğru,
harita gerçekten girdiye yanıt veriyor. Ama aerodinamik yük %0,2 değişti;
değişen AKTARIMDI. CFD yüzeyi deforme olurken yük haritasının dayandığı FEA
STL'i referans konumda kalıyor ve en-yakın-komşu eşlemesi bozuluyor.

Yakınsama sahte değil ama SEBEBİ fizik değil. Bu ayrım yazılmazsa sonuç
"iki-yönlü FSI çalışıyor" diye okunur.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from fsi_surucu import aktarim_surulu_mu  # noqa: E402


def _tur(fea, cfd, ak, i=1):
    return {"tur": i, "Fz_fea_N": fea, "Fz_cfd_N": cfd, "aktarim_hatasi_pct": ak}


OLCULEN = [_tur(0.6615, -0.60577, 8.4, 1),
           _tur(0.4405, -0.60648, 27.4, 2),
           _tur(0.4405, -0.60701, 27.4, 3)]


def test_OLCULEN_vakada_kapi_YANIYOR():
    r = aktarim_surulu_mu(OLCULEN)
    assert r["aktarim_surulu_mu"] is True
    assert r["aero_yuk_degisimi_pct"] < 1.0, "aerodinamik yük neredeyse sabitti"
    assert r["fea_yuk_degisimi_pct"] > 30.0
    assert r["aktarim_hatasi_sicramasi_puan"] > 15.0
    assert "AKTARIMDAN GELİYOR OLABİLİR" in r["aktarim_notu"]


def test_SAGLIKLI_kuplajda_kapi_SUSUYOR():
    """Aerodinamik yük gerçekten değişiyorsa uyarı yazılmaz.

    Her yakınsamaya basılan bir uyarı okunmaz hale gelir; kapının değeri
    AYIRT ETMESİNDEDİR.
    """
    saglikli = [_tur(0.66, -0.600, 8.4, 1), _tur(0.49, -0.450, 8.6, 2)]
    r = aktarim_surulu_mu(saglikli)
    assert r["aktarim_surulu_mu"] is False
    assert "AKTARIMDAN" not in r["aktarim_notu"]


def test_AKTARIM_sabitken_kapi_SUSUYOR():
    """FEA yükü değişse bile aktarım artığı sıçramadıysa sebep aktarım değildir."""
    r = aktarim_surulu_mu([_tur(0.66, -0.600, 8.4, 1), _tur(0.44, -0.599, 8.5, 2)])
    assert r["aktarim_surulu_mu"] is False


def test_TEK_TUR_hukum_vermez():
    assert aktarim_surulu_mu([_tur(0.66, -0.6, 8.4)]) == {}
    assert aktarim_surulu_mu([]) == {}


def test_ESKI_kayitlar_sessizce_HUKUM_uretmiyor():
    """Kuvvet alanları taşımayan eski tur kayıtları için iddia YOK."""
    eski = [{"tur": 1, "max_disp_mm": 11.8}, {"tur": 2, "max_disp_mm": 11.8}]
    assert aktarim_surulu_mu(eski) == {}


def test_SURUCU_bu_alanlari_TURA_yaziyor():
    """Kapı ancak veri kaydediliyorsa çalışır — bu deponun baskın kusuru."""
    import ast
    src = (KOK / "fsi_surucu.py").read_text(encoding="utf-8")
    alanlar = set()
    for d in ast.walk(ast.parse(src)):
        if isinstance(d, ast.Call) and getattr(
                getattr(d.func, "attr", None), "__str__", lambda: "")() == "append":
            for a in d.args:
                if isinstance(a, ast.Dict):
                    alanlar |= {k.value for k in a.keys
                                if isinstance(k, ast.Constant)}
    for gerekli in ("Fz_fea_N", "Fz_cfd_N", "aktarim_hatasi_pct"):
        assert gerekli in alanlar, (
            f"tur kaydında '{gerekli}' yok — aktarım-sürülü kapısı beslenemez")
