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

from vehicle_pipeline import inspect_geometry, prepare_geometry

# ── Öğrenme: büyüyen vaka kütüphanesi (instance-based / k-NN) ────────────────
MEMORY = Path(__file__).parent / "auto_pilot_memory.jsonl"
MIN_CASES = 8        # bu sayıdan az onaylı vaka varken yalnız kural-tabanlı
TIPLER = ("roket", "ucak", "multikopter", "genel")


def _features(metrik: dict) -> list:
    """k-NN için normalize özellik vektörü (hepsi ~[0,1])."""
    return [min(metrik.get("L_D", 0), 30) / 30, metrik.get("W_L", 0),
            metrik.get("H_L", 0), metrik.get("H_W", 0),
            min(metrik.get("govde", 1), 8) / 8]


def record_case(metrik: dict, otopilot_tip: str, onayli_tip: str,
                result: dict | None = None, dosya: str = "") -> None:
    """Onaylanan/düzeltilen analizi kütüphaneye ekle (öğrenme sinyali)."""
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M"), "dosya": dosya, "metrik": metrik,
           "otopilot_tip": otopilot_tip, "onayli_tip": onayli_tip,
           "cd_toplam": (result or {}).get("Cd_toplam"),
           "rejim": (result or {}).get("rejim")}
    with open(MEMORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load_cases() -> list:
    if not MEMORY.exists():
        return []
    out = []
    for line in MEMORY.read_text(encoding="utf-8").splitlines():
        try:
            c = json.loads(line)
            if c.get("onayli_tip") and c.get("metrik"):
                out.append(c)
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


def cd_outlier(vtype: str, cd: float) -> str | None:
    """Birikmiş aynı-tip Cd dağılımına göre aykırı sonuç bayrağı."""
    if cd is None:
        return None
    vals = [c["cd_toplam"] for c in _load_cases()
            if c.get("onayli_tip") == vtype and c.get("cd_toplam")]
    if len(vals) < 5:
        return None
    mu = sum(vals) / len(vals)
    sd = (sum((v - mu) ** 2 for v in vals) / len(vals)) ** 0.5
    sd_eff = max(sd, 0.1 * abs(mu))   # özdeş değerlerde göreli taban
    if sd_eff > 0 and abs(cd - mu) > 2.5 * sd_eff:
        return (f"C_D={cd:.3f}, bu tipteki {len(vals)} vakanın ortalamasından "
                f"({mu:.3f}±{sd:.3f}) belirgin sapıyor — geometri/ayar kontrolü önerilir.")
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
    # Multikopter: kompakt + geniş + çok-gövdeli (kollar)
    if compact >= 0.3 and span_ratio >= 0.55 and slender < 4 and bodies >= 2:
        score["multikopter"] += compact + 0.5
        reasons.append(f"kompakt (H/L≈{compact:.2f}), çok-gövde ({bodies} kol)")

    vtype = max(score, key=score.get)
    total = sum(v for v in score.values() if v > 0)
    conf = score[vtype] / total if total else 0.3
    metrik = {"L_D": round(slender, 2), "W_L": round(span_ratio, 2),
              "H_L": round(compact, 2), "H_W": round(flatness, 2),
              "planform_frontal": round(planform_ratio, 2), "govde": bodies}
    out = {"tip": vtype, "guven": round(conf, 2), "metrik": metrik,
           "gerekce": reasons, "kural_tip": vtype}
    # Öğrenme: birikmiş kütüphane yeterliyse k-NN oyunu harmanla
    lv = learned_vote(metrik)
    if lv:
        out["ogrenilen"] = lv
        if lv["guven"] >= 0.6 and lv["tip"] != vtype:
            # öğrenilen kanıt güçlü ve kuraldan farklı -> öğrenileni öne al
            out["tip"] = lv["tip"]
            out["gerekce"] = (reasons + [f"öğrenilen kütüphane ({lv['kutuphane']} vaka): "
                                         f"{lv['komsu']} komşunun %{lv['guven']*100:.0f}'i "
                                         f"'{lv['tip']}' → kural ('{vtype}') geçersiz kılındı"])
            out["guven"] = round((conf + lv["guven"]) / 2, 2)
    return out


def _quality_for(lmax_m: float, faces: int) -> str:
    """Boyut + üçgen sayısına göre mesh kalitesi (büyük/karmaşık → daha kaba)."""
    if lmax_m > 3.0 or faces > 200_000:
        return "hizli"        # büyük/ağır geometri → hücre bütçesini koru
    if lmax_m < 0.5 and faces < 20_000:
        return "hassas"       # küçük/basit → ince çözebiliriz
    return "standart"


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
    quality = _quality_for(lmax, geo.get("ucgen_sayisi", 0))

    cfg = {"stl": str(prep), "tip": tip, "kalite": quality,
           "guven": cls["guven"], "metrik": cls["metrik"],
           "kural_tip": cls.get("kural_tip"), "ogrenilen": cls.get("ogrenilen"),
           "su_gecirmez": geo.get("su_gecirmez"), "lmax_m": lmax,
           "olcek_notu": info.get("birim_olcek")}

    apply_type_settings(cfg, tip, dogrulama_modu)

    uyarilar = []
    if not geo.get("su_gecirmez"):
        uyarilar.append("Geometri su-geçirmez değil; dış-aero için sorun değil ama "
                        "ıslak alan (sürtünme) bir üst-tahmin olabilir.")
    if cls["guven"] < 0.45:
        uyarilar.append("Sınıflandırma güveni düşük — planı kontrol edin.")
    if info.get("birim_olcek"):
        uyarilar.append(f"Birim ölçeği uygulandı: {info['birim_olcek']} (Lmax={lmax:.2f} m).")
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
    elif tip == "ucak":
        cfg.update(rejim="subsonic", hiz_ms=25.0, aoa_listesi=[0, 2, 4, 6, 8],
                   analiz="polar")
        cfg["plan"] = (f"Sabit-kanat (güven {gv}) → ses-altı polar tarama "
                       f"AoA={cfg['aoa_listesi']}°, U∞=25 m/s, {q} mesh (kaldırma-ilgili).")
    elif tip == "multikopter":
        cfg.update(rejim="subsonic", hiz_ms=12.0, analiz="tekil")
        cfg["plan"] = (f"Multikopter (güven {gv}) → ses-altı tekil analiz "
                       f"U∞=12 m/s, {q} mesh (frontal referans).")
    else:
        cfg.update(rejim="subsonic", hiz_ms=20.0, analiz="tekil")
        cfg["plan"] = (f"Genel cisim → muhafazakâr ses-altı tekil analiz "
                       f"U∞=20 m/s, {q} mesh. Tip belirsizse elle ayarlayın.")
    return cfg


def narrate(config: dict, result: dict | None = None) -> str:
    """LLM yorumcu (opsiyonel). ANTHROPIC_API_KEY varsa Claude ile doğal-dil
    yorum; yoksa yapılandırılmış şablon fallback (her zaman çalışır, çevrimdışı)."""
    import os
    base = (f"Otopilot bu geometriyi '{config['tip']}' olarak sınıflandırdı "
            f"(güven %{config.get('guven', 0)*100:.0f}; {', '.join(config.get('gerekce', [])) or '—'}). "
            f"Seçilen plan: {config.get('plan', '')}")
    if result and result.get("Cd_toplam") is not None:
        base += f" Sonuç: C_D≈{result['Cd_toplam']:.3f}."
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return base + " [Şablon yorum — doğal-dil yorum için ANTHROPIC_API_KEY tanımlayın.]"
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-opus-4-8", max_tokens=400,
            messages=[{"role": "user", "content":
                       "Bir CFD otopilotunun kararını ve sonucunu bir havacılık "
                       "mühendisi gibi 3-4 cümlede yorumla (Türkçe, nicel, eleştirel):\n"
                       + base + f"\nKonfig: {config}\nSonuç: {result}"}])
        return msg.content[0].text
    except Exception:
        return base + " [LLM çağrısı başarısız; şablon yoruma düşüldü.]"
