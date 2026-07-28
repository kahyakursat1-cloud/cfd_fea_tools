"""Harici araç keşfi — Docker'a taşınmanın ön koşulu.

Uygulama Docker imajında Linux'ta koşacak. Önceki durumda OpenVSP/OpenRocket yolları
DÖRT dosyaya mutlak Windows yolu olarak gömülüydü ve bulunamadıklarında `pipeline.py`
"bulunamadi — atlandi" deyip None dönüyordu: raporda VSPAERO bölümü EKSİK görünür,
HATALI görünmezdi. Bu testler hem sıralamayı hem de "sebebini söyleme" borcunu bağlar.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import dis_araclar

KOK = Path(__file__).resolve().parent.parent


def test_ENV_degiskeni_varsayilani_EZER(tmp_path, monkeypatch):
    sahte = tmp_path / "OpenRocket.jar"
    sahte.write_text("x")
    monkeypatch.setenv("OPENROCKET_JAR", str(sahte))
    r = dis_araclar.bul("openrocket_jar")
    assert r["yol"] == str(sahte) and r["kaynak"] == "ENV"


def test_ENV_gecersizse_ARAMA_DEVAM_EDER(tmp_path, monkeypatch):
    """Yanlış ayarlanmış bir değişken keşfi ÖLDÜRMEMELİ, sadece kayda geçmeli."""
    monkeypatch.setenv("OPENROCKET_JAR", str(tmp_path / "yok.jar"))
    r = dis_araclar.bul("openrocket_jar")
    assert any("OPENROCKET_JAR=" in a for a in r["aranan"])


def test_bulunamayan_arac_NEREYE_BAKTIGINI_soyler(monkeypatch):
    """'Bulunamadı' tek başına eyleme geçirilebilir bilgi değildir."""
    monkeypatch.setitem(dis_araclar.ARACLAR, "hayali",
                        {"aciklama": "yok", "env": "HAYALI_ARAC",
                         "path_isim": ["kesinlikle_yok_boyle_bir_program"],
                         "varsayilan": ["/hic/olmayan/yol"]})
    r = dis_araclar.bul("hayali")
    assert r["yol"] is None
    assert "HAYALI_ARAC" in r["neden"]
    assert "/hic/olmayan/yol" in r["aranan"]
    assert any("PATH:" in a for a in r["aranan"])


def test_dizin_bekleyen_arac_DOSYAYI_kabul_etmez(tmp_path, monkeypatch):
    d = tmp_path / "sahte.jar"
    d.write_text("x")
    monkeypatch.setenv("JAVA_HOME", str(d))
    r = dis_araclar.bul("java_home")
    assert r["kaynak"] != "ENV"          # dosya verildi, dizin bekleniyor


def test_tanimsiz_arac_SESSIZCE_None_donmez():
    with pytest.raises(KeyError):
        dis_araclar.bul("boyle_bir_arac_yok")


def test_CLI_eksik_varsa_SIFIR_DISI_cikis_kodu_verir(monkeypatch, capsys):
    """Docker imaj doğrulaması buna dayanacak: `python dis_araclar.py` başarısızsa
    build kırılmalı, sessizce eksik bir imaj yayınlanmamalı."""
    monkeypatch.setattr(dis_araclar, "ARACLAR", {
        "hayali": {"aciklama": "yok", "env": "HAYALI_ARAC",
                   "path_isim": [], "varsayilan": ["/hic/olmayan/yol"]}})
    assert dis_araclar.main() == 1
    assert "arandi" in capsys.readouterr().out


def test_CLI_hepsi_bulunursa_SIFIR_doner(monkeypatch, tmp_path):
    v = tmp_path / "var.jar"
    v.write_text("x")
    monkeypatch.setattr(dis_araclar, "ARACLAR", {
        "hayali": {"aciklama": "var", "env": "HAYALI_ARAC",
                   "path_isim": [], "varsayilan": [str(v)]}})
    assert dis_araclar.main() == 0


def test_ZORUNLU_OLMAYAN_arac_hazir_hukmunu_dusurmez(monkeypatch):
    """openvsp_dll yalnız Windows'ta zorunlu; Linux imajında yokluğu kurulumu
    başarısız SAYMAMALI (kütüphane rpath/LD_LIBRARY_PATH ile bulunur)."""
    monkeypatch.setattr(dis_araclar, "ARACLAR", {
        "opsiyonel": {"aciklama": "yok", "env": "OPS", "zorunlu": False,
                      "path_isim": [], "varsayilan": ["/hic/olmayan/yol"]}})
    assert dis_araclar.rapor()["hazir"] is True


def test_koprulerde_MUTLAK_WINDOWS_YOLU_kalmadi():
    """Docker'da kırılacak her gömülü yol burada yakalanır."""
    import re
    desen = re.compile(r"r?[\"'][A-Za-z]:[\\/]")
    kirli = []
    for ad in ("openvsp_bridge.py", "openrocket_bridge.py", "pipeline.py",
               "mesh_generator.py"):
        for i, satir in enumerate((KOK / ad).read_text(encoding="utf-8").splitlines(), 1):
            if desen.search(satir) and "dis_araclar" not in satir:
                kirli.append(f"{ad}:{i}")
    assert not kirli, f"gomulu mutlak yol: {kirli}"


def test_dis_araclar_TEK_KAYNAK_ve_varsayilanlari_iki_platformu_kapsar():
    for ad, t in dis_araclar.ARACLAR.items():
        assert t.get("varsayilan"), f"{ad}: varsayilan yok"
        assert t.get("env"), f"{ad}: ortam degiskeni tanimlanmamis"


def test_rapor_JSON_serilestirilebilir():
    json.dumps(dis_araclar.rapor(), ensure_ascii=False)
