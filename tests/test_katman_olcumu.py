"""Katman çökmesi ÖLÇÜMÜ — çıkarım değil.

Bugüne kadar katman çökmesi yalnız DOLAYLI teşhis ediliyordu: "ölçülen y⁺ hedefin
5 katından büyükse şüphe". Oysa snappyHexMesh sonunda kaç katman ördüğünü bir
tabloda YAZIYOR. MiniHawk 'hassas' koşusunda 12 katman istenmiş, mesh katmansız
koşuyla BİREBİR aynı hücre sayısını vermiş (3.943.330) ve y⁺=4113 ölçülmüştü —
yani katman adımı sessizce çökmüştü ve rapor yine "12 katman" diyordu.
"""
from pathlib import Path

import pytest

from vehicle_pipeline import katman_hukmu, parse_layer_report

TABLO = """
Layer mesh : cells:3943330  faces:11000000  points:4000000

patch      faces    layers   overall thickness
                             [m]       [%]
-----      -----    ------   ---       ---
{ad}   12345    {n}        {t}      {p}

Finished meshing in = 1234 s.
"""


def _log(tmp_path, ad="minihawk", n=0, t=0.0, p=0.0):
    d = tmp_path / "case"
    d.mkdir(exist_ok=True)
    (d / "log.snappyHexMesh").write_text(TABLO.format(ad=ad, n=n, t=t, p=p))
    return d


def test_sifir_katman_COKTU_olarak_olculur(tmp_path):
    d = _log(tmp_path, n=0)
    h = katman_hukmu(parse_layer_report(d / "log.snappyHexMesh"), 12, "minihawk")
    assert h["durum"] == "COKTU"
    assert h["istenen"] == 12 and h["eklenen"] == 0


def test_tam_katman_ok(tmp_path):
    d = _log(tmp_path, n=12, t=5.5e-4, p=8.0)
    h = katman_hukmu(parse_layer_report(d / "log.snappyHexMesh"), 12, "minihawk")
    assert h["durum"] == "ok" and h["eklenen"] == 12
    assert h["kalinlik_m"] == pytest.approx(5.5e-4)


def test_yarisindan_az_KISMI(tmp_path):
    d = _log(tmp_path, n=4, t=1e-4, p=2.0)
    h = katman_hukmu(parse_layer_report(d / "log.snappyHexMesh"), 12, "minihawk")
    assert h["durum"] == "kismi"


def test_log_yoksa_OK_DEMEZ(tmp_path):
    h = katman_hukmu(parse_layer_report(tmp_path / "yok.log"), 12)
    assert h["durum"] == "olculemedi"
    assert "yok" in h["neden"]


def test_katman_istenmediyse_sikayet_etmez(tmp_path):
    h = katman_hukmu(parse_layer_report(tmp_path / "yok.log"), 0)
    assert h["durum"] == "katman_istenmedi"


def test_tablo_yoksa_SEBEBI_yazilir(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "log.snappyHexMesh").write_text("Finished meshing in = 10 s.\n")
    r = parse_layer_report(d / "log.snappyHexMesh")
    assert r["okundu"] is False
    assert "katman tablosu yok" in r["neden"]


def test_DOGRU_PATCH_secilir(tmp_path):
    """Zemin-etkili kurulumda bottom da wall — yanlış yamayı okumak 5200'lük
    y⁺ hayaletinin aynısını katman tarafında üretirdi."""
    d = tmp_path / "c"
    d.mkdir()
    (d / "log.snappyHexMesh").write_text(
        "patch      faces    layers   overall thickness\n"
        "                             [m]       [%]\n"
        "-----      -----    ------   ---       ---\n"
        "bottom     999      10       1e-3      5\n"
        "minihawk   12345    0        0         0\n\n"
        "Finished meshing in = 1 s.\n")
    r = parse_layer_report(d / "log.snappyHexMesh")
    assert len(r["yamalar"]) == 2
    assert katman_hukmu(r, 12, "minihawk")["durum"] == "COKTU"
    assert katman_hukmu(r, 12, "bottom")["durum"] == "ok"
