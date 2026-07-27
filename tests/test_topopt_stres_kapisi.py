"""Topoloji optimizasyonu stres kapısı — "kompliyans-körlüğü".

`vehicle_topopt` KOMPLİYANS minimize eder; kompliyans stresi kontrol ETMEZ. Yani
"optimal" bir tasarım akmayı aşabilir ve rakam (düşük kompliyans) yine de iyi görünür.
Kapı final tasarımı yeniden-analiz SF'siyle hükme bağlar. Modül %18 kapsamdaydı ve bu
karar mantığı hiç test edilmemişti.
"""
import pytest

from vehicle_topopt import _stress_gate


def test_guvenli_tasarim():
    r = _stress_gate({"emniyet_faktoru_temsili": 2.3})
    assert r["durum"] == "güvenli" and r["SF"] == 2.3
    assert r["mesaj"].startswith("✅")


def test_marjinal_bant():
    r = _stress_gate({"emniyet_faktoru_temsili": 1.2})
    assert r["durum"] == "marjinal"
    assert "KONTROL ETMEZ" in r["mesaj"], "kompliyans-körlüğü açıkça söylenmeli"


def test_akma_asildi_kompliyans_korlugu_adlandirilir():
    """En tehlikeli durum: tasarım kompliyans-OPTİMAL ama stres-GÜVENSİZ."""
    r = _stress_gate({"emniyet_faktoru_temsili": 0.8})
    assert r["durum"] == "akma_asildi"
    assert "kompliyans-körlüğü" in r["mesaj"]
    assert "stress_topopt" in r["mesaj"], "çözüm yolu gösterilmeli"


@pytest.mark.parametrize("sf,beklenen", [
    (1.5, "güvenli"), (1.49, "marjinal"), (1.0, "marjinal"), (0.99, "akma_asildi")])
def test_esik_sinirlari(sf, beklenen):
    assert _stress_gate({"emniyet_faktoru_temsili": sf})["durum"] == beklenen


def test_tekillik_robust_sf_tercih_edilir():
    """TO geometrisi jagged → tepe SF büyük olasılıkla SAHTE tekillik. Temsili SF
    varsa o kullanılmalı, tepe değil."""
    r = _stress_gate({"emniyet_faktoru_temsili": 2.0, "emniyet_faktoru": 0.4})
    assert r["SF"] == 2.0 and r["durum"] == "güvenli"


def test_temsili_yoksa_tepeye_duser():
    r = _stress_gate({"emniyet_faktoru": 1.8})
    assert r["SF"] == 1.8 and r["durum"] == "güvenli"


def test_sf_okunamazsa_guvenli_denmez():
    """Stres okunamadıysa sessizce 'güvenli' demek en tehlikeli hatadır."""
    for sa in ({}, {"emniyet_faktoru_temsili": None, "emniyet_faktoru": None}):
        r = _stress_gate(sa)
        assert r["durum"] == "değerlendirilemedi" and r["SF"] is None
        assert "GARANTİ ETMEZ" in r["mesaj"]


def test_kapi_sonuca_bagli():
    """Kapı hesaplanıp sonuç sözlüğüne yazılmalı — hesaplanıp atılırsa değersiz."""
    import inspect

    import vehicle_topopt
    src = inspect.getsource(vehicle_topopt)
    assert '"stres_kapisi": _stress_gate(' in src


def test_yuk_aktarilmamissa_guvenli_denmez():
    """En sinsi hata: yük hiç aktarılmamışsa SF ASTRONOMİK çıkar ve 1.5 eşiğini rahat
    geçer → "kompliyans-optimal tasarım stres-güvenli" denir. Oysa hiçbir şey test
    edilmemiştir. `sa` zaten fizik_kabul taşıyordu, kapı ona bakmıyordu."""
    sa = {"emniyet_faktoru_temsili": 5500.0,
          "fizik_kabul": {"verdict": "inadmissible",
                          "reasons": ["gerilme sayısal sıfır oysa 160 N yük uygulandı"]}}
    r = _stress_gate(sa)
    assert r["durum"] == "değerlendirilemedi" and r["SF"] is None
    assert "SF ANLAMSIZ" in r["mesaj"]
    assert "160 N" in r["mesaj"], "gerekçe taşınmalı"


def test_fizik_kapisi_okse_normal_hukum():
    sa = {"emniyet_faktoru_temsili": 2.3, "fizik_kabul": {"verdict": "ok", "reasons": []}}
    assert _stress_gate(sa)["durum"] == "güvenli"


def test_fizik_kapisi_yoksa_geriye_uyumlu():
    """Eski sonuç sözlüklerinde fizik_kabul yok — kapı düşmemeli."""
    assert _stress_gate({"emniyet_faktoru_temsili": 2.3})["durum"] == "güvenli"
