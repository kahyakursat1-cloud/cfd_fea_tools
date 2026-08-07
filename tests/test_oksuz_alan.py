"""Üretilen her sonuç alanının en az bir tüketicisi olmalı.

Bu oturumun tekrar eden kusuru: bir büyüklük ÖLÇÜLÜYOR, sonuç nesnesine
yazılıyor, ama hiçbir tüketici onu okumuyor. Ölçümün maliyeti ödenir ve karar
ondan habersiz verilir; hiçbir test kırılmaz, hiçbir log uyarmaz.

Ölçülen örnekler: `ref_bump="oto"` beş çağırandan birine ulaşmıştı;
`en_kucuk_boyut_m` yüzey kapısının imzasındaydı ama gövdede kullanılmıyordu;
`fizik_kabul` FEA motorunda vardı, arayüz yok sayıyordu; `mesh_levels` arayüzden
hiç geçmiyordu; `log_files` üretiliyordu ama hata mesajı hangi loga bakılacağını
söylemiyordu.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from oksuz_alan import SERILESTIRME_MUAFI, tara  # noqa: E402


def test_oksuz_alan_yok():
    b = tara()
    assert not b, (
        "üretilen ama hiç okunmayan alan(lar): "
        + ", ".join(f"{x['sinif']}.{x['alan']}" for x in b)
        + ". Ya bir tüketiciye bağlayın ya da alanı kaldırın — ölçüp "
          "kullanmamak, maliyeti ödeyip karardan dışlamaktır.")


def test_muafiyet_listesi_gerekcesi_olan_alanlarla_sinirli():
    """Muafiyet, taramayı susturmanın kolay yolu olmamalı: yalnız
    serileştirmeyle tüketilen birkaç alan muaf."""
    assert len(SERILESTIRME_MUAFI) <= 8, SERILESTIRME_MUAFI


def test_tarayici_getattr_okumasini_goruyor():
    """Aracın kendi yanlış pozitifi: ilk sürüm `getattr(r, "pervane")`
    biçimini görmüyor ve alanı öksüz sanıyordu."""
    src = (KOK / "oksuz_alan.py").read_text(encoding="utf-8")
    assert "getattr" in src
    from vehicle_pipeline import VehicleAnalysisResult
    assert "pervane" in VehicleAnalysisResult.__dataclass_fields__
    assert not any(x["alan"] == "pervane" for x in tara())


def test_hata_mesaji_DUSEN_ASAMAYI_soyluyor():
    """`log_files` ve aşama telemetrisi üretiliyordu ama hata mesajı 2000
    karakter ham stderr'den ibaretti — kullanıcı hangi adımın çöktüğünü ve
    hangi dosyaya bakacağını kendisi çıkarmak zorundaydı."""
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    i = src.index("if not res.success or res.cd is None:")
    blok = src[i:i + 1400]
    assert "DÜŞEN AŞAMA" in blok
    assert "res.log_files" in blok
    assert "asama_sureleri" in blok
