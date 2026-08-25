"""y⁺ ALAN kapsamı karar yoluna ulaşıyor mu?

Hakem incelemesi (2026-08-24): ``ortalama y⁺ bandda'' demek, duvar işleminin
yüzeyin üçte birinde geçerli olmadığı gerçeğini gizleyebiliyor. Ölçüldü:

    Ahmed 25°  ort 30,5 · bantta ALAN yalnız %65,8
    küp        ort 40,9 · bantta ALAN yalnız %69,4
    disk                              %59,8

Üçü de ortalama-kapısından geçiyordu. Ölçüm (`duvar_islemi_kapsami`) vardı ama
yalnız bir deney betiği okuyordu.

BU BİR RET KAPISI DEĞİL, NİTELEYİCİDİR --- ve öyle kalmalıdır. Eşiği bugün
sıkılaştırmak `bluff.wall_function` hücresinin iki çapasını da düşürür ve bandı
ÖLÇMEDEN genişletirdi.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


def test_kapsam_URETIM_YOLUNDAN_hesaplaniyor():
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    assert "_yplus_kapsami(case_dir" in src, "kapsam üretim yolunda çağrılmıyor"
    assert '"alan_kapsami": _kapsam' in src, "kapsam koşu kaydına girmiyor"


def test_kapsam_KULLANICIYA_gorunuyor():
    """Kayda yazıp göstermemek, tam da eleştirilen kusur."""
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    i = src.index("y⁺ ALAN KAPSAMI:")
    blok = src[i - 400:i + 700]
    assert "uyarilar.append" in blok, "kapsam uyarı listesine girmiyor"
    assert "kapsam_pct" in blok, "sayı uyarıda yok"
    assert "ÖLÇÜLEMEDİ" in blok, "ölçülememe sessizce geçiliyor"


def test_kapsam_DUVAR_ISLEMINE_gore_okunuyor():
    """Tek bir yüzdeyi duvar işleminden bağımsız okumak, bu ölçerin
    engellemek için yazıldığı kusurun kendisi.

    Küre çapası duvar-ÇÖZÜNÜR koşar ve log-bandındaki alanı %0,4'tür; bunu
    ``kapsam yetersiz'' diye okumak tam tersini söyler.
    """
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    i = src.index("def _yplus_kapsami(")
    govde = src[i:src.index("\ndef ", i + 10)]
    assert "wall_resolved" in govde and "wall_function" in govde
    assert "n_layers > 0" in govde, "duvar işlemi katman sayısından türemiyor"


def test_kapsam_RET_KAPISI_DEGIL():
    """Bugün sıkılaştırmak bandı ölçmeden genişletirdi. Kapsam sınıfı
    İNDİRMEMELİ; yalnız niteleyici olmalı."""
    src = (KOK / "vehicle_pipeline.py").read_text(encoding="utf-8")
    i = src.index("y⁺ ALAN KAPSAMI:")
    blok = src[i - 400:i + 700]
    for yasak in ("OUT_OF_ENVELOPE", "raise ", "status = \"error\""):
        assert yasak not in blok, f"kapsam ret kapısına dönüşmüş: {yasak}"


def test_olcut_duvar_islemiyle_DEGISIYOR():
    """Aynı dağılım, iki duvar işlemi, iki farklı kapsam — davranışla sınanır."""
    from yplus_dagilim import duvar_islemi_kapsami
    d = {"bandda_alan_pct": 65.8, "cozunur_alan_pct": 0.4, "cozunur_esik": 5,
         "band": (30.0, 300.0)}
    wf = duvar_islemi_kapsami(d, "wall_function")
    wr = duvar_islemi_kapsami(d, "wall_resolved")
    assert wf["kapsam_pct"] != wr["kapsam_pct"], (
        "kapsam duvar işleminden bağımsız okunuyor")
    assert wf["kapsam_pct"] == 65.8 and wr["kapsam_pct"] == 0.4
