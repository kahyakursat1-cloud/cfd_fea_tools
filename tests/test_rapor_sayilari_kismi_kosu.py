"""Kısmi üretim tek-kaynak dosyayı BUDAMAMALI.

ÖLÇÜLEN KUSUR (2026-08-15): `rapor_sayilari.py` `--test` bayrağı olmadan
koşulduğunda `gecen_test` anahtarı çıktı sözlüğünde hiç oluşmuyor ve dosya
üzerine yazılıyordu; tek-kaynak dosya sessizce kırpıldı. Tüketici (tez önerisi
kanıt denetimi) `KeyError` ile durdu, yani bu sefer gürültülüydü. Tehlikeli
olan ikizi ise sessiz: `cov.json` yoksa `kapsam_pct` de üretilmez, ama o
anahtar dosyada zaten varsa BAYAT bir değer olarak hayatta kalır ve raporlanır.

Beklenen davranış: eksik ölçüm eski değeri korur, ve hangi değerin taşındığı
dosyada yazılıdır — taşınan değer ile yeni ölçülen değer ayırt edilebilmelidir.
"""
import json
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def test_KISMI_kosu_onceki_anahtarlari_KORUR(tmp_path, monkeypatch):
    import importlib

    sys.path.insert(0, str(KOK / "experiments"))
    mod = importlib.import_module("rapor_sayilari")

    sahte_kok = tmp_path
    (sahte_kok / "experiments").mkdir()
    (sahte_kok / "tests").mkdir()
    (sahte_kok / "rapor_sayilari.json").write_text(
        json.dumps({"kod_satiri": 1, "gecen_test": 4242, "kapsam_pct": 99}),
        encoding="utf-8")
    monkeypatch.setattr(mod, "KOK", sahte_kok)
    monkeypatch.setattr(sys, "argv", ["rapor_sayilari.py"])   # --test YOK
    mod.main()

    d = json.loads((sahte_kok / "rapor_sayilari.json").read_text(encoding="utf-8"))
    assert d["gecen_test"] == 4242, "kısmi koşu tek-kaynak dosyayı BUDADI"
    assert "gecen_test" in d["_onceki_kosudan_tasinan"], "taşınan değer işaretlenmemiş"
    assert "kod_satiri" in d["_bu_kosuda_olculen"], "ölçülen değer işaretlenmemiş"
    assert "gecen_test" not in d["_bu_kosuda_olculen"]


def test_uretilen_dosya_TUKETICININ_bekledigi_anahtarlari_tasir():
    """Tez önerisi kanıt denetimi bu üç anahtarı okur; yokluğu onu durdurur."""
    d = json.loads((KOK / "rapor_sayilari.json").read_text(encoding="utf-8-sig"))
    for k in ("kod_satiri", "gecen_test", "kapsam_pct"):
        assert k in d, f"{k} yok — tez kanıt denetimi bu anahtarı okuyor"


def test_betik_calisir_durumda():
    r = subprocess.run([sys.executable, "-c", "import ast,pathlib;"
                        "ast.parse(pathlib.Path(r'experiments/rapor_sayilari.py')"
                        ".read_text(encoding='utf-8'))"],
                       cwd=KOK, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_KIRMIZI_suitten_test_sayisi_YAYIMLANMAZ(monkeypatch):
    """Düşen test varken KIRMIZILIK dosyaya yazılmalı.

    ÖLÇÜLEN KUSUR (2026-08-15): `_pytest_sayisi` yalnız "N passed" dizgisini
    okuyup pytest'in çıkış kodunu yok sayıyordu. Süitte 5 test düşmüşken
    üretici sorunsuz koştu ve "1593 geçen test" yazdı. Kırmızı süitten alınan
    sayı yanlış bir iddiadır: "1593 test geçiyor" diye okunur, doğrusu
    "1593 geçti, 5 düştü"dür.
    """
    import importlib
    import subprocess

    sys.path.insert(0, str(KOK / "experiments"))
    mod = importlib.import_module("rapor_sayilari")

    class SahteCikti:
        def __init__(self, ozet):
            self.stdout = "...\n" + ozet + "\n"

    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: SahteCikti("5 failed, 1593 passed, 2 skipped in 296s"))
    gecen, dusen = mod._pytest_sayisi([])
    assert (gecen, dusen) == (1593, 5), "kırmızılık görünür değil"

    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: SahteCikti("1598 passed, 2 skipped in 276s"))
    assert mod._pytest_sayisi([]) == (1598, 0), "yeşil süitte sayı üretilmedi"
