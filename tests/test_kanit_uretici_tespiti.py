"""kanit.uretici_kod — "yeniden üretilemez" AĞIR bir iddiadır, kanıtlanmalı.

ÖLÇÜLDÜ (2026-08-02): denetim 10 kanıt için "ÜRETİCİ KOD DEPODA YOK — yeniden
üretilemez" diyordu. Sekizinin üreticisi duruyordu; araç göremiyordu çünkü:

  (a) çıktı adı HESAPLANIYOR — exp_gci_xfine.py `f"gci_{lbl}.json"` yazar ve
      literal "gci_xfine.json" kaynakta HİÇ geçmez;
  (b) gevşek tarama yalnız adın İLK geçişine bakıyordu — ad önce bir sabitte
      (nx_siniflandirici_testi.py'nin CIKTI_JSON sözlüğü) geçip yazma çok
      aşağıda olduğunda üretici görünmez oluyordu.

Yani aracın İDDİASI KANITINDAN GÜÇLÜYDÜ — bu oturumun tekrarlayan kusuru, bu
kez denetleyicinin kendisinde. Gerçek sayı 10 değil 2.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import kanit  # noqa: E402


def _yaz(tmp, ad, govde):
    (tmp / ad).write_text(govde, encoding="utf-8")


def test_HESAPLANMIS_cikti_adi_bulunuyor(tmp_path, monkeypatch):
    monkeypatch.setattr(kanit, "ROOT", tmp_path)
    _yaz(tmp_path, "uretici.py",
         'lbl = sys.argv[1]\nPath(f"gci_{lbl}.json").write_text(json.dumps(out))\n')
    assert kanit.uretici_kod("gci_xfine.json") == "uretici.py"
    assert kanit.uretici_kod("gci_xxfine.json") == "uretici.py"


def test_kalip_DIZIN_sinirini_asmiyor(tmp_path, monkeypatch):
    """`{...}` dosya-adı parçasıdır; ayraç geçerse başka dizindeki kanıt
    yanlışlıkla üretilmiş sayılırdı."""
    monkeypatch.setattr(kanit, "ROOT", tmp_path)
    _yaz(tmp_path, "u.py", 'Path(f"raporlar/{ad}.json").write_text(x)\n')
    assert kanit.uretici_kod("raporlar/alt/gci.json") == ""


def test_ILK_gecis_degil_HER_gecis_taraniyor(tmp_path, monkeypatch):
    """Ad önce bir sabitte geçip yazma çok aşağıdaysa da bulunmalı."""
    monkeypatch.setattr(kanit, "ROOT", tmp_path)
    _yaz(tmp_path, "u.py",
         'CIKTI = {"test": "olcum.json"}\n' + "x = 1\n" * 40
         + 'Path(CIKTI["test"]).write_text(json.dumps(d))   # olcum.json\n')
    assert kanit.uretici_kod("olcum.json") == "u.py"


def test_YAZMA_yoksa_uretici_sayilmiyor(tmp_path, monkeypatch):
    """Dosya adını yalnız OKUYAN kod üretici değildir; yoksa her tüketici
    'üretici' sayılır ve 'yeniden üretilebilir' iddiası boşalırdı."""
    monkeypatch.setattr(kanit, "ROOT", tmp_path)
    _yaz(tmp_path, "okuyan.py", 'd = json.loads(open("olcum.json").read())\n')
    assert kanit.uretici_kod("olcum.json") == ""


def test_denetci_KENDI_dokumantasyonuyla_eslesmiyor():
    """kanit.py'nin yorumunda örnek olarak `gci_{lbl}.json` geçiyor ve araç
    kendini üretici sanıyordu."""
    assert kanit.uretici_kod("gci_xfine.json") != "kanit.py"


def test_GERCEK_depoda_uretici_yolu_donuyor():
    """Bu dosyalar depoda gerçekten üretilebilir; yol gösterilmeli ki komut
    yazılabilsin ('üretici var' demek onu koşmak için yetmiyordu)."""
    for ad, bekle in (("gci_xfine.json", "experiments/exp_gci_xfine.py"),
                      ("gci_cgrid_base.json", "experiments/exp_cgrid_run.py"),
                      ("gci_cgridP_smoke.json",
                       "experiments/exp_cgrid_run_parallel.py"),
                      ("tmr_gci_verdict_a8.json", "tmr_cfd/run_gci_campaign.py")):
        if (ROOT / bekle).exists():
            assert kanit.uretici_kod(ad) == bekle, ad


def test_ureticiler_komutu_ARTIK_kendileri_yaziyor():
    """Aynı körlük yeni koşularda tekrarlanmasın: çıktı adını hesaplayan
    scriptler `_uretim` alanını kanıta kendileri koymalı."""
    for yol in ("experiments/exp_gci_xfine.py", "experiments/exp_cgrid_run.py",
                "experiments/exp_cgrid_run_parallel.py",
                "tmr_cfd/run_gci_campaign.py"):
        p = ROOT / yol
        if p.exists():
            assert '"_uretim"' in p.read_text(encoding="utf-8"), yol


class TestOzgullukVeGerekce:
    """İki ayrı iddia karışıyordu ve ikisi de fazla güçlüydü."""

    def test_EN_OZGUL_kalip_kazaniyor(self, tmp_path, monkeypatch):
        """`gci_{lbl}.json` HER gci_*.json ile eşleşiyor. gci_cgrid_base.json için
        hem exp_gci_xfine.py hem exp_cgrid_run.py uyuyor; doğru cevap ikincisi."""
        monkeypatch.setattr(kanit, "ROOT", tmp_path)
        _yaz(tmp_path, "a_genel.py", 'Path(f"gci_{lbl}.json").write_text(x)\n')
        _yaz(tmp_path, "b_ozel.py", 'Path(f"gci_cgrid_{lbl}.json").write_text(x)\n')
        assert kanit.uretici_kod("gci_cgrid_base.json") == "b_ozel.py"
        assert kanit.uretici_kod("gci_xfine.json") == "a_genel.py"

    def test_LITERAL_eslesme_kalibi_yeniyor(self, tmp_path, monkeypatch):
        monkeypatch.setattr(kanit, "ROOT", tmp_path)
        _yaz(tmp_path, "a_kalip.py", 'Path(f"gci_{lbl}.json").write_text(x)\n')
        _yaz(tmp_path, "z_literal.py", 'Path("gci_xfine.json").write_text(x)\n')
        assert kanit.uretici_kod("gci_xfine.json") == "z_literal.py"
        assert kanit.uretici_kesin("gci_xfine.json") is True

    def test_kalip_eslesmesi_KESIN_sayilmiyor(self, tmp_path, monkeypatch):
        """"Bu script bu adda bir dosya YAZABİLİR" ile "bu dosyayı ÜRETMİŞTİR"
        aynı iddia değil; manifest ikisini ayrı göstermeli."""
        monkeypatch.setattr(kanit, "ROOT", tmp_path)
        _yaz(tmp_path, "u.py", 'Path(f"gci_{lbl}.json").write_text(x)\n')
        assert kanit.uretici_kod("gci_xfine.json") == "u.py"
        assert kanit.uretici_kesin("gci_xfine.json") is False

    def test_URETILEMEZ_gerekcesi_manifeste_giriyor(self, tmp_path, monkeypatch):
        """Gerekçesiz ❌ bilgi vermiyor; NEDEN üretilemediği eylem planı üretir."""
        import json as _j
        monkeypatch.setattr(kanit, "ROOT", tmp_path)
        p = tmp_path / "olcum.json"
        p.write_text(_j.dumps({"vaka": "x", "verdikt": "✅ ok",
                               "_uretilemez": "elle birlestirilmis ozet"}),
                     encoding="utf-8")
        k = kanit.sinifla(p)
        assert k["uretilemez_neden"] == "elle birlestirilmis ozet"
        assert "elle birlestirilmis ozet" in kanit.tablo([k])

    def test_GERCEK_iki_uretilemez_kanit_gerekce_tasiyor(self):
        """Depodaki iki gerçek vaka gerekçesiz kalmasın."""
        import json as _j
        for ad in ("mesh_independence.json", "supersonic_validation.json"):
            p = ROOT / ad
            if p.exists():
                d = _j.loads(p.read_text(encoding="utf-8"))
                assert d.get("_uretilemez"), ad
                assert kanit.uretici_kod(ad) == "", f"{ad} artik uretilebilir mi?"
