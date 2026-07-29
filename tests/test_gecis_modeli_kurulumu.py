"""kOmegaSSTLM (Langtry-Menter geçiş modeli) kurulumu — ÇÖZÜCÜ KOŞMADAN doğrula.

NEDEN GEREKLİ: kOmegaSST hücum kenarından itibaren TAM TÜRBÜLANSLI çözer. Re=2.5e5'te
gerçek NACA2412'nin ön kordunun büyük kısmı laminerdir; tam-türbülans sınır tabakayı
aşırı kalınlaştırır → viskoz de-kamburlanma. Ölçülen imza tam bu: taşıma EĞİMİ doğru
(0.948·2π) ama α_L0 −0.81° (olması gereken −2.07°). Geometrinin doğru olduğu ayrıca
ölçüldü (grid yüzeyi girdi profilinden ≤6.5e-5 kord; grid kamberinden α_L0=−2.09°).

Bu testler eksik bir alanın/şemanın çözücüyü AÇIKLAMASIZ düşürmesini engeller —
`divSchemes default none` altında tanımsız her div terimi ölümcüldür.
"""
from pathlib import Path

import pytest

pytest.importorskip("numpy")
import construct2d_bridge as cb


def _kur(tmp_path, model):
    """run_validation'ın DOSYA YAZAN kısmını çalıştır; çözücüyü çağırma."""
    case = tmp_path / "c"
    for d in ("system", "constant/polyMesh", "0"):
        (case / d).mkdir(parents=True, exist_ok=True)
    (case / "constant" / "polyMesh" / "boundary").write_text("FoamFile{}\n(\n)\n")
    monkey = {}

    def sahte_run(*a, **k):
        monkey["kosuldu"] = True
        class R:
            returncode, stdout, stderr = 0, "", ""
        return R()
    orij = cb.subprocess.run
    cb.subprocess.run = sahte_run
    try:
        cb.run_validation(str(case), V=15.0, nu=6e-5, chord=1.0,
                          end_time=10, model=model)
    except Exception:
        pass                       # forces.dat yok — dosya yazimi zaten tamamlandi
    finally:
        cb.subprocess.run = orij
    return case


def test_LM_alanlari_yaziliyor(tmp_path):
    c = _kur(tmp_path, "kOmegaSSTLM")
    for f in ("gammaInt", "ReThetat"):
        assert (c / "0" / f).exists(), f"{f} alani yazilmadi — cozucu aciklamasiz duser"


def test_varsayilan_modelde_LM_alanlari_YAZILMIYOR(tmp_path):
    c = _kur(tmp_path, "kOmegaSST")
    assert not (c / "0" / "gammaInt").exists()
    assert not (c / "0" / "ReThetat").exists()


def test_momentumTransport_modeli_dogru(tmp_path):
    assert "kOmegaSSTLM" in (_kur(tmp_path, "kOmegaSSTLM")
                             / "constant" / "momentumTransport").read_text()
    assert "model kOmegaSST;" in (_kur(tmp_path, "kOmegaSST")
                                  / "constant" / "momentumTransport").read_text()


def test_div_semalari_TANIMLI(tmp_path):
    """`divSchemes default none` altinda tanimsiz div terimi cozucuyu dusurur."""
    s = (_kur(tmp_path, "kOmegaSSTLM") / "system" / "fvSchemes").read_text()
    assert "div(phi,gammaInt)" in s and "div(phi,ReThetat)" in s
    s0 = (_kur(tmp_path, "kOmegaSST") / "system" / "fvSchemes").read_text()
    assert "gammaInt" not in s0


def test_cozucu_ve_gevsetme_LM_alanlarini_kapsiyor(tmp_path):
    s = (_kur(tmp_path, "kOmegaSSTLM") / "system" / "fvSolution").read_text()
    assert "gammaInt" in s and "ReThetat" in s
    assert "gammaInt 0.5" in s and "ReThetat 0.5" in s


def test_ReThetat_serbest_akis_degeri_MAKUL(tmp_path):
    """Menter 2006 korelasyonu; Tu=0.18% icin Re_theta_t ~ 1140-1200."""
    import re
    s = (_kur(tmp_path, "kOmegaSSTLM") / "0" / "ReThetat").read_text()
    v = float(re.search(r"internalField uniform ([\d.]+)", s).group(1))
    assert 200.0 < v < 3000.0, f"ReThetat={v} fiziksel araligin disinda"
