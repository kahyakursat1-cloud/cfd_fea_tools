"""Yük bütünlüğü: basınç-yalnız aktarım tasarım-sınıfı alamaz.

ÖLÇÜMDEN DOĞDU. `coupling_fsi` varsayılan olarak yalnız BASINÇ taşır ve bu,
adın gizlediği bir kapsam sınırıydı. Turek--Hron bayrağında çözücünün kendi
yüzey integrali viskoz eksenel kuvveti basıncınkinin **9,6 katı** verdi; uç
yer değiştirmesinin x bileşeni bir mertebe yanlış çıktı ve kanal açılınca
sapma %1,3'e indi.

Daha da önemlisi: deponun 195 kuvvet kaydının **138'inde** basınç/viskoz
ayrımı hiç yazılmamış (üretim araç yolu dâhil). Yani o vakalarda cevap
``önemsiz'' değil ``BİLİNMİYOR'' --- ve yokluk iyilik sayılamaz.

KAPI ÜÇ DALLI ve üçü de açık:
  * kayma taşındı           -> sınıf düşmez
  * pay ölçüldü ve küçük    -> sınıf düşmez
  * pay ölçülmedi ya da büyük -> EĞİLİM

`yuk_bileseni=None` ise kural HİÇ çalışmaz: elle uygulanan yükte ya da
modal analizde CFD aktarımı yoktur ve ilgisiz bir sonucu sıkmak yanlış
olurdu. Bu, kapının yanlış-pozitif tarafıdır ve ayrıca sınanır.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

from validity_envelope import (  # noqa: E402
    TREND,
    VALIDATED,
    classify_fea,
    overall_class,
)


def _kod(v):
    return [x.kod for x in v]


def test_YUK_CFDDEN_GELMIYORSA_KURAL_CALISMAZ():
    """YANLIŞ-POZİTİF KAPISI. Elle yüklenen bir braket ya da modal analiz
    bu kuraldan etkilenmemeli; etkilenirse kapı ilgisiz sonuçları sıkar."""
    v = classify_fea(yuk_bileseni=None)
    assert overall_class(v) == VALIDATED
    assert not [k for k in _kod(v) if k.startswith("FEA_YUK")]


def test_KAYMA_TASINDIYSA_SINIF_DUSMEZ():
    v = classify_fea(yuk_bileseni={"kayma_tasindi": True})
    assert overall_class(v) == VALIDATED
    assert "FEA_YUK_TAM" in _kod(v)


def test_PAY_OLCULMEDIYSE_SINIF_DUSER():
    """Asıl iddia: yokluk 'küçük' sayılamaz. 138 kayıtta durum tam budur."""
    v = classify_fea(yuk_bileseni={"kayma_tasindi": False,
                                   "viskoz_pay_pct": None})
    assert overall_class(v) == TREND
    assert "FEA_YUK_VISKOZ_BILINMIYOR" in _kod(v)
    assert all(x.design_safe is False for x in v
               if x.kod == "FEA_YUK_VISKOZ_BILINMIYOR")


def test_PAY_KUCUKSE_SINIF_DUSMEZ():
    """Bandın öbür yüzü. Kapı her basınç-yalnız koşuyu düşürseydi, ölçülen
    16 ailenin yedisini gereksiz yere eğilime indirirdi."""
    v = classify_fea(yuk_bileseni={"kayma_tasindi": False,
                                   "viskoz_pay_pct": 2.0})
    assert overall_class(v) == VALIDATED
    assert "FEA_YUK_TAM" in _kod(v)


def test_PAY_BUYUKSE_SINIF_DUSER():
    """Turek-Hron bayrağı: pay %410. Bu düşmezse kapı âtıldır."""
    v = classify_fea(yuk_bileseni={"kayma_tasindi": False,
                                   "viskoz_pay_pct": 410.0})
    assert overall_class(v) == TREND
    assert "FEA_YUK_VISKOZ_BUYUK" in _kod(v)


def test_ESIK_TEK_KAYNAKTAN_OKUNUYOR():
    """Eşik kopyalanırsa iki yer ayrışır ve biri sessizce eskir. Kapı onu
    tarama betiğinden okur; geri düşüş değeri de AYNI olmalı."""
    from kayma_payi import ESIK_PCT

    from validity_envelope import _viskoz_esik_pct
    assert _viskoz_esik_pct() == ESIK_PCT
    # Esigin HEMEN ustu ve alti farkli siniflandirilmali --- yoksa esik
    # okunuyor ama KULLANILMIYOR olabilir.
    alt = classify_fea(yuk_bileseni={"kayma_tasindi": False,
                                     "viskoz_pay_pct": ESIK_PCT - 0.1})
    ust = classify_fea(yuk_bileseni={"kayma_tasindi": False,
                                     "viskoz_pay_pct": ESIK_PCT + 0.1})
    assert overall_class(alt) == VALIDATED
    assert overall_class(ust) == TREND


def test_MESAJ_COZUMU_ONERIYOR():
    """Bir kapı ne yapılacağını söylemezse kullanıcı onu kapatır."""
    v = classify_fea(yuk_bileseni={"kayma_tasindi": False,
                                   "viskoz_pay_pct": None})
    m = next(x.message for x in v if x.kod == "FEA_YUK_VISKOZ_BILINMIYOR")
    assert "forces" in m and "kayma=True" in m


def test_ENVANTER_KANITI_KAPIYI_DESTEKLIYOR():
    """Kapının gerekçesi ölçülmüş olmalı, hatırlanmış değil: taramada
    okunamayan kayıt gerçekten var mı?"""
    import json
    kanit = KOK / "kayma_payi.json"
    if not kanit.exists():
        import pytest
        pytest.skip("kayma_payi.json yok")
    d = json.loads(kanit.read_text(encoding="utf-8"))
    cevapsiz = sum(c["dosya"] for c in d["cevapsiz_aile"])
    assert cevapsiz > 0, (
        "ayrımı olmayan kayıt kalmadıysa 'bilinmiyor' dalının gerekçesi "
        "zayıflar; kapı kalabilir ama kayıt güncellenmeli")


def test_URETIM_YOLU_KAPIYI_GERCEKTEN_SURUYOR():
    """Kapı doğru çalışabilir ama üretim yolu ona `yuk_bileseni`
    vermiyorsa savunma âtıldır --- bu deponun baskın kusuru ve bugün
    ikinci kez aynı sınıf.

    Ölçüt METNE değil ÇAĞRIYA bağlanır: `classify_fea` çağrısı anahtar
    kelimeyi taşımalı."""
    import ast
    src = (KOK / "vehicle_fea.py").read_text(encoding="utf-8")
    agac = ast.parse(src)
    cagrilar = [n for n in ast.walk(agac)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "classify_fea"]
    assert cagrilar, "vehicle_fea artık classify_fea çağırmıyor"
    for c in cagrilar:
        assert any(k.arg == "yuk_bileseni" for k in c.keywords), (
            "classify_fea çağrısı yuk_bileseni taşımıyor; yük bütünlüğü "
            "kapısı bu yolda hiç çalışmaz")


def test_PAY_OKUYUCUSU_YOK_VAKADA_NONE_DONUYOR(tmp_path):
    """'Ölçemedim' ile 'sıfır' ayrı kalmalı: boş bir koşu dizini None
    döndürmeli, 0.0 değil --- 0.0 kapıyı GEÇİRİRDİ."""
    from vehicle_fea import _viskoz_pay_pct
    assert _viskoz_pay_pct(tmp_path) is None


def test_PAY_OKUYUCUSU_GERCEK_KAYITTAN_SAYI_DONUYOR():
    """Yanlış-negatif kapısı: okuyucu her zaman None dönseydi kapı hep
    'bilinmiyor' derdi ve ayırt etmezdi. Depoda ayrımı olan bir vaka var."""
    from vehicle_fea import _viskoz_pay_pct
    aday = KOK / "turek_hron_cfd1_case"
    if not aday.exists():
        import pytest
        pytest.skip("ayrımı olan vaka diskte yok")
    pay = _viskoz_pay_pct(aday)
    assert pay is not None and pay > 0
