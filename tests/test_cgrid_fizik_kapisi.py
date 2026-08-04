"""C-grid koşucusu IRAKSAMIŞ çözümü `status: ok` diye kaydediyordu.

Kontrol yalnız "FOAM FATAL yok" ve "log 'End' ile bitti" diye bakıyordu. Ama
temiz biten bir koşu YAKINSAMIŞ demek değildir.

ÖLÇÜLDÜ (teshis_ilkhucre, Re=3.5e5 + ilk hücre 8e-6):
    SST  Cd = -0.24224                 negatif sürükleme — fiziksel değil
    LM   Cd = -691205.41  Cl = -11352049.28
ve script bunu `status: ok` diye KANIT dosyasına yazdı. Iraksamış bir çözümün
"başarılı" kaydedilmesi kanıt kütüphanesine çöp sokar — bu depoda avlanan
sınıfın en doğrudan hâli.
"""
import ast
from pathlib import Path

from validity_envelope import force_admissibility

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "experiments" / "exp_cgrid_run.py").read_text(encoding="utf-8")


def test_OLCULEN_iraksama_fizik_kapisindan_geciyor():
    r = force_admissibility(-691205.41037, -11352049.2825, 4.0)
    assert r["verdict"] == "inadmissible"
    assert any("sürükleme" in x for x in r["reasons"])


def test_NEGATIF_Cd_de_yakalaniyor():
    """SST aşaması Cd=-0.24 vermişti; 'küçük' negatif de fiziksel değildir."""
    assert force_admissibility(-0.24224, 1.1774, 4.0)["verdict"] == "inadmissible"


def test_YAKINSAK_kosu_gecerli_kaliyor():
    """Kapı yalnız çöpü elemeli; L4'ün gerçek değerleri geçmeli."""
    assert force_admissibility(0.01778, 0.1916, 4.0)["verdict"] == "ok"


def test_kosucu_status_ok_demeden_ONCE_kapiyi_cagiriyor():
    agac = ast.parse(SRC)
    metin = ast.dump(agac)
    assert "force_admissibility" in metin, "fizik kapısı hiç çağrılmıyor"
    i = SRC.index('out["status"]="ok"')
    onceki = SRC[max(0, i - 700):i]
    assert "force_admissibility" in onceki, "kapı 'ok' atamasından SONRA geliyor"
    assert "inadmissible" in onceki


def test_fizik_disi_AYRI_durum_olarak_kaydediliyor():
    """'ok değil' ile 'çöktü' aynı şey değil; kanıt bunu ayırt edebilmeli."""
    assert 'out["status"]="fizik_disi"' in SRC
    assert 'out["fizik_kabul"]' in SRC


def test_SST_asamasi_da_yargilaniyor():
    """Negatif Cd önce SST'de göründü; yalnız LM'e bakmak onu kaçırırdı."""
    assert 'out["SST_fizik"]' in SRC
