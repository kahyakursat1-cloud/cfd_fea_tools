"""Salınım (limit çevrimi) hükme girmeli — "rezidüel düştü" yakınsama demek DEĞİL.

Ölçülen kusur: `salinim_analizi` vardı, `conv["salinim"]`e yazılıyordu ve HİÇBİR
tüketicisi yoktu — ne `sonuc_kapisi` ne rapor. Cd ±%4 salınırken drift ölçümü fazla
denk geldiği için %1.25 (limit %2) çıkıyor, rezidüeller de temiz olunca kapı
"✅ yakınsadı" diyordu.

Fiziksel gerekçe uydurma değil: geriye-basamaklı akış çapasında (Driver & Seegmiller,
Re_H=37500) p rezidüeli 4000→20000 iterasyon boyunca 7e-5…9e-5 bandında PLATOYA oturdu.
Kanonik eşiğin (1e-4) altında ama düşmüyor — kararlı SIMPLE bu akışta sabit noktaya
oturmuyor. Projenin kendi kodu da biliyordu: salinim_analizi docstring'i "küp dersi:
steady-SIMPLE keskin-kenar küt cisimde salınır" diyor.
"""
import math

import pytest

from validity_envelope import sonuc_kapisi
from vehicle_pipeline import DRIFT_LIMIT_PCT, salinim_analizi


def _salinan_tarihce(n=200, periyot=20, genlik=0.04, taban=1.0):
    return [taban + genlik * math.sin(2 * math.pi * i / periyot) for i in range(n)]


def test_ASIL_KUSUR_salinim_kapiyi_gecemez():
    """Drift ve rezidüel ölçütleri sağlanıyor ama çözüm salınıyor → 'yakınsadı' DENMEZ."""
    hist = _salinan_tarihce()
    sal = salinim_analizi(hist)
    assert sal["osilasyon"] is True, "dedektör salınımı görmeli"
    r = sonuc_kapisi({"verdict": "ok"},
                     {"drift_ok": True, "rezidual_ok": True, "salinim": sal})
    assert r["seviye"] == "uyari"
    assert "salınım" in r["etiket"].lower()
    assert any("SALINIYOR" in g for g in r["gerekce"])


def test_drift_olcumu_gercekten_kandirilabiliyor():
    """Kusurun ölçülen sebebi: drift son nokta ile %20-öncekini kıyaslar; salınım
    periyodu o pencereye denk gelirse ölçülen drift limitin ALTINDA çıkar."""
    hist = _salinan_tarihce()
    w = max(2, len(hist) // 5)
    drift = abs(hist[-1] - hist[-w]) / abs(hist[-1]) * 100
    assert drift < DRIFT_LIMIT_PCT, "senaryo geçersiz — drift zaten limiti aşıyor"
    assert salinim_analizi(hist)["genlik_pct"] > 2 * drift, (
        "gerçek genlik ölçülen driftten belirgin büyük olmalı")


def test_salinim_yoksa_temiz_kosu_hala_gecer():
    """Düzeltme yanlış alarma dönüşmemeli."""
    duz = [1.0 + 1e-6 * i for i in range(200)]
    sal = salinim_analizi(duz)
    r = sonuc_kapisi({"verdict": "ok"},
                     {"drift_ok": True, "rezidual_ok": True, "salinim": sal})
    assert r["seviye"] == "ok" and r["etiket"] == "✅ yakınsadı"


def test_salinim_alani_yoksa_geriye_uyumlu():
    """Eski sonuç sözlüklerinde 'salinim' yok — kapı düşmemeli, davranış değişmemeli."""
    r = sonuc_kapisi({"verdict": "ok"}, {"drift_ok": True, "rezidual_ok": True})
    assert r["seviye"] == "ok"


def test_kisa_tarihcede_dedektor_None_doner_ve_kapi_gecer():
    """min_n altında salınım ölçülemez; 'ölçülemedi' 'salınıyor' sayılmamalı."""
    assert salinim_analizi([1.0] * 10) is None
    r = sonuc_kapisi({"verdict": "ok"},
                     {"drift_ok": True, "rezidual_ok": True, "salinim": None})
    assert r["seviye"] == "ok"


def test_fizik_kapisi_salinimdan_ONCE_gelir():
    """Öncelik sırası bozulmamalı: fizik-dışı koşu salınım etiketiyle yumuşatılamaz."""
    r = sonuc_kapisi({"verdict": "inadmissible", "reasons": ["Cd sonlu değil"]},
                     {"drift_ok": True, "rezidual_ok": True,
                      "salinim": salinim_analizi(_salinan_tarihce())})
    assert r["seviye"] == "engel" and "fizik" in r["etiket"]


def test_belirsizligin_GCIya_girmedigi_soyleniyor():
    """En yanıltıcı durum: GCI dar çıkar, salınım genliği ondan büyüktür ve rapor
    yalnız GCI'yı gösterir. Gerekçe bunu AÇIKÇA söylemeli."""
    r = sonuc_kapisi({"verdict": "ok"},
                     {"drift_ok": True, "rezidual_ok": True,
                      "salinim": salinim_analizi(_salinan_tarihce())})
    g = " ".join(r["gerekce"])
    assert "GCI" in g and "GİRMEZ" in g


def test_rapor_salinimi_gosteriyor():
    """Kapı kurmak yetmez — mühendisin baktığı yere ulaşmalı."""
    import inspect

    import vehicle_report
    src = inspect.getsource(vehicle_report)
    i = src.index('conv.get("salinim")')
    assert "SALINIM VAR" in src[i:i + 800]
    assert "GCI" in src[i:i + 800], "genliğin GCI'ya girmediği raporda da yazmalı"


@pytest.mark.parametrize("genlik,beklenen", [(0.0005, False), (0.04, True)])
def test_esik_makul(genlik, beklenen):
    """Sayısal gürültü salınım sayılmamalı; gerçek limit çevrimi sayılmalı."""
    sal = salinim_analizi(_salinan_tarihce(genlik=genlik))
    assert sal["osilasyon"] is beklenen


def test_yplus_olculemedigi_SESSIZ_gecmiyor():
    """MiniHawk yeniden koşusunda ölçüldü: y⁺ ortalama 5399 (duvar tümüyle çözümsüz)
    ama `measure_yplus` geçici bir hatada `except: pass` ile düz None döndü ve kanıta
    `yplus: null` yazıldı. Böylece 'ölçülemedi' ile 'ölçüldü ve iyi' AYNI göründü,
    rapor da bu geometrinin en kritik sınırını hiç söyleyemedi."""
    import inspect

    import vehicle_pipeline
    src = inspect.getsource(vehicle_pipeline.measure_yplus)
    assert "olculemedi" in src and "neden" in src, "başarısızlık sebebi taşınmalı"
    assert "_yplus_dat_oku" in src, "diskte kalan yPlus.dat son çare olarak okunmalı"


def test_yplus_dat_yedegi_calisiyor(tmp_path):
    d = tmp_path / "postProcessing" / "yPlus" / "100"
    d.mkdir(parents=True)
    (d / "yPlus.dat").write_text(
        "# y+ ()\n# Time\tpatch\tmin\tmax\taverage\n"
        "100\tminihawk_prep\t2.10281027e+03\t6.92199628e+03\t5.39858893e+03\n")
    from vehicle_pipeline import _yplus_dat_oku
    r = _yplus_dat_oku(tmp_path, None)
    assert r["ort"] == pytest.approx(5398.59, abs=0.01)
    assert r["patch"] == "minihawk_prep"


def test_rapor_olculemedi_ile_iyi_yplusu_ayiriyor():
    import inspect

    import vehicle_report
    src = inspect.getsource(vehicle_report)
    i = src.index('yp.get("olculemedi")')
    assert "ÖLÇÜLEMEDİ" in src[i:i + 400]


def test_rapor_yuksek_yplusu_DUZ_LEVHA_capasina_bagliyor():
    """'y⁺ yüksek' NİTEL uyarısı yerine ölçülmüş hata büyüklüğü verilmeli."""
    import inspect

    import vehicle_report
    src = inspect.getsource(vehicle_report)
    i = src.index('yp["ort"] > 1000')
    assert "%40" in src[i:i + 500] and "Düz levha" in src[i:i + 500]
