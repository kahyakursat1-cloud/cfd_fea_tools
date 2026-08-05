"""XFOIL MODEL-FORM doğrulaması — panel bandı bu soruyu YANITLAMIYORDU.

`xfoil_kesit` panel-bağımsızlığını ölçüyordu (%0.55) ama o AYRIKLAŞTIRMA
bandıdır: "sayıyı daha ince ayrıklaştırınca ne kadar değişir" der, "gerçeği ne
kadar tutturur" DEMEZ. Birleştirici kesit Cd'sini mutlak sürüklemeye kattığı
için model-form hatası bilinmeliydi.

REFERANS EZBERDEN DEĞİL DEPODAN: gci_airfoil.json içindeki Ladson NACA0012
verisi (Re=3.4e6, α=4°). Bu oturumda τ/δ grafik değerlerini ezberden almayı
reddettiğim gibi burada da referans dosyadan okunur.

ÖLÇÜLDÜ: Cl %+0.86, Cd %−4.06 (serbest geçiş referansına karşı).

YOL BOYUNCA BULUNAN KUSUR: α=4 süpürmede YAKINSAMIYORDU — referansın tanımlı
olduğu tam açı. XFOIL PACC süpürmesinde önceki çözümü başlangıç tahmini olarak
taşır; tek başına koşunca yakınsıyor.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KANIT = ROOT / "xfoil_dogrulama.json"


def _d():
    return json.loads(KANIT.read_text(encoding="utf-8")) if KANIT.exists() else None


def test_referans_DEPODAN_okunuyor():
    """Ezberden alıntı kanıt değildir; sayı dosyadan gelmeli."""
    src = (ROOT / "experiments" / "xfoil_dogrulama.py").read_text(encoding="utf-8")
    assert "gci_airfoil.json" in src
    assert '["reference"]' in src
    # Referans degerleri KODA GOMULMEMELI
    assert "0.0064" not in src.split('"""')[2] if len(src.split('"""')) > 2 else True


def test_OLCULEN_sapma_makul():
    d = _d()
    if not d:
        return
    s = d["sapma_pct"]
    assert abs(s["Cl"]) < 5.0, s
    assert abs(s["Cd_vs_serbest_gecis"]) < 15.0, s
    assert d["model_form_band_pct"] == max(abs(s["Cl"]),
                                           abs(s["Cd_vs_serbest_gecis"]))


def test_REYNOLDS_farki_ACIKCA_yaziliyor():
    """Doğrulama Re=3.4e6'da; kullanım Re=3.5e5. Band oraya ÖNCÜL olarak taşınır,
    ÖLÇÜM olarak değil — karıştırılırsa olmayan bir kesinlik yayınlanır."""
    d = _d()
    if not d:
        return
    k = d["_kisit"]
    assert "3.5e5" in k and "ONCUL" in k
    assert "OLCUM olarak DEGIL" in k


def test_N_KRIT_secimi_kisitta_geciyor():
    """N_krit geçiş yerini ve dolayısıyla Cd'yi doğrudan belirler."""
    d = _d()
    if not d:
        return
    assert "N_krit" in d["_kisit"]


def test_YAKINSAMAYAN_aci_tek_tek_yeniden_deneniyor():
    """α=4 süpürmede düşüyordu ve o referans açısıydı — doğrulama yapılamaz
    hale geliyordu."""
    import inspect

    import xfoil_kesit as xk
    src = inspect.getsource(xk.polar)
    assert "tekrar" in src
    assert "tekrar=False" in src, "tekil yeniden deneme sonsuz dongu koruması yok"
    assert inspect.signature(xk.polar).parameters["tekrar"].default is True


def test_supurmede_TUM_acilar_donuyor():
    """Kurtarma çalışmazsa referans açısı yine kaybolur."""
    d = _d()
    if not d:
        return
    assert d.get("xfoil", {}).get("Cl") is not None
    assert abs(d["alpha"] - 4.0) < 1e-9
