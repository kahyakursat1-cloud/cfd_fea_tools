"""Uydurma sayı "ölçüldü" damgası ALAMAZ (provenance yıkaması).

Bulunan hata: `solvers/openfoam_wrapper._run_mock_simulation()` çözücü yokken SABİT
katsayı dosyası yazıyordu (Cd=0.1452); `post_processing` onu dosyadan okuyup
`source='openfoam'` diyordu. Sayı bir dosyadan geçerek "çözücü çıktısı"na dönüşüyor,
`[SUCCESS] END-TO-END` çerçevesiyle sunuluyordu. Mühendis için en tehlikeli hata sınıfı.
"""
import numpy as np

from post_processing.cfd_postprocessor import CFDPostProcessor
from solvers.openfoam_wrapper import OpenFOAMRunner

KATSAYI = "# Time Cd Cl Cm Cd_p Cd_v\n1000 0.145 0.522 -0.012 0.133 0.012\n"


def _dat_yaz(case: "object", metin=KATSAYI, mock=False):
    from pathlib import Path
    case = Path(case)
    d = case / "postProcessing" / "forces" / "0"
    d.mkdir(parents=True, exist_ok=True)
    (d / "coefficient.dat").write_text(metin, encoding="utf-8")
    if mock:
        (case / "postProcessing" / ".MOCK").write_text("mock", encoding="utf-8")
    return case


def test_mock_verisi_olculdu_sayilmaz(tmp_path):
    case = _dat_yaz(tmp_path / "c1", mock=True)
    r = CFDPostProcessor(case, reference_area=0.3, reference_length=0.2).extract_all(
        aircraft_name="t", wind_speed=15.0)
    assert r.data_source == "mock"
    assert r.olculdu is False
    assert "cozucu ciktisi DEGIL" in r.provenance_uyarisi()
    assert "TAHMIN" in str(r)


def test_gercek_cozucu_verisi_olculdu(tmp_path):
    case = _dat_yaz(tmp_path / "c2", mock=False)
    r = CFDPostProcessor(case, reference_area=0.3, reference_length=0.2).extract_all(
        aircraft_name="t", wind_speed=15.0)
    assert r.data_source == "openfoam" and r.olculdu is True
    assert r.provenance_uyarisi() == ""


def test_analitik_fallback_isaretlenir(tmp_path):
    """Katsayı dosyası hiç yoksa analitik tahmine düşülür — gizlenmez."""
    case = tmp_path / "c3"
    (case / "postProcessing").mkdir(parents=True)
    r = CFDPostProcessor(case, reference_area=0.3, reference_length=0.2).extract_all(
        aircraft_name="t", wind_speed=15.0)
    assert r.olculdu is False
    assert r.data_source != "openfoam"


def test_temsili_yakinsama_egrisi_isaretlenir(tmp_path):
    """log.simpleFoam yoksa dönen rezidüel eğrisi TEMSİLİDİR — ölçülmüş sayılmaz."""
    case = _dat_yaz(tmp_path / "c4", mock=True)
    r = CFDPostProcessor(case, reference_area=0.3, reference_length=0.2).extract_all(
        aircraft_name="t", wind_speed=15.0)
    assert r.convergence_source == "placeholder"


def test_mock_kosu_isaretci_birakir(tmp_path):
    """Mock simülasyon, ürettiği veriyi kendi işaretler (okuyucuya bağımlı değil)."""
    case = tmp_path / "c5"
    (case / "postProcessing").mkdir(parents=True)
    runner = OpenFOAMRunner(case, solver="simpleFoam")
    assert runner._run_mock_simulation() is True
    assert (case / "postProcessing" / ".MOCK").exists()
    dat = (case / "postProcessing" / "forces" / "0" / "coefficient.dat").read_text()
    assert "MOCK" in dat.splitlines()[0]
    # yorum satirlari veri okumayi bozmamali
    assert np.loadtxt(case / "postProcessing" / "forces" / "0" / "coefficient.dat",
                      comments="#").shape[1] == 6
