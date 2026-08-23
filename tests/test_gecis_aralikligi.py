"""Geçiş modeli koşusu DELİL mi, yoksa aynı kapanışın ikinci ölçümü mü?

`kOmegaSSTLM` bir kapanış SEÇİMİ değil bir kapanış İMKÂNIDIR. Aralıklılık
(gammaInt) her yerde 1 kalırsa üretim terimleri hiç sönmez ve model
tam-türbülanslı kOmegaSST'ye DEJENERE olur; o koşudan çıkan Cd/St sapması
kapanış hakkında hiçbir şey söylemez.

ÖLÇÜLDÜ (2026-08-23): TI=%1 ile gammaInt min 0,9869 / ortalama 1,0000 /
laminer hücre %0,0. Sapma (Cd %−27,55) tam-türbülanslı koşuyla (%−26,88)
neredeyse aynı çıktı. "Hipotez çürüdü" diye yazılsaydı YANLIŞ olurdu; koşu
hipotezi hiç sınamamıştı. Bu testler o hatayı elle değil KODLA engeller.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

import silindir_gecis_3b as g  # noqa: E402


def _yaz(case: Path, degerler: list[float]) -> None:
    (case / "0").mkdir(parents=True, exist_ok=True)
    d = case / "1.5"
    d.mkdir(parents=True, exist_ok=True)
    (d / "gammaInt").write_text(
        "internalField   nonuniform List<scalar>\n"
        f"{len(degerler)}\n(\n" + "\n".join(str(x) for x in degerler) + "\n)\n;\n")


def test_her_yerde_bir_ise_DEVREYE_GIRMEDI(tmp_path):
    _yaz(tmp_path, [1.0, 0.9869, 1.0, 0.999])
    a = g.aralik_denetimi(tmp_path)
    assert a["okunabildi"]
    assert a["devreye_girdi"] is False
    assert a["laminer_hucre_orani_pct"] == 0.0


def test_laminer_hucre_varsa_DEVREDE(tmp_path):
    _yaz(tmp_path, [1.0, 0.02, 0.31, 1.0])
    a = g.aralik_denetimi(tmp_path)
    assert a["devreye_girdi"] is True
    assert a["laminer_hucre_orani_pct"] == 50.0


def test_alan_yoksa_SESSIZCE_gecerli_sayilmaz(tmp_path):
    (tmp_path / "0").mkdir()
    (tmp_path / "2").mkdir()
    a = g.aralik_denetimi(tmp_path)
    assert a["okunabildi"] is False
    assert not a.get("devreye_girdi")


def test_devreye_girmeyen_kosu_HIPOTEZI_CURUTMUS_SAYILMAZ():
    """En kritik nokta: sonuçsuzluk ile çürütme AYNI SÖZCÜKLERLE yazılamaz."""
    aralik = {"min": 0.9869, "laminer_hucre_orani_pct": 0.0,
              "devreye_girdi": False}
    v = g._verdikt(False, aralik, {"sapma_pct": {"Cd": -27.55, "St": 30.22}}, "")
    assert "SONUÇSUZ" in v
    assert "hipotez ÇÜRÜMEDİ" in v
    # ÖLÇÜT İDDİAYA BAĞLI, KELİMEYE DEĞİL. İlk sürüm çıplak "ÇÜRÜDÜ" arıyordu
    # ve metne "Tu açıklaması SINANDI ve ÇÜRÜDÜ" cümlesi girince düştü ---
    # oysa çürüyen şey hipotez değil, sebebe dair İLK AÇIKLAMAYDI. Yasak olan
    # HİPOTEZİ çürümüş ilan etmek.
    assert "HİPOTEZ ÇÜRÜDÜ" not in v
    assert "delil değildir" in v


def test_devredeyken_iki_sapma_da_duzelmezse_CURUDU():
    aralik = {"min": 0.02, "laminer_hucre_orani_pct": 12.0,
              "devreye_girdi": True}
    v = g._verdikt(True, aralik, {"sapma_pct": {"Cd": -30.0, "St": 35.0}}, "")
    assert "ÇÜRÜDÜ" in v


def test_devredeyken_tek_sapma_duzelirse_EKSIK():
    """Yalnız biri düzelirse açıklama EKSİKTİR — 'destekledi' denemez."""
    aralik = {"min": 0.02, "laminer_hucre_orani_pct": 12.0,
              "devreye_girdi": True}
    v = g._verdikt(True, aralik, {"sapma_pct": {"Cd": -10.0, "St": 35.0}}, "")
    assert "EKSİK" in v and "DESTEKLENDİ" not in v


def test_kapanis_hukmu_gecis_modelini_KOSULSUZ_ONERMIYOR():
    """Sınanmamış bir öneri, ölçülmüş gibi yazılamaz."""
    import validity_envelope as v
    r = v.subkritik_kapanis_hukmu("bluff", 5.0e4, "kOmegaSST")
    assert r["tetiklendi"]
    h = r["hukum"]
    assert "KOŞULLUDUR" in h, "geçiş modeli koşulsuz öneriliyor"
    assert "gammaInt" in h, "aralıklılık denetimi hükümde yazılı değil"


def test_kanonik_denetim_URETIM_YOLUNDAN_cagriliyor():
    """Bu deponun baskın kusuru: kapı VAR ama üretim yolu onu çağırmıyor."""
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    assert "gecis_devrede_mi" in src, "kanonik denetim üretim yolunda YOK"
    i = src.index("gecis_devrede_mi(")
    blok = src[i:i + 900]
    assert "DEVREYE GİRMEDİ" in blok, "devreye girmeyen koşu uyarı üretmiyor"
    assert "uyarilar.insert(0" in blok, "uyarı listenin başına konmuyor"
    # YOKLUK 'devrede' SAYILMAZ — okunamama sessizce gecerlilige donusmemeli
    assert "ÖLÇÜLEMEDİ" in blok


def test_TU_ON_KOSULU_geri_cekildigi_KAYITLI():
    """Denenip ölçümle çürütülen bir kural, sessizce silinmez — kayda geçer.

    Tu>%0,5 sert reddi yazıldı; sonra küre çapası (aynı TI=%1) devreye
    girmiş bulundu ve kural çalışan bir çapayı öldürecekti. Geri çekiliş
    kodda yazılı olmalı ki aynı kural üçüncü kez yazılmasın.
    """
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    i = src.index("def gecis_modeli_onkosulu(")
    govde = src[i:src.index("\ndef ", i + 10)]
    assert "GERI CEKILDI" in govde, "geri çekiliş kayda geçmemiş"
    assert "kure" in govde.lower() and "1,05" in govde, "dayanak sayı yok"
    # Sert red GERCEKTEN kalkmis olmali — not yazip dali birakmak, geri
    # cekilmis gibi gorunup hala reddetmek olurdu.
    assert "TU_GECIS" not in govde, "geri çekilen Tu reddi hâlâ kapıda"
    assert "return (" not in govde.split("GERI CEKILDI")[1], (
        "geri çekiliş notundan sonra hâlâ bir red dalı var")


def test_iki_capa_ayni_Tu_da_ZIT_sonuc_verdi():
    """Kuralın neden geri çekildiğinin ÖLÇÜLMÜŞ dayanağı — arşivlerden."""
    from analysis.openfoam_runner import gecis_devrede_mi
    kure = KOK / "validation_anchors_runs" / "_anchor_sphere" / "_anchor_sphere"
    sil = KOK / "_silindir_gecis_3b"
    if not (kure.exists() and sil.exists()):
        import pytest
        pytest.skip("koşu arşivleri yok (gitignore)")
    a, b = gecis_devrede_mi(kure), gecis_devrede_mi(sil)
    assert a["devrede"] is True and b["devrede"] is False, (
        "iki arşiv artık ayrışmıyor — Tu'nun ön koşul OLMADIĞI dayanağı düştü")


def test_DEVREDE_ile_GECERLI_ayri_kapilar():
    """Küre çapası: aralıklılık DEVREDE ama y⁺=59 — duvar kapısı reddediyor.

    İki kapı birbirinin yerine okunursa ikisi de boşa çıkar: model yürüyor
    diye ağ yeterli olmaz, ağ yeterli diye model yürümüş olmaz.
    """
    from validity_envelope import duvar_hukmu
    kure = {"yplus": {"ort": 59.08, "min": 1.27, "max": 213.96},
            "katman_olcumu": {"durum": "kismi", "istenen": 10, "eklenen": 0.535}}
    ok, _ = duvar_hukmu(kure, "kOmegaSSTLM")
    assert ok is False, "duvar kapısı küre koşusunu geçiriyor"

    yol = KOK / "validation_anchors_runs" / "_anchor_sphere" / "_anchor_sphere"
    if not yol.exists():
        import pytest
        pytest.skip("çapa arşivi yok (gitignore)")
    from analysis.openfoam_runner import gecis_devrede_mi
    assert gecis_devrede_mi(yol)["devrede"] is True, (
        "aynı koşu hem devre-dışı hem duvar-reddi olsaydı ayrım örneklenemezdi")


def _nut_yaz(case, tip: str) -> None:
    (case / "0").mkdir(parents=True, exist_ok=True)
    (case / "0" / "nut").write_text(
        "boundaryField\n{\n  duvar { type %s; value uniform 0; }\n}\n" % tip)


def test_kurulum_denetimi_LOG_YASASI_dayatanini_reddediyor(tmp_path):
    """Ölçülen kök sebep: `nutkWallFunction` laminer bölgede nut→0'ı imkânsız
    kılar; geçiş modelinin üretebileceği tek şey tam-türbülanslı çözümdür."""
    from analysis.openfoam_runner import gecis_kurulum_denetimi
    _nut_yaz(tmp_path, "nutkWallFunction")
    r = gecis_kurulum_denetimi(tmp_path)
    assert r["uygun"] is False
    assert "nutkWallFunction" in r["_neden"]
    assert "nutLowReWallFunction" in r["_neden"], "uyumlu seçenek söylenmiyor"


def test_kurulum_denetimi_UYUMLULARI_geciriyor(tmp_path):
    from analysis.openfoam_runner import gecis_kurulum_denetimi
    for tip in ("nutLowReWallFunction", "nutUSpaldingWallFunction"):
        _nut_yaz(tmp_path, tip)
        assert gecis_kurulum_denetimi(tmp_path)["uygun"] is True, tip


def test_kurulum_denetimi_YOKLUGU_uygun_saymiyor(tmp_path):
    from analysis.openfoam_runner import gecis_kurulum_denetimi
    assert gecis_kurulum_denetimi(tmp_path)["uygun"] is None
    _nut_yaz(tmp_path, "bilinmeyenBirSey")
    assert gecis_kurulum_denetimi(tmp_path)["uygun"] is None


def test_kurulum_denetimi_KANONIK_YAZICIDAN_sonra_cagriliyor():
    """Kapı VAR ama üretim yolu çağırmıyorsa kapı yoktur."""
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    assert "raise ValueError(f\"GECIS MODELI KURULUMU:" in src, (
        "kurulum denetimi build_case sonunda çağrılmıyor")
    i = src.index("_kd = gecis_kurulum_denetimi(case_dir)")
    assert "GECIS_MODELLERI" in src[max(0, i - 300):i], (
        "denetim geçiş-modeli koşuluna bağlı değil")


def test_TU_ACIKLAMASI_curudugu_KAYITLI():
    """İlk sebep açıklaması (Tu) sınandı ve çürüdü — kayda geçmeli.

    Tu %1 ve %0,1: gammaInt minimumu 0,9869 ve 0,9867. On kat girdi farkı,
    sonuçta fark yok. Çürüyen açıklamayı silmek, onu üçüncü kez yazdırır.
    """
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    i = src.index("def gecis_kurulum_denetimi(")
    govde = src[i:src.index("\ndef ", i + 10)]
    assert "0,9869" in govde and "0,9867" in govde, "iki ölçüm de yazılı değil"
    assert "Tu değildi" in govde or "Sebep Tu değildi" in govde


def test_DUZGUN_alan_da_okunuyor(tmp_path):
    """Aralıklılık gerçekten her yerde 1 ise OpenFOAM `uniform 1` yazar —
    liste bekleyip pas geçmek, tam da aranan kusuru gizlerdi."""
    from analysis.openfoam_runner import gecis_devrede_mi
    (tmp_path / "3").mkdir(parents=True)
    (tmp_path / "3" / "gammaInt").write_text(
        "dimensions [0 0 0 0 0 0 0];\ninternalField   uniform 1;\n")
    a = gecis_devrede_mi(tmp_path)
    assert a["okunabildi"] and a["devrede"] is False and a["n"] == 1


def test_ayristirma_sorunu_YUTULMUYOR(tmp_path):
    """Sebep taşınmazsa 'alan yok' ile 'alan bozuk' aynı görünür."""
    from analysis.openfoam_runner import gecis_devrede_mi
    (tmp_path / "5").mkdir(parents=True)
    (tmp_path / "5" / "gammaInt").write_text("bambaska bir icerik\n")
    a = gecis_devrede_mi(tmp_path)
    assert a["okunabildi"] is False
    assert "ayrıştırılamadı" in a["_neden"], a["_neden"]


def _v():
    from validity_envelope import VALIDATED, Verdict
    return [Verdict("C_D", VALIDATED, True, "ok", "X", {})]


def test_devreye_girmeyen_kosu_TASARIM_SINIFINDAN_iniyor():
    from validity_envelope import TREND, apply_gecis_gate
    o = apply_gecis_gate(
        _v(), {"devrede": False, "min": 0.9869,
               "laminer_hucre_orani_pct": 0.0}, "kOmegaSSTLM")[0]
    assert o.klass == TREND and o.kod == "GECIS_DEVREDE_DEGIL"
    # SAYI GEREKCEDE DURSUN — hukum denetlenebilir olmali
    assert "0.9869" in o.message and "%0.0" in o.message


def test_devredeyken_kapi_SUSUYOR():
    from validity_envelope import VALIDATED, apply_gecis_gate
    o = apply_gecis_gate(
        _v(), {"devrede": True, "min": 0.0206,
               "laminer_hucre_orani_pct": 1.05}, "kOmegaSSTLM")[0]
    assert o.klass == VALIDATED, "devredeki koşu haksız yere indiriliyor"


def test_OLCULEMEDI_sessiz_inmeye_donusmuyor():
    """Ölçememek ile kusur bulmak aynı şey değil — sebep yazılamadan inilmez."""
    from validity_envelope import VALIDATED, apply_gecis_gate
    o = apply_gecis_gate(_v(), {"devrede": None}, "kOmegaSSTLM")[0]
    assert o.klass == VALIDATED
    o2 = apply_gecis_gate(_v(), None, "kOmegaSSTLM")[0]
    assert o2.klass == VALIDATED


def test_gecis_disi_modelde_kapi_hic_calismiyor():
    from validity_envelope import VALIDATED, apply_gecis_gate
    o = apply_gecis_gate(_v(), {"devrede": False, "min": 0.99,
                                "laminer_hucre_orani_pct": 0.0},
                         "kOmegaSST")[0]
    assert o.klass == VALIDATED


def test_model_listesi_TEK_KAYNAKTAN():
    """İkinci bir demet yazmak, listeyi genişletenin kapıyı atlamasına yol açar."""
    src = (KOK / "validity_envelope.py").read_text(encoding="utf-8")
    i = src.index("def apply_gecis_gate(")
    govde = src[i:src.index("\ndef ", i + 10)]
    assert "from analysis.openfoam_runner import GECIS_MODELLERI" in govde
    assert 'kOmegaSSTLM"' not in govde.split('"""')[2], "model adı gövdede sabit"


def test_kapi_IKI_KANALDA_da_cagriliyor():
    """Bir kanalda görünüp öbüründe susmak bu deponun tekrarlayan kusuru."""
    for dosya in ("hizmet.py", "app_analyzer.py"):
        src = (KOK / dosya).read_text(encoding="utf-8")
        assert "_gecis_kapisi(v, r)" in src, f"{dosya}: geçiş kapısı YOK"


def test_kanit_dosyasi_SONUCSUZLUGU_tasiyor():
    """Sonuçsuz koşunun kaydı silinmemeli: en öğretici parça o."""
    y = KOK / "silindir_gecis_3b.json"
    if not y.exists():
        import pytest
        pytest.skip("kanıt dosyası yok")
    d = json.loads(y.read_text(encoding="utf-8"))
    assert d["sinav_gecerli"] is False
    assert d["aralik_denetimi"]["laminer_hucre_orani_pct"] == 0.0
    assert "SONUÇSUZ" in d["verdikt"]
