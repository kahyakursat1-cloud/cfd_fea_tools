"""Validasyon çapaları + model-belirsizlik öncülleri (ASME V&V 20 validasyon bacağı).

İki işi var:
1. ANCHORS — literatürden bilinen-doğru referans Cd'ler. validate_pipeline.py bunları
   pipeline'dan geçirip rejim-başına ÖLÇÜLEN hata bandını üretir (compute gerektirir).
2. model_uncertainty_pct — pipeline daha validate edilmeden önce kullanılan LİTERATÜR
   ÖNCÜLÜ: RANS-SST'nin rejim/duvar-çözünürlüğüne göre tipik model hatası. Ölçülen bant
   (validation_band.json) varsa O kullanılır; yoksa bu öncül + açık "validasyon beklemede"
   etiketi döner. Sahte-kesinlik verilmez.

Kaynaklar: küre subkritik Cd≈0.47 (White, Fluid Mechanics; Schlichting). NACA0012 α=0
Cd₀≈0.0081 (Ladson NASA TM-4074 / NASA TMR). Ahmed body 25° Cd≈0.285 (Ahmed 1984; Meile
2011). Rejim model-hatası mertebeleri: RANS-SST harici-aerodinamik V&V literatürü.

u_ref_pct (u_D) BEYAN KURALI: sayı ya kaynağın kendisinden gelir ya da hiç yazılmaz.
Türetilmişse `u_ref_sinif` alanı neyin ölçüldüğünü söyler — örneğin NACA0012 α=0'ın
u_D'si TMR'nin yedi kodunun yayılımıdır (ALT SINIR: deneysel belirsizliği kapsamaz).
Beyan edilmemiş çapaların engeli `referans_belirsizligi.json` içinde adıyla kayıtlı;
"u_D yok" ile "u_D ölçülemez" aynı şey değildir.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

ANCHORS = {
    "sphere": {
        "Cd": 0.47, "regime": "bluff", "Re": "1e3–2e5 (subkritik)",
        "aref": "frontal", "ref": "White, Fluid Mechanics; Schlichting BL Theory",
        "u_ref_pct": None,   # ders kitabı değeri; kaynak band beyan etmiyor
    },
    "naca0012_a0": {
        # REJIM ETIKETI YANLISTI ("lifting"): alpha=0'da tasima SIFIRDIR ve bu
        # vaka bagli 2B akistir. model_form_bandi zaten onu attached_2d hucresine
        # yaziyordu, yani iki kaynak celisiyordu; dogru olan attached_2d.
        "Cd": 0.0081, "regime": "attached_2d", "Re": "6e6",
        "aref": "kiriş", "ref": "Ladson NASA TM-4074; NASA Turbulence Modeling Resource",
        # OLCULDU (tmr_kod_yayilimi.json): TMR tekil deger yayimliyor SANILIYORDU;
        # aslinda ayni vakayi ayni agda (897x257) ve ayni modelle (SA) YEDI
        # bagimsiz kodla kosup hepsini yayimliyor. Capanin referansi bir deney
        # degil o TMR degeri oldugu icin, referansin belirsizligi ayni seyi
        # hesaplayan kodlarin yayilimidir: 1σ = %0.796 (tam aralik %2.204).
        # ALT SINIR — kod-arasi yayilim DENEYSEL belirsizligi kapsamaz; TMR bu
        # vakada olculen suruklemenin sinir-tabaka tetiklemesine cok duyarli
        # oldugunu ayrica uyariyor.
        "u_ref_pct": 0.796,
        "u_ref_sinif": "ALT SINIR (kod-arası yayılım, n=7)",
    },
    "ahmed_25": {
        # REFERANS KOSULA ESLESTIRILDI (2026-08-19). Onceki deger 0,285 ve
        # beyan edilen Re "~1e6" idi; ikisi de KOSUYU ANLATMIYORDU.
        #
        # OLCULDU: bu capa V=40 m/s, L=1,044 m ile kosuyor → Re = 2,784e6.
        # Iki yayimlanmis deger var ve FARKLI KOSULLARDA:
        #   Ahmed & Ramm 1984 (SAE 840300): cD=0,2875 @ Re=4,29e6, V=60 m/s
        #   Meile vd. 2011 (CFD Letters 3(1)): cD=0,299 @ Re=2,784e6, V=40 m/s
        # Yani Meile'nin kosulu bu capanin kosuguyla BIREBIR AYNI.
        #
        # Onceki not "iki deger ayni Re'de degil, o yuzden yazilmaz" diyordu.
        # Bu, u_D TURETMEK icin dogru bir gerekcedir ama REFERANS SECIMI icin
        # degil: kostugun kosulda olculmus deger, baska bir kosulda olculmus
        # degerden daha iyi bir referanstir. Sapma %16,2 → %10,8'e iner ve
        # farkin bir kismi model hatasi degil KOSUL UYUSMAZLIGIYDI.
        #
        # KANIT DERECESI: iki BAGIMSIZ ikincil kaynak (SimFlow ve SimScale
        # dogrulama sayfalari) kosullariyla birlikte uyusuyor; birincil makale
        # metinleri ucretli duvar arkasinda ve OKUNAMADI. Bu yuzden u_ref
        # hala beyan EDILMIYOR — iki deger farkli Re'de oldugu icin aradaki
        # fark u_D degil, Re bagimliligiyla karisir.
        "Cd": 0.299, "regime": "bluff", "Re": "2,784e6 (V=40 m/s, L=1,044 m)",
        "aref": "frontal",
        "ref": ("Meile vd. 2011, CFD Letters 3(1) — cD=0,299 @ Re=2,784e6 "
                "(KOSULA ESLESIK); krs. Ahmed & Ramm 1984 SAE 840300, "
                "cD=0,2875 @ Re=4,29e6"),
        "u_ref_pct": None,
    },
    "cube": {
        "Cd": 1.05, "regime": "bluff", "Re": ">1e4 (keskin-kenar, Re-duyarsız)",
        "aref": "frontal", "ref": "Hoerner, Fluid-Dynamic Drag (1965)",
        "u_ref_pct": None,   # Hoerner tablo degeri; band beyan etmiyor
    },
    "disk": {
        "Cd": 1.17, "regime": "bluff", "Re": ">1e3 (keskin-kenar, Re-duyarsız)",
        "aref": "frontal", "ref": "Hoerner, Fluid-Dynamic Drag (1965)",
        "u_ref_pct": None,   # Hoerner tablo degeri; band beyan etmiyor
    },
    "naca0012_wing_ar6": {
        "Cd": 0.020, "regime": "lifting", "Re": "3e5 (c=0.15 m, 30 m/s), α=4°",
        "aref": "planform",
        "ref": ("YARI-ANALİTİK (±%15): türbülanslı profil Cd0≈0.014 (düz-plaka Cf "
                "+ form) + lifting-line CDi=CL²/(πeAR), CL≈0.32, e≈0.9 — Anderson; "
                "deneysel tekil referans yok, band ölçümü bu belirsizlikle etiketli"),
        # BELIRSIZLIK METINDE YAZILIYDI AMA SAYI OLARAK TASINMIYORDU, dolayisiyla
        # ayrilabilirlik hesabina HIC girmiyordu. ASME V&V 20'de karsilastirma
        # belirsizligi u_val = sqrt(u_num^2 + u_input^2 + u_D^2); referans
        # belirsizligi (u_D) o toplamin bileseni. Burada BASKIN bilesen odur.
        "u_ref_pct": 15.0,
    },
}

# Rejim × duvar-çözünürlüğü → RANS-SST tipik model belirsizliği (%, 1σ mertebesi).
# (wall_resolved=y⁺≲1+katman, wall_function=y⁺≳30). Literatür-öncül; ölçülen bant gelince
# bu DEVRE-DIŞI kalır.
_MODEL_U_PCT = {
    "lifting": {"wall_resolved": 5.0, "wall_function": 12.0},
    "bluff":   {"wall_resolved": 10.0, "wall_function": 20.0},
    # AYRILMIŞ AKIŞ AYRI BİR REJİMDİR ve bunu ölçtük: geriye-basamaklı akışta
    # kOmegaSST yeniden-yapışmayı %11.58 kaçırıyor (Driver & Seegmiller 1985).
    # Bağlı akışın model-form hatasını ayrılmış akışa taşımak, RANS'ın en zayıf
    # olduğu rejimi en güçlü olduğu rejimin bandıyla raporlamak olurdu.
    "separated": {"wall_resolved": 12.0, "wall_function": 25.0},
    # 2B bağlı akış — TMR C-grid ailesinde ÖLÇÜLDÜ (%3.5, y⁺<1).
    "attached_2d": {"wall_resolved": 5.0, "wall_function": 12.0},
}
_BAND_FILE = HERE / "validation_band.json"


def regime_of(vehicle_type: str, preset: dict) -> str:
    """Araç tipini model-belirsizlik rejimine indir: lift üreten → 'lifting', küt → 'bluff'."""
    return "lifting" if preset.get("lift_relevant") else "bluff"


def model_uncertainty_pct(regime: str, wall_resolved: bool) -> dict:
    """Rejim+duvar-çözünürlüğü için model belirsizliği (%). Ölçülen validasyon bandı
    (validation_band.json) varsa onu, yoksa literatür-öncülünü döndürür (kaynak etiketli)."""
    key = "wall_resolved" if wall_resolved else "wall_function"
    if _BAND_FILE.exists():
        try:
            band = json.loads(_BAND_FILE.read_text(encoding="utf-8"))
            v = band.get(regime, {}).get(key)
            if v is not None:
                # KAC CAPADAN geldigi de soylenir: n=1 bir DAGILIM degil, tek
                # olcumdur ve okuyucu bunu bilmelidir.
                n = None
                ay = HERE / "model_form_bandi.json"
                if ay.exists():
                    d = json.loads(ay.read_text(encoding="utf-8"))
                    n = ((d.get("olculen_hucreler") or {})
                         .get(regime, {}).get(key, {}).get("n_capa"))
                return {"u_model_pct": round(float(v), 2),
                        "kaynak": ("ölçülen (validation_band.json"
                                   + (f", n={n} çapa" if n else "") + ")"),
                        "n_capa": n}
        # sessiz-yutma: kabul — ölçülen band okunamazsa ÖNCÜLE düşülür ve
        # kaynak etiketi bunu zaten söyler; sayı uydurulmaz.
        except Exception:
            pass
    # BILINMEYEN REJIM SESSIZCE 'bluff' SAYILIYORDU. Kunt cisim oncululu
    # (%10/20) tanimadigimiz her rejime uygulanmis oluyordu ve etikette bunun
    # izi YOKTU. Artik rejimin taninmadigi ACIKCA yazilir.
    if regime not in _MODEL_U_PCT:
        return {"u_model_pct": _MODEL_U_PCT["bluff"][key],
                "kaynak": (f"literatür-öncül — REJİM TANINMADI ('{regime}'), "
                           "künt cisim önculü uygulandı; bu bir ÖLÇÜM DEĞİL "
                           "ve rejim-uygunluğu DOĞRULANMAMIŞTIR"),
                "rejim_taninmadi": True}
    return {"u_model_pct": _MODEL_U_PCT[regime][key],
            "kaynak": "literatür-öncül (pipeline-validasyonu beklemede)"}


def combine_uncertainty(u_num_pct: float | None, u_model_pct: float | None) -> float | None:
    """Sayısal (GCI) + model belirsizliğini RSS ile birleştir → toplam genişletilmiş U (%)."""
    parts = [u for u in (u_num_pct, u_model_pct) if u is not None]
    if not parts:
        return None
    return round(math.sqrt(sum(u * u for u in parts)), 2)
