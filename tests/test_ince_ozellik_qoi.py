"""İnce özellik hükmü BÜYÜKLÜĞE GÖRE ayrılır — tek 'geçerli' etiketi yanlıştır.

Dış inceleme (2026-08-21, CFD/FEA + V&V bakışı) bunu en yerinde bulgu olarak
işaretledi: ölçüm zaten yapılıyordu (`openfoam_runner` `ozellik_cozuldu`
alanını hesaplıyor) ama yalnız KAYIT olarak duruyordu — tek tüketicisi bir
deney betiğiydi, geçerlilik sınıfına hiç girmiyordu. Bu deponun baskın kusuru:
ölçülür, kaydedilir, karara ulaşmaz.

Fizik: taşıma ve moment Kutta koşulundan doğar. Firar kenarı ağda temsil
edilmiyorsa sirkülasyon "belirsiz" değil KURULMAMIŞTIR. Direnç farklıdır —
basınç direncinin ana bileşeni gövdeden gelir ve yakalanır; eksik olan
özelliğin kendi katkısıdır.
"""
from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from validity_envelope import (  # noqa: E402
    OUT,
    TREND,
    VALIDATED,
    Verdict,
    apply_ince_ozellik_gate,
)


def _v():
    return [Verdict("C_D", VALIDATED, True, "ok"),
            Verdict("C_L", VALIDATED, True, "ok"),
            Verdict("L/D", VALIDATED, True, "ok"),
            Verdict("C_M", VALIDATED, True, "ok")]


def _sinif(vs):
    return {x.quantity: x.klass for x in vs}


def test_sirkulasyona_bagli_buyuklukler_ZARF_DISI():
    # MiniHawk'ta olculen deger: 0,17 hucre/ozellik
    s = _sinif(apply_ince_ozellik_gate(
        _v(), {"ozellik_cozuldu": False, "ozellik_basina_hucre": 0.17}))
    assert s["C_L"] == OUT
    assert s["C_M"] == OUT
    assert s["L/D"] == OUT, "L/D, Cl'e bağlı olduğu için kurtarılamaz"


def test_direnc_REDDEDILMEZ_egilime_iner():
    # Reddetmek orantisiz olurdu: basinc direncinin ana bileseni yakalanir.
    # "Dogrulanmis" demek de yanlis: ozelligin katkisi bandda YOK.
    s = _sinif(apply_ince_ozellik_gate(
        _v(), {"ozellik_cozuldu": False, "ozellik_basina_hucre": 0.94}))
    assert s["C_D"] == TREND


def test_gerekce_SAYIYI_tasiyor():
    v = apply_ince_ozellik_gate(
        _v(), {"ozellik_cozuldu": False, "ozellik_basina_hucre": 0.17})
    for x in v:
        assert x.kod.startswith("INCE_OZELLIK"), x.kod
        assert "0.17" in x.message, "hüküm ölçülen sayıyı taşımıyor"


def test_COZULDUYSE_ve_OLCULMEDIYSE_dokunulmaz():
    assert _sinif(apply_ince_ozellik_gate(
        _v(), {"ozellik_cozuldu": True, "ozellik_basina_hucre": 6.0})) \
        == {"C_D": VALIDATED, "C_L": VALIDATED, "L/D": VALIDATED, "C_M": VALIDATED}
    # Olculmediyse SESSIZCE indirme YOK — "olcemedim" ile "kotu" ayri seylerdir
    assert _sinif(apply_ince_ozellik_gate(_v(), None))["C_L"] == VALIDATED
    assert _sinif(apply_ince_ozellik_gate(
        _v(), {"ozellik_cozuldu": False}))["C_L"] == VALIDATED, \
        "sayı yokken gerekçe yazılamaz; sınıf indirilmemeli"


def test_URETIM_YOLU_kapiyi_CAGIRIYOR():
    """Kapı VAR ama üretim yolu çağırmıyor deseni — bu deponun baskın kusuru.

    Hüküm doğru olsa bile çağrılmayan bir kapı kullanıcıya ulaşmaz. İki sunum
    kanalı da (servis ve arayüz) çağırmalı; biri çağırıp öteki çağırmazsa
    `kanal_ayrismasi` sınıfına düşer.
    """
    for ad in ("hizmet.py", "app_analyzer.py"):
        src = (KOK / ad).read_text(encoding="utf-8")
        assert "apply_ince_ozellik_gate(" in src, f"{ad} kapıyı çağırmıyor"
        assert "geometri_goreli" in src, f"{ad} kapıya ölçümü vermiyor"


def test_URETICININ_semasi_kullaniliyor():
    # Kendi anahtar adini uydurmak, alani hic okuyamayan sessiz bir kapi
    # uretirdi. Uretici bunu `ozellik_basina_hucre` olarak yaziyor.
    src = (KOK / "analysis" / "openfoam_runner.py").read_text(encoding="utf-8")
    assert '"ozellik_basina_hucre"' in src
    kapi = (KOK / "validity_envelope.py").read_text(encoding="utf-8")
    assert 'g.get("ozellik_basina_hucre")' in kapi
