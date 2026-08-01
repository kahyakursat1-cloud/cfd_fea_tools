"""Sınıflandırıcı hedefi: PRESET DOĞRULUĞU ARTIK TEK BELİRLEYİCİ DEĞİL.

`nx_siniflandirici_testi` "preset doğruluğu = analiz ayarını gerçekten etkileyen
metrik" diyordu. O iddia preset'in tek karar olduğu dönemde doğruydu. İki şey
değişti:

  1. `ref_bump="oto"` eylem uzayına girdi. ÖLÇÜLDÜ ki y⁺'ı duvar-fonksiyonu
     bandına sokan tek kaldıraç odur (MiniHawk: bump +1/+2/+3 → y⁺ 340/112/61) —
     ve kademe SINIFTAN değil geometri+bütçeden hesaplanır. Sınıflandırıcı doğru
     da olsa yanlış da olsa aynı çıkar.
  2. Sınıf yalnız preset'i değil REJİMİ ve ANALİZ TİPİNİ de seçiyor. PRESET_MAP
     eşitliği bunu göremez: ucak/tilt_rotor/kanatli_vtol üçü de "ucak" preset'i
     ama serbest akım 25/22/20 m/s.

ÖLÇÜLEN FARK (2026-08-01, NX ayrık setler):
  kör set : preset %96.3 → ayar-eşdeğerliği %81.5 (1 AĞIR + 4 HAFİF)
  test set: preset %100  → ayar-eşdeğerliği %82.9 (0 AĞIR + 7 HAFİF)
Yani "preset %100" 7 vakada yanlış serbest-akım hızını gizliyordu.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from nx_siniflandirici_testi import ayar_farki  # noqa: E402


def test_ayni_tip_ESDEGER():
    assert ayar_farki("ucak", "ucak")["siddet"] == "ESDEGER"


def test_REJIM_degisimi_AGIR():
    """Süpersonik cd_mach yerine ses-altı tekil koşmak farklı bir çözücü ve
    farklı bir çıktıdır; iki sonuç kıyaslanamaz. Kör sette gerçekleşti
    (izgara_ld7: kanatli_roket → genel)."""
    f = ayar_farki("kanatli_roket", "genel")
    assert f["siddet"] == "AGIR"
    assert "rejim" in f["farkli_anahtarlar"] and "analiz" in f["farkli_anahtarlar"]


def test_preset_AYNI_ama_hiz_farkli_HAFIF_olarak_GORUNUYOR():
    """ASIL BULGU: PRESET_MAP her ikisini de 'ucak' der ve ölçüt 'hatasız' sayar;
    oysa serbest akım 22 yerine 25 m/s koşulur."""
    from auto_pilot import PRESET_MAP
    assert PRESET_MAP["tilt_rotor"] == PRESET_MAP["ucak"], "önkoşul değişmiş"
    f = ayar_farki("tilt_rotor", "ucak")
    assert f["siddet"] == "HAFIF"
    assert f["farkli_anahtarlar"] == ["hiz_ms"]
    assert f["gercek_ayar"]["hiz_ms"] == 22.0 and f["tahmin_ayar"]["hiz_ms"] == 25.0


def test_preset_farki_ORTA():
    """Aynı rejim/analiz/hız ama farklı preset: araba zemin düzlemi kurar."""
    f = ayar_farki("araba", "genel")
    assert f["siddet"] == "ORTA" and f["farkli_anahtarlar"] == ["vehicle_preset"]


def test_ayar_ayni_olsa_bile_PLAN_CEKINCESI_izleniyor():
    """Plan metni mühendislik çekincesi taşır ('tilt-rotor: bu analiz yalnız
    YATAY uçuş aerodinamiğidir'). Ayar aynı olsa da o uyarı kaybolabilir."""
    f = ayar_farki("kanatli_roket", "roket")
    assert f["siddet"] == "ESDEGER" and f["plan_uyarisi_degisti"] is True


def test_ref_bump_SINIFTAN_gelmiyor():
    """Eylem uzayının ölçülmüş en güçlü kaldıracı sınıfa bağlı DEĞİL; bu yüzden
    sınıflandırıcı doğruluğu tek başına analiz kalitesini belirleyemez."""
    from auto_pilot import apply_type_settings
    for tip in ("roket", "ucak", "multikopter", "genel"):
        cfg = apply_type_settings({"kalite": "standart", "guven": 1.0}, tip)
        assert "ref_bump" not in cfg, "ref_bump tipe göre seçiliyor olmamalı"


def test_OLCULEN_kanit_dosyalari_yeni_metrigi_iceriyor():
    for ad, esik in (("nx_siniflandirici_kor.json", 0.80),
                     ("nx_siniflandirici.json", 0.80)):
        p = ROOT / ad
        if not p.exists():
            continue
        o = json.loads(p.read_text(encoding="utf-8"))["ozet"]
        assert "ayar_esdegerlik" in o, f"{ad} eski metrikle kalmış"
        assert o["ayar_esdegerlik"] >= esik, (ad, o["ayar_esdegerlik"])
        # Yeni ölçüt preset'ten DAHA SIKI olmalı, yoksa hiçbir şey eklemiyordur.
        assert o["ayar_esdegerlik"] <= o["preset_dogruluk"]
