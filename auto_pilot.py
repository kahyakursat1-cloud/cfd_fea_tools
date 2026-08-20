"""Analiz otopilotu — geometriden araç tipini sınıflandırır ve TÜM analiz
ayarlarını (rejim, Mach/hız, mesh kalitesi, viskoz/inviscid, referans) deterministik
olarak seçer. "Öner + onayla": bir plan + gerekçe döner; GUI gösterir, kullanıcı
onaylayınca koşar. LLM yorumcu opsiyonel (model yoksa şablon fallback).
================================================================================
Karar mantığı kural-tabanlıdır (LLM değil): CFD ayarları tekrarlanabilir ve
savunulabilir olmalı. LLM yalnız SONUCU yorumlar, ayar SEÇMEZ.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path

import trimesh

from vehicle_pipeline import (
    SINIF_BOY_BANDI_M,
    birim_sinif_cozumu,
    inspect_geometry,
    prepare_geometry,
)

# ── Öğrenme: büyüyen vaka kütüphanesi (instance-based / k-NN) ────────────────
# SEED: uzman (hakem) etiketli kanonik taban — uygulamayla birlikte gelir (commit'li).
# MEMORY: çalışma-zamanı öğrenmesi — kullanıcı onayladıkça büyür (gitignore'da).
SEED = Path(__file__).parent / "auto_pilot_seed.jsonl"
# REAL_SEED: internetten indirilen gerçek CAD modellerinin hakem-etiketli
# metrikleri (gerçek-dünya oranları; sentetik idealize plakaların açığını kapatır).
REAL_SEED = Path(__file__).parent / "auto_pilot_real_seed.jsonl"
# NX_SEED: NX'te parametrik üretilmiş, etiketi inşa anında bilinen EĞİTİM ailesi.
# Varlık sebebi: eski 241 kaydın hiçbirinde `donel_simetri` yok, bu yüzden kNN gerçek
# bir multikopterin yanına komşu bulamıyordu. AYRIK test ailesi buraya GİRMEZ.
NX_SEED = Path(__file__).parent / "auto_pilot_nx_seed.jsonl"
MEMORY = Path(__file__).parent / "auto_pilot_memory.jsonl"
MIN_CASES = 8        # bu sayıdan az onaylı vaka varken yalnız kural-tabanlı
# Multikopter dalı ÖNCE H/L ≥ 0.30 istiyordu ve bu ULAŞILAMAZ bir eşikti: bilinen 33
# multikopterin hepsinde H/L ≤ 0.28 (medyan 0.13). Ateşlenen 24 vakanın 23'ü 'genel'di —
# dal ters çalışıyordu. Eşiği gevşetmek DENENDİ ve GERİLEDİ (ayrık NX setinde kural
# doğruluğu %51.2 → %34.1), çünkü radyal doluluk multikopter (0.25-0.39) ile uçağı
# (0.34-0.42) ayırmıyor. Ayıran şey yassılık değil DÖNEL SİMETRİ: çok-rotorlu gövde
# üstten 360/k derece dönünce kendine oturur, kanatlı araç oturmaz.
# Eşikler AYRI NX EĞİTİM ailesinde kalibre edildi (test setine bakılmadan):
#   multikopter simetri 0.52-1.00 / doluluk 0.21-0.28  (n=5)
#   en yakın yabancı: tilt_rotor simetri 0.46          → yanlış ateşleme 0/24
# 0.55 seçildi (0.50 değil): yanlış 'multikopter' hükmü yanlış preset ve yanlış A_ref
# demektir; kaçırılan multikopter ise kNN'e düşer. Marj dar (0.46 ↔ 0.52) ve eğitim
# örneği az (5) — bu dal kesin değil, kNN'i DESTEKLER.
MULTIKOPTER_SIMETRI_ESIGI = 0.55
MULTIKOPTER_DOLULUK_ESIGI = 0.45
# Temel tipler (kural+k-NN) + hibrit alt-tipler (yalnız k-NN ile öğrenilir).
# 'araba' kural-imzasız (tekerlek/zemin sezgisi geometriden güvenilir çıkmaz):
# kullanıcı seçimi + k-NN öğrenmesiyle gelir; preset zemin-düzlemini otomatik kurar.
TIPLER = ("roket", "ucak", "multikopter", "genel", "kanatli_roket", "tilt_rotor",
          "kanatli_vtol", "kaldirici_govde", "araba")
# Sınıflandırma tipi -> CFD preset (vehicle_pipeline.VEHICLE_PRESETS anahtarı)
PRESET_MAP = {"roket": "roket", "ucak": "ucak", "multikopter": "multikopter",
              "genel": "genel", "kanatli_roket": "roket", "tilt_rotor": "ucak",
              "kanatli_vtol": "ucak", "kaldirici_govde": "roket", "araba": "araba"}


def _features(metrik: dict) -> list:
    """k-NN için AĞIRLIKLI normalize özellik vektörü (her özellik √w ile ölçeklenir,
    Öklid mesafesi ağırlıklı olur). Ağırlıklar fizikseldir: yassılık (H/L) ve
    incelik (L/D) sınıfı en çok ayırır; W/L belirsizdir (delta W/L≈1 ama yassı)."""
    # planform/frontal: kanat (planform»frontal) ile küt/kaldırıcı gövdeyi ayırır;
    # gerçek-dünya CAD'lerinde gövdeli uçağı kaldırıcı gövdeden kısmen ayrıştırır.
    # ince_yassilik (bbox-üstü): kanat-inceliği; gövdeli uçağı kaldırıcı/küt
    # gövdeden ayırmada bbox oranlarının yetmediği yerde ek sinyal.
    # radyal_doluluk (üst-görünüm spoke↔sürekli): multikopter↔kanat bbox-örtüşmesini
    # çözen güçlü ayırt edici; eski-anchorda yoksa 1.0 (sürekli) varsayılır.
    # donel_simetri (360/k dönel simetri): çok-rotorlu gövdeyi kanatlıdan ayıran tek
    # güçlü sinyal; doluluk tek başına ayırmıyor (multikopter 0.25-0.39 ↔ uçak 0.34-0.42).
    # Eski kayıtlarda yok → 0.0 (simetrisiz) varsayılır, "bilinmiyor"u simetrik saymaz.
    w = {"L_D": 1.3, "W_L": 0.6, "H_L": 2.0, "H_W": 1.5, "govde": 0.7,
         "pf": 1.2, "yass": 1.4, "dol": 1.5, "sim": 1.8}
    iy = metrik.get("ince_yassilik")
    dol = metrik.get("radyal_doluluk")
    sim = metrik.get("donel_simetri")
    f = [min(metrik.get("L_D", 0), 30) / 30, metrik.get("W_L", 0),
         metrik.get("H_L", 0), metrik.get("H_W", 0),
         min(metrik.get("govde", 1), 8) / 8,
         min(metrik.get("planform_frontal", 0), 20) / 20,
         min(iy if iy is not None else 1.0, 1.0),
         dol if dol is not None else 1.0,
         sim if sim is not None else 0.0]
    sw = [w["L_D"], w["W_L"], w["H_L"], w["H_W"], w["govde"], w["pf"], w["yass"],
          w["dol"], w["sim"]]
    return [fi * (wi ** 0.5) for fi, wi in zip(f, sw)]


def referee_gate(metrik: dict, vtype: str, result: dict | None) -> dict:
    """Hakem (analiz-mühendisi) hükmünü ÖĞRENME KAPISINA çevirir: bir koşunun
    Cd'si güvenilir bir çapa mı, yoksa şüpheli mi? Şüpheli Cd kütüphaneye temiz
    çapa olarak GİRMEZ (yalnız tip etiketi öğrenilir) — kötü sonuç kirletmesin.
    Döner: {cd_guvenilir, suspect, gerekce[]}."""
    r = result or {}
    cd = r.get("Cd_toplam")
    nedenler = []
    if r.get("status") == "FAILED":
        nedenler.append("koşu başarısız (status=FAILED)")
    if cd is None:
        nedenler.append("Cd yok")
    elif cd <= 0 or cd > 5.0:
        nedenler.append(f"fiziksel olmayan Cd={cd}")
    drift = r.get("Cd_drift_pct")
    if drift is not None and abs(drift) > 5.0:
        nedenler.append(f"zayıf yakınsama (Cd drift %{abs(drift):.1f} > %5)")
    if cd is not None and cd > 0:
        # AREF_MODE GECIRILIR: Cd yalniz ayni referans alanina gore
        # hesaplanmis degerlerle kiyaslanabilir.
        flag = cd_outlier(vtype, cd, (r or {}).get("aref_mode"))
        if flag:
            nedenler.append("aykırı: " + flag)
    cd_guvenilir = (cd is not None) and not nedenler
    return {"cd_guvenilir": cd_guvenilir, "suspect": bool(nedenler), "gerekce": nedenler}


def record_case(metrik: dict, otopilot_tip: str, onayli_tip: str,
                result: dict | None = None, dosya: str = "") -> dict:
    """Onaylanan/düzeltilen analizi kütüphaneye ekle (öğrenme sinyali).
    Hakem-kapısı: Cd yalnız GÜVENİLİRSE temiz çapa olur; şüpheliyse cd_toplam=None
    yazılır (tip yine öğrenilir) + suspect bayrağı/gerekçe saklanır. Gate döner."""
    gate = referee_gate(metrik, onayli_tip, result)
    cd_raw = (result or {}).get("Cd_toplam")
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M"), "dosya": dosya, "metrik": metrik,
           "otopilot_tip": otopilot_tip, "onayli_tip": onayli_tip,
           "cd_toplam": cd_raw if gate["cd_guvenilir"] else None,
           # REFERANS ALANI KAYDEDILIR. Onceden yazilmiyordu ve kutuphanedeki
           # 277 vakanin HICBIRI tasimiyor; `cd_outlier` bu yuzden farkli
           # referans alanina gore hesaplanmis Cd'leri ayni havuzda
           # toplayabiliyordu (planform vs frontal farki tam o mertebede).
           "aref_mode": (result or {}).get("aref_mode"),
           "aref_m2": (result or {}).get("aref_m2"),
           "rejim": (result or {}).get("rejim")}
    if gate["suspect"]:
        rec["suspect"] = True
        rec["suspect_neden"] = "; ".join(gate["gerekce"])
        if cd_raw is not None:
            rec["cd_ham"] = cd_raw           # şeffaflık: ham değer saklanır, çapa değil
    with open(MEMORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return gate


# Kütüphane kaynakları TEK YERDE adlandırılır. Kaynak listesi çağrı yerinde gömülüyken
# NX_SEED eklenmesi testlerin izolasyon fixture'ını SESSİZCE deldi (boş kütüphane
# beklerken 29 kayıt görüldü). Adları buradan okumak, yeni kaynağın izolasyona
# otomatik dahil olmasını sağlar.
KAYNAK_ADLARI = ("SEED", "REAL_SEED", "NX_SEED", "MEMORY")


def _load_cases() -> list:
    """Uzman-etiketli SEED tabanı + NX eğitim tohumu + çalışma-zamanı MEMORY."""
    out = []
    for _ad in KAYNAK_ADLARI:
        src = globals()[_ad]
        if not src.exists():
            continue
        for line in src.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line)
                if c.get("onayli_tip") and c.get("metrik"):
                    out.append(c)
            # sessiz-yutma: kabul — bozuk JSONL satırı atlanır; kural motoru kütüphanesiz de çalışır
            except Exception:
                pass
    return out


def learned_vote(metrik: dict, k: int = 5) -> dict | None:
    """Birikmiş kütüphaneden k-en-yakın komşu oyu (yeterli vaka varsa)."""
    cases = _load_cases()
    if len(cases) < MIN_CASES:
        return None
    fv = _features(metrik)
    scored = sorted(cases, key=lambda c: sum(
        (a - b) ** 2 for a, b in zip(fv, _features(c["metrik"]))))[:k]
    votes = Counter(c["onayli_tip"] for c in scored)
    top, n = votes.most_common(1)[0]
    return {"tip": top, "guven": round(n / len(scored), 2),
            "komsu": len(scored), "kutuphane": len(cases)}


def cd_outlier(vtype: str, cd: float, aref_mode: str | None = None) -> str | None:
    """Birikmiş aynı-tip Cd dağılımına göre aykırı sonuç bayrağı.

    SAGLAM ISTATISTIK (medyan + MAD), ORTALAMA + SD DEGIL.
    Aykiri-dedektorunu ortalama ve standart sapmayla kurmak kendi kendini
    baltalar: aykirilar sd'yi sisirir ve KENDILERINI gizler.

    OLCULDU (2026-08-19, `ucak` tipi, n=14): dagilim iki kumeli —
    12 vaka 0,0039-0,0211 arasinda, 2 vaka 0,337 ve 0,400 (16-19 KAT buyuk).
      ortalama+sd : mu=0,062  sd=0,126  -> esik 2,5sd = 0,377
                    0,337 BAYRAKLANMIYOR (tipik degerin 17 kati olmasina ragmen)
      medyan+MAD  : med=0,0136  sigma=0,0088 -> esik = 0,0221
                    IKI aykiri da bayraklaniyor, normaller etkilenmiyor
    Ucuncu bir aykiri gelseydi sd daha da siser ve ikisi birden kacardi.

    AREF_MODE AYRIMI: Cd yalniz AYNI referans alanina gore hesaplanmis
    degerlerle kiyaslanabilir; planform ile frontal arasindaki fark tam bu
    mertebededir. Kutuphanedeki 277 eski vaka `aref_mode` TASIMIYOR (kayit
    fonksiyonu yazmiyordu; artik yaziyor). Bu yuzden eslestirme SIKI DEGIL:
    mod iki tarafta da biliniyorsa esitlik aranir, biri bilinmiyorsa vaka
    havuzda kalir ve bu hukumde SOYLENIR — eski veriyi atmak calisan bir
    kapiyi kor etmek olurdu.
    """
    if cd is None:
        return None
    hepsi = [c for c in _load_cases()
             if c.get("onayli_tip") == vtype and c.get("cd_toplam")]
    if aref_mode:
        havuz = [c for c in hepsi
                 if c.get("aref_mode") in (None, aref_mode)]
        _mod_bilinmeyen = sum(1 for c in havuz if c.get("aref_mode") is None)
    else:
        havuz, _mod_bilinmeyen = hepsi, len(hepsi)
    vals = sorted(c["cd_toplam"] for c in havuz)
    if len(vals) < 5:
        return None

    def _med(x):
        n = len(x)
        return x[n // 2] if n % 2 else 0.5 * (x[n // 2 - 1] + x[n // 2])

    med = _med(vals)
    mad = _med(sorted(abs(v - med) for v in vals))
    # 1,4826: normal dagilimda MAD'i standart sapmaya cevirir.
    # Taban: yarisindan fazlasi ozdesse MAD=0 olur ve kapi her seyi bayraklar.
    sigma = max(1.4826 * mad, 0.1 * abs(med))
    if sigma > 0 and abs(cd - med) > 2.5 * sigma:
        # "YALNIZSIN" ile "SENIN GIBI BIR KUME VAR" AYNI SEY DEGIL.
        # Tek basina uzakta duran bir deger muhtemelen bir KUSURDUR. Ama
        # etrafinda benzer bir kume varsa, o kume buyuk olasilikla baska bir
        # REFERANS ALANI sozlesmesiyle hesaplanmistir ve "geometrini kontrol
        # et" demek yanlis yere bakmaktir.
        #
        # OLCULDU (2026-08-19): tilt_rotor'da 12 vaka 0,009-0,023 ve 4 vaka
        # 0,26-0,337 (14-37 KAT sicrama); kanatli_roket'te 17 vaka 0,167-0,322
        # ve 3 vaka 0,452-0,646. Bu kadar duzenli iki-kumelilik gurultu degil,
        # sozlesme farkinin imzasidir (planform vs frontal oran mertebesi).
        # KOMSULUK GORELI OLCULUR, sigma ile DEGIL. Ilk surum `|v-cd| <= 2.5*sigma`
        # kullaniyordu ve ise yaramadi: sigma DAR olan alt kumeden gelir
        # (tilt_rotor'da 0,008) ama aykiri kume genis bir aralikta durur
        # (0,26-0,337, yani ~10 sigma). Mutlak pencere yanlis olcektedir.
        # Iki-kat bandi olcekten bagimsizdir ve sozlesme farkini yakalar.
        komsu = sum(1 for v in vals if 0.5 * cd <= v <= 2.0 * cd)
        if komsu >= 3:
            _tani = (f"AMA benzer {komsu} vaka daha var — bu, tek bir hatadan çok "
                     "FARKLI REFERANS ALANI (planform↔frontal) işaretidir; "
                     "önce A_ref sözleşmesini doğrulayın")
        else:
            _tani = (f"ve yakınında yalnız {komsu} vaka var — "
                     "geometri/ayar kontrolü önerilir")
        _not = (f" [{_mod_bilinmeyen} vakanın referans alanı kayıtlı değil — "
                "eski kayıtlar]" if _mod_bilinmeyen else "")
        return (f"C_D={cd:.3f}, bu tipteki {len(vals)} vakanın medyanından "
                f"({med:.3f}, sağlam σ≈{sigma:.3f}) belirgin sapıyor{_not} "
                f"{_tani}.")
    return None


def cd_predict(metrik: dict, vtype: str, k: int = 5, min_support: int = 5) -> dict | None:
    """Geometri-farkında Cd ön-kestirimi: aynı-tip kütüphane vakalarından feature-uzayında
    k-en-yakın komşunun MESAFE-AĞIRLIKLI Cd ortalaması + BELİRSİZLİK (komşu yayılımı).
    Veri ince (n<min_support) ise şeffaf REDDEDER (None) — sahte güven vermez.
    cd_outlier'ın tip-ortalamasına göre geometri-duyarlı (instance-tabanlı surrogate)."""
    cases = [c for c in _load_cases()
             if c.get("onayli_tip") == vtype and c.get("cd_toplam") is not None]
    if len(cases) < min_support:
        return None
    fv = _features(metrik)
    def d2(c):
        return sum((a - b) ** 2 for a, b in zip(fv, _features(c["metrik"])))
    knn = sorted(cases, key=d2)[:min(k, len(cases))]
    w = [1.0 / (d2(c) ** 0.5 + 1e-6) for c in knn]
    cds = [c["cd_toplam"] for c in knn]
    wsum = sum(w) or 1.0
    cd_hat = sum(wi * ci for wi, ci in zip(w, cds)) / wsum
    unc = (sum(wi * (ci - cd_hat) ** 2 for wi, ci in zip(w, cds)) / wsum) ** 0.5
    rel_unc = unc / (abs(cd_hat) + 1e-6)
    guven = round(min(1.0, len(cases) / 15.0) / (1.0 + rel_unc), 2)
    return {"cd_tahmin": round(cd_hat, 4), "belirsizlik": round(unc, 4),
            "n_destek": len(cases), "komsu": len(knn), "guven": guven}


def cd_prior_check(metrik: dict, vtype: str, cd: float) -> str | None:
    """CFD Cd'sini geometri-farkında ön-kestirimle karşılaştır (referee için). Belirgin
    sapma → kontrol bayrağı. cd_outlier'dan (tip-ortalama) daha sıkı/geometri-duyarlı."""
    if cd is None:
        return None
    pred = cd_predict(metrik, vtype)
    if not pred or pred["guven"] < 0.3:
        return None
    band = max(pred["belirsizlik"], 0.15 * abs(pred["cd_tahmin"]))
    if abs(cd - pred["cd_tahmin"]) > 3 * band:
        return (f"C_D={cd:.3f}, benzer {pred['n_destek']} geometrinin öğrenilen "
                f"ön-kestiriminden ({pred['cd_tahmin']:.3f}±{pred['belirsizlik']:.3f}) "
                f"belirgin sapıyor — geometri/mesh/ayar kontrolü önerilir.")
    return None


def classify_vehicle(geo: dict) -> dict:
    """inspect_geometry çıktısından araç tipi (roket/uçak/multikopter/genel).
    Skorlama: her tip için kanıt toplar, en yüksek skoru seçer, güven döner."""
    dims = sorted(geo["boyutlar_m"], reverse=True)
    L, W, H = dims[0], dims[1], dims[2]
    frontal = max(geo.get("on_alan_m2", 1e-9), 1e-9)
    planform = max(geo.get("planform_alan_m2", 1e-9), 1e-9)
    bodies = geo.get("govde_sayisi", 1) or 1

    d_eff = math.sqrt(4 * frontal / math.pi)          # eşdeğer frontal çap
    slender = L / max(d_eff, 1e-6)                     # incelik oranı L/D
    span_ratio = W / max(L, 1e-6)                      # yanal genişlik / boy
    flatness = H / max(W, 1e-6)                        # H/W: ~1 yuvarlak, «1 yassı
    compact = H / max(L, 1e-6)
    planform_ratio = planform / frontal
    solidity = geo.get("radyal_doluluk", 1.0)         # üst-görünüm doluluk (spoke↔sürekli)
    donel = geo.get("donel_simetri")                  # 360/k dönel simetri (kopter↔kanat)

    score = {"roket": 0.0, "ucak": 0.0, "multikopter": 0.0, "genel": 0.3}
    reasons = []
    # Roket: ince + EKSENEL-YUVARLAK kesit (W≈H)
    if slender >= 4 and flatness >= 0.5 and span_ratio < 0.5:
        score["roket"] += min((slender - 3) / 5, 1.0) + flatness * 0.5
        reasons.append(f"ince (L/D≈{slender:.1f}) ve yuvarlak kesit (H/W≈{flatness:.2f})")
    # Uçak/kanat: İNCE (H/L küçük, boyca yassı) ve GENİŞ (W/L makul) = kaldırma yüzeyi
    if compact < 0.2 and span_ratio >= 0.35:
        score["ucak"] += (0.2 - compact) * 3 + span_ratio
        reasons.append(f"ince-yassı (H/L≈{compact:.2f}) ve geniş (W/L≈{span_ratio:.2f}) → kaldırma yüzeyi")
    # Multikopter: kompakt + geniş + RADYAL-KOLLU (düşük solidity = spoke; bağlı-kollu
    # modelde bodies=1 olabilir → solidity bodies'ten daha güvenilir ayırt edici)
    # Multikopter: RADYAL SİMETRİ (üstten 360/k dönünce kendine oturur) + spoke topolojisi.
    # donel_simetri None ise (siluet çıkarılamadı) dal ateşlenmez — "bilinmiyor" ≠ "değil".
    if (donel is not None and donel >= MULTIKOPTER_SIMETRI_ESIGI
            and solidity < MULTIKOPTER_DOLULUK_ESIGI and slender < 4):
        score["multikopter"] += 1.0 + (donel - MULTIKOPTER_SIMETRI_ESIGI)
        reasons.append(f"radyal simetrik (dönel simetri≈{donel:.2f}) ve spoke-kollu "
                       f"(doluluk≈{solidity:.2f}) → çok-rotorlu gövde")

    vtype = max(score, key=score.get)
    total = sum(v for v in score.values() if v > 0)
    conf = score[vtype] / total if total else 0.3
    metrik = {"L_D": round(slender, 2), "W_L": round(span_ratio, 2),
              "H_L": round(compact, 2), "H_W": round(flatness, 2),
              "planform_frontal": round(planform_ratio, 2), "govde": bodies,
              "ince_yassilik": geo.get("ince_yassilik"),
              "radyal_doluluk": round(solidity, 3),
              "donel_simetri": round(donel, 3) if donel is not None else None}
    out = {"tip": vtype, "guven": round(conf, 2), "metrik": metrik,
           "gerekce": reasons, "kural_tip": vtype}
    # Öğrenme: birikmiş kütüphane yeterliyse k-NN oyunu harmanla
    lv = learned_vote(metrik)
    if lv:
        out["ogrenilen"] = lv
        # FİZİK-VETO: sürekli yüzey (yüksek solidity) multikopter OLAMAZ (spoke-kollu değil)
        # → eski-anchorlar bu özelliği taşımasa da yanlış 'multikopter' override'ı engellenir.
        veto = (lv["tip"] == "multikopter" and solidity > 0.55)
        if lv["guven"] >= 0.6 and lv["tip"] != vtype and not veto:
            # öğrenilen kanıt güçlü ve kuraldan farklı -> öğrenileni öne al
            out["tip"] = lv["tip"]
            out["gerekce"] = (reasons + [f"öğrenilen kütüphane ({lv['kutuphane']} vaka): "
                                         f"{lv['komsu']} komşunun %{lv['guven']*100:.0f}'i "
                                         f"'{lv['tip']}' → kural ('{vtype}') geçersiz kılındı"])
            out["guven"] = round((conf + lv["guven"]) / 2, 2)
    return out


# Süpersonik (yoğunluk-bazlı shockFluid) tipler — explicit, deltaT-limitli çözücü.
SUPERSONIC_TIPLER = {"roket", "kanatli_roket", "kaldirici_govde"}


def _regime_for_tip(tip: str) -> str:
    return "supersonic" if tip in SUPERSONIC_TIPLER else "subsonic"


def _quality_for(lmax_m: float, faces: int, regime: str = "subsonic") -> str:
    """Boyut + üçgen sayısı + REJİME göre mesh kalitesi. Süpersonik shockFluid
    explicit/deltaT-limitli: küçük hücre → küçük deltaT → maliyet patlar (~1M hücre
    saatler sürer). Bu yüzden süpersonikte hücre bütçesi çok daha düşük tutulur."""
    if regime == "supersonic":
        if lmax_m < 0.4 and faces < 15_000:
            return "standart"     # çok küçük/basit: süpersonikte bile makul
        return "hizli"            # aksi halde kaba mesh — yoksa intractable
    if lmax_m > 3.0 or faces > 200_000:
        return "hizli"            # büyük/ağır geometri → hücre bütçesini koru
    if lmax_m < 0.5 and faces < 20_000:
        return "hassas"           # küçük/basit → ince çözebiliriz
    return "standart"


def _runtime_band(regime: str, quality: str, lmax_m: float) -> str:
    """Çözücü-ÖNCESİ kaba wall-time bandı (hücre sayısı henüz bilinmez; rejim+
    kalite+boyut sezgisi). Kullanıcı uzun koşuyu bilerek başlatsın (öner+onayla).
    Mesh-kalite geçidiyle eşleşir: geçit kötü mesh'i eler, bu uzun koşuyu uyarır."""
    if regime == "supersonic":           # explicit shockFluid — pahalı
        return "uzun (saatler–gün)" if lmax_m > 1.0 else "orta (≈30–90 dk)"
    if quality == "hassas" or lmax_m > 3.0:
        return "orta–uzun (≈30–90 dk)"
    if quality == "hizli" and lmax_m < 1.0:
        return "hızlı (<15 dk)"
    return "orta (≈15–45 dk)"


def auto_configure(stl_path, out_dir="vehicle_runs/_autoprep",
                   dogrulama_modu: bool = False) -> dict:
    """Geometriyi hazırla + sınıflandır + TÜM analiz ayarlarını seç.
    dogrulama_modu=True → viskoz duvar (mutlak Cd); aksi halde hızlı inviscid+buildup.
    Döner: çalıştırılabilir config + insan-okunur plan (öner+onayla için)."""
    prep, info = prepare_geometry(stl_path, Path(out_dir))
    geo = inspect_geometry(prep)
    cls = classify_vehicle(geo)
    tip = cls["tip"]
    lmax = geo["lmax_m"]

    # SINIFA OZEL boy onceli birimi cozebiliyorsa olcegi DUZELT. Genel band
    # (0.05-10 m) 200x genis oldugu icin cogu girdide iki-uc birim birden makul
    # cikiyordu; roket oncelinde (0.3-2 m) tek-aday cozunurluk 9/28 -> 21/28.
    # Siniflandirmanin olcekten bagimsiz oldugu olculdu (6 mertebe), o yuzden
    # once siniflandirip sonra olceklemek gecerli. Duzeltme UYARIYA yazilir:
    # sessiz yeniden-olcekleme, duzelttigi sessiz hatanin aynisi olurdu.
    birim_notu = None
    _band = SINIF_BOY_BANDI_M.get(tip)
    if _band:
        _c = birim_sinif_cozumu(info.get("ham_lmax", lmax), lmax, _band,
                                olcek_uygulandi=bool(info.get("birim_olcek")))
        if _c["karar"] in ("cozuldu", "metrik_varsayildi"):
            _m = trimesh.load(str(prep), force="mesh")
            _m.apply_scale(_c["yeni_lmax"] / lmax)
            _m.export(str(prep))
            geo = inspect_geometry(prep)
            lmax = geo["lmax_m"]
            _bas = ("Birim sınıf önceliyle DÜZELTİLDİ"
                    if _c["karar"] == "cozuldu"
                    else "Birim VARSAYIMLA düzeltildi")
            birim_notu = f"{_bas}: {_c['gerekce']}."
        elif _c["karar"] != "dokunulmadi":
            birim_notu = f"Birim/ölçek şüphesi: {_c['gerekce']}."

    regime = _regime_for_tip(tip)
    quality = _quality_for(lmax, geo.get("ucgen_sayisi", 0), regime)

    # ref_bump="oto": YUZEY IYILESTIRME KADEMESI ML EYLEM UZAYINA GIRER.
    # Otopilot yalniz hizli/standart/hassas seciyordu; ref_bump preset'in SABIT
    # alanidir. Ama OLCULDU ki y+'i duvar-fonksiyonu bandina (30-300) sokan tek
    # kaldirac budur — ve dogru kademe govde boyutuna/hiza bagli oldugu icin sabit
    # bir sayi tum geometrilere uymuyor (sabit bump=2 ile multikopter_kucuk y+=25
    # verip bandin ALTINA dustu; oto kademeyle y+=38.6 ve gecti).
    #
    # 12-geometrilik taramada oto kademeyle secilen bump'lar 0'dan 4'e degisti ve
    # ONBIRININ DE olculen y+'i banda girdi (39-117). Bu satir olmadan GUI ve
    # otopilot varsayilan (0) ile kosuyor, yani olculen %83'luk oran KULLANICI
    # YUZU hicbir yolda gecerli degildi.
    cfg = {"stl": str(prep), "tip": tip, "kalite": quality, "ref_bump": "oto",
           "guven": cls["guven"], "metrik": cls["metrik"],
           "kural_tip": cls.get("kural_tip"), "ogrenilen": cls.get("ogrenilen"),
           "su_gecirmez": geo.get("su_gecirmez"), "lmax_m": lmax,
           "olcek_notu": info.get("birim_olcek")}

    apply_type_settings(cfg, tip, dogrulama_modu)

    cfg["tahmini_sure"] = _runtime_band(regime, quality, lmax)
    uyarilar = []
    if regime != "supersonic" and ("uzun" in cfg["tahmini_sure"]):
        uyarilar.append(f"Tahmini koşu süresi: {cfg['tahmini_sure']} (bu donanımda "
                        "kaba; uzunsa 'hizli' kalite ya da gece-boyu düşünün).")
    if regime == "supersonic" and lmax > 1.0:
        uyarilar.append(
            f"MALİYET: süpersonik shockFluid explicit/deltaT-limitli; Lmax≈{lmax:.1f} m "
            f"geometride tek nokta saatler sürebilir (~1M hücrede gün mertebesi). "
            f"Mesh '{quality}' seçildi (kaba). Trend için inviscid yeterli; mutlak Cd "
            f"veya yakınsamış sonuç için gece-boyu/HPC bütçesi planlayın.")
    if not geo.get("su_gecirmez"):
        uyarilar.append("Geometri su-geçirmez değil; dış-aero için sorun değil ama "
                        "ıslak alan (sürtünme) bir üst-tahmin olabilir.")
    if cls["guven"] < 0.45:
        uyarilar.append("Sınıflandırma güveni düşük — planı kontrol edin.")
    if info.get("birim_olcek"):
        uyarilar.append(f"Birim ölçeği uygulandı: {info['birim_olcek']} (Lmax={lmax:.2f} m).")
    # Birim sezgisi yalniz m ve mm'yi tanir; cm/inc girdide SESSIZCE yanlis
    # olcekler. Sonuc arac bandinin disindaysa bunu kullanici yuzune tasi —
    # aksi halde uyari info sozlugunde olu kalirdi.
    if info.get("birim_uyarisi"):
        uyarilar.append(info["birim_uyarisi"])
    if birim_notu:
        uyarilar.append(birim_notu)
    # GCI-öncülü (öğrenilen): geçmiş mesh-yakınsama sonuçlarından koşu-öncesi beklenti.
    # Yalnız PLAN uyarısıdır; ölçülen band değildir, UQ/rapora girmez (gci_advisor).
    try:
        from gci_advisor import advise as _gci_advise
        gp = _gci_advise(cls["metrik"], tip)
        if gp:
            cfg["gci_onculu"] = gp
            _pa = gp.get("asimptotik_olasilik")
            uyarilar.append(
                f"GCI-öncülü ({gp['n_destek']} geçmiş koşu): beklenen sayısal band "
                f"~%{gp['u_num_beklenen_pct']}, asimptotik-çıkma olasılığı "
                + (f"{_pa:.0%}" if _pa is not None else "HESAPLANMADI (ayırt edici değil)")
                + f". {gp['oneri']}")
    except Exception as e:
        # "Öncül bir şey söylemedi" ile "öncül HİÇ ÇALIŞMADI" ayrı durumlar; ikincisi
        # sessizken plan, olmayan bir deneyime dayanıyormuş gibi görünüyordu.
        uyarilar.append(f"GCI-öncülü okunamadı ({type(e).__name__}) — koşu-öncesi "
                        "sayısal band beklentisi YOK; plan yalnız kural-tabanlı.")
    # Mesh-öncülü (öğrenilen): benzer geometrilerin ayar→sonuç geçmişinden kalite/y⁺
    # önerisi. Kural seçimini EZMEZ — öner+onayla planında kullanıcıya gösterilir.
    try:
        from mentor import advise_mesh as _mesh_advise
        mp = _mesh_advise(cls["metrik"], tip)
        if mp:
            cfg["mesh_onculu"] = mp
            if mp.get("onerilen_kalite") and mp["onerilen_kalite"] != quality:
                uyarilar.append(
                    f"Mesh-öncülü ({mp['n_destek']} geçmiş koşu): bu geometri sınıfında "
                    f"'{mp['onerilen_kalite']}' kalite daha başarılı görünüyor "
                    f"(kural '{quality}' seçti; başarı oranları {mp['kalite_basari']}).")
            for r in mp.get("riskler", []):
                uyarilar.append("Mesh-öncülü risk: " + r)
            if mp.get("yplus_duzeltme"):
                uyarilar.append("y⁺-öncülü: " + mp["yplus_duzeltme"]["oneri"])
    except Exception as e:
        # Sessizken "öncül bir şey söylemedi" ile "öncül HİÇ ÇALIŞMADI" aynı görünüyordu.
        # Kural seçimi etkilenmez ama kullanıcı hangi durumda olduğunu bilmeli.
        uyarilar.append(f"Mesh-öncülü okunamadı ({type(e).__name__}) — plan yalnız "
                        "kural-tabanlı; geçmiş koşu deneyimi bu öneriye KATILMADI.")
    n_kutuphane = len(_load_cases())
    if n_kutuphane < MIN_CASES:
        uyarilar.append(f"Öğrenme: kütüphanede {n_kutuphane}/{MIN_CASES} onaylı vaka — "
                        "henüz yalnız kural-tabanlı. Onayladıkça isabet artacak.")
    elif cls.get("ogrenilen"):
        lv = cls["ogrenilen"]
        uyarilar.append(f"Öğrenme aktif: {lv['kutuphane']} vakalık kütüphane, en yakın "
                        f"{lv['komsu']} komşu → '{lv['tip']}' (%{lv['guven']*100:.0f}).")
    cfg["uyarilar"] = uyarilar
    cfg["gerekce"] = cls["gerekce"]
    return cfg


def apply_type_settings(cfg: dict, tip: str, dogrulama_modu: bool = False) -> dict:
    """Verilen araç tipine göre analiz ayarlarını (rejim/Mach/hız/AoA) + planı kur.
    auto_configure VE kullanıcı tip düzeltmesi bu eşlemeyi kullanır."""
    cfg["tip"] = tip
    cfg["vehicle_preset"] = PRESET_MAP.get(tip, "genel")   # CFD preset (GUI/pipeline)
    q = cfg.get("kalite", "standart")
    gv = f"%{cfg.get('guven', 0) * 100:.0f}"
    # önceki tipe ait anahtarları temizle
    for kkey in ("mach_listesi", "aoa_listesi", "hiz_ms", "viscous"):
        cfg.pop(kkey, None)
    if tip == "roket":
        cfg.update(rejim="supersonic", mach_listesi=[0.8, 1.2, 2.0, 3.0],
                   viscous=dogrulama_modu, analiz="cd_mach")
        cfg["plan"] = (f"Roket (güven {gv}) → süpersonik Cd-Mach taraması "
                       f"M={cfg['mach_listesi']}, {q} mesh, "
                       f"{'viskoz kΩ-SST' if dogrulama_modu else 'inviscid + analitik sürtünme'}.")
    elif tip == "kanatli_roket":
        cfg.update(rejim="supersonic", mach_listesi=[0.8, 1.2, 2.0, 3.0],
                   viscous=dogrulama_modu, analiz="cd_mach")
        cfg["plan"] = (f"Kanatlı roket/füze (güven {gv}) → süpersonik Cd-Mach "
                       f"M={cfg['mach_listesi']}, {q} mesh. HİBRİT: gövde roket gibi "
                       f"(dalga sürüklemesi) AMA kanatlar kaldırma/manevra üretir; "
                       f"sürükleme eğrisi geçerli, kaldırma için ek polar gerekebilir.")
    elif tip == "ucak":
        cfg.update(rejim="subsonic", hiz_ms=25.0, aoa_listesi=[0, 2, 4, 6, 8],
                   analiz="polar")
        cfg["plan"] = (f"Sabit-kanat (güven {gv}) → ses-altı polar tarama "
                       f"AoA={cfg['aoa_listesi']}°, U∞=25 m/s, {q} mesh (kaldırma-ilgili).")
    elif tip == "tilt_rotor":
        cfg.update(rejim="subsonic", hiz_ms=22.0, aoa_listesi=[0, 2, 4, 6, 8],
                   analiz="polar")
        cfg["plan"] = (f"Tilt-rotor/VTOL (güven {gv}) → ses-altı polar (yatay uçuş) "
                       f"AoA={cfg['aoa_listesi']}°, U∞=22 m/s, {q} mesh. HİBRİT: kanat "
                       f"kaldırması + rotor itkisi; bu analiz YATAY-uçuş aerodinamiğidir, "
                       f"dikey/geçiş rejimi (pervane indüklemesi) ayrı ele alınmalı.")
    elif tip == "kanatli_vtol":
        cfg.update(rejim="subsonic", hiz_ms=20.0, aoa_listesi=[0, 2, 4, 6, 8],
                   analiz="polar")
        cfg["plan"] = (f"Sabit-kanat VTOL/quadplane (güven {gv}) → ses-altı polar "
                       f"AoA={cfg['aoa_listesi']}°, U∞=20 m/s, {q} mesh. HİBRİT: "
                       f"yatay-uçuş kanat kaldırmasıyla; dağıtık rotorlar dikey-kalkış "
                       f"içindir, cruise sürüklemesinde durağan kabul edilir.")
    elif tip == "kaldirici_govde":
        cfg.update(rejim="supersonic", mach_listesi=[0.8, 1.2, 2.0, 3.0],
                   viscous=dogrulama_modu, analiz="cd_mach")
        cfg["plan"] = (f"Kaldırıcı gövde / uzay-uçağı (güven {gv}) → süpersonik "
                       f"Cd-Mach M={cfg['mach_listesi']}, {q} mesh. HİBRİT: kaldırma "
                       f"gövde şeklinden gelir (ayrık kanat yok); yüksek-Mach geri-giriş "
                       f"rejimi — L/D için ek hücum-açısı taraması gerekebilir.")
    elif tip == "multikopter":
        cfg.update(rejim="subsonic", hiz_ms=12.0, analiz="tekil")
        cfg["plan"] = (f"Multikopter (güven {gv}) → ses-altı tekil analiz "
                       f"U∞=12 m/s, {q} mesh (frontal referans).")
    elif tip == "araba":
        cfg.update(rejim="subsonic", hiz_ms=20.0, analiz="tekil")
        cfg["plan"] = (f"Kara aracı (güven {gv}) → ses-altı tekil analiz U∞=20 m/s, "
                       f"{q} mesh, frontal referans. ZEMİN-ETKİLİ: taban noSlip zemin "
                       f"düzlemi otomatik kurulur (clearance verilmezse Ahmed-oranı "
                       f"0.17·H); Cd yalnız zemin-etkili referanslarla kıyaslanır.")
    else:
        cfg.update(rejim="subsonic", hiz_ms=20.0, analiz="tekil")
        cfg["plan"] = (f"Genel cisim → muhafazakâr ses-altı tekil analiz "
                       f"U∞=20 m/s, {q} mesh. Tip belirsizse elle ayarlayın.")
    return cfg


def narrate(config: dict, result: dict | None = None) -> str:
    """HAKEM-seviyesi çevrimdışı yorumcu (API gerektirmez): otopilot kararını ve
    sonucu eleştirel/nicel değerlendirir — güven, öğrenme-kanıtı, rejim uygunluğu,
    sonuç makullüğü, V&V çekinceleri. ANTHROPIC_API_KEY varsa LLM ile zenginleştirir."""
    import os
    tip = config["tip"]
    conf = config.get("guven", 0)
    sat = [f"Sınıflandırma: '{tip}' (güven %{conf*100:.0f}). "
           f"Gerekçe: {', '.join(config.get('gerekce', [])) or '—'}."]

    # 1) Güven ve öğrenme-kanıtı eleştirisi (hakem bakışı)
    lv = config.get("ogrenilen")
    if lv and config.get("kural_tip") and lv["tip"] != config.get("kural_tip"):
        sat.append(f"⚠ Kural '{config['kural_tip']}' derken öğrenilen kütüphane "
                   f"({lv['kutuphane']} vaka) %{lv['guven']*100:.0f} ile '{lv['tip']}' "
                   f"dedi ve geçersiz kıldı; benzer onaylı vakalara dayandığından "
                   f"daha güvenilir, yine de gözle doğrulayın.")
    elif lv:
        sat.append(f"Öğrenilen kütüphane ({lv['kutuphane']} vaka) kuralı destekliyor "
                   f"(%{lv['guven']*100:.0f}) — sağlam sınıflandırma.")
    if conf < 0.45:
        sat.append("DÜŞÜK GÜVEN: geometri sınır bir durumda; planı elle gözden geçirin "
                   "veya tipi düzeltin (öğrenmeyi de besler).")

    # 2) Rejim/yöntem uygunluğu
    if tip == "roket":
        sat.append("Süpersonik Cd-Mach taraması doğru tercih (roketler M>1 uçar); "
                   "ancak inviscid+analitik-sürtünme YAKLAŞIK — mutlak Cd değil TREND "
                   "savunulabilir, mutlak değer için viskoz-duvar gerekir.")
    elif tip == "ucak":
        sat.append("Ses-altı polar (Cl-Cd) doğru; kaldırma-ilgili referans (planform) "
                   "kullanılmalı. Yüksek hücum açılarında ayrılma/stall RANS ile "
                   "yaklaşık, çekinceyle yorumlayın.")
    elif tip == "multikopter":
        sat.append("Ses-altı tekil analiz makul; pervane indüklemesi modellenmediğinden "
                   "gerçek itki-altı akıştan farklı olabilir (aktüatör-disk opsiyonu).")
    else:
        sat.append("Tip belirsiz → muhafazakâr ses-altı; sonuç yön-gösterici, "
                   "kritik karar için tipi netleştirin.")

    # 3) Sonuç değerlendirmesi + aykırılık + V&V
    if result and result.get("Cd_toplam") is not None:
        cd = result["Cd_toplam"]
        sat.append(f"Sonuç: C_D≈{cd:.3f}.")
        flag = cd_outlier(tip, cd)
        # Geometri-farkında öğrenilen ön-kestirim (KABA prior; LOO medyan-hata veriyle
        # düşüyor: 64-vaka %42 → 241-vaka %28; precise surrogate DEĞİL — bilgilendirici).
        pred = cd_predict(config.get("metrik", {}), tip)
        if pred and pred["guven"] >= 0.3:
            sat.append(f"Öğrenilen ön-kestirim ({pred['n_destek']} benzer geometri): "
                       f"C_D≈{pred['cd_tahmin']:.3f}±{pred['belirsizlik']:.3f} (kaba prior).")
            pflag = cd_prior_check(config.get("metrik", {}), tip, cd)
            if pflag:
                sat.append("⚠ " + pflag)
        if flag:
            sat.append("⚠ " + flag)
        else:
            sat.append("Sonuç bu tipteki geçmiş vakalarla tutarlı (aykırılık yok).")
        sat.append("V&V: çözücü küre deneyiyle doğrulanmış; tek mesh (GCI yok) → "
                   "mutlak değere belirsizlik bandı atanmamıştır.")

    base = " ".join(sat)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return base
    try:
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model="claude-opus-4-8", max_tokens=400,
            messages=[{"role": "user", "content":
                       "Şu hakem değerlendirmesini akıcı 3-4 cümleye getir (Türkçe, "
                       "nicel, eleştirel ton koru):\n" + base}])
        return msg.content[0].text
    except Exception:
        return base
