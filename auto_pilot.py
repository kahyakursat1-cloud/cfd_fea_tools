"""Analiz otopilotu — geometriden araç tipini sınıflandırır ve TÜM analiz
ayarlarını (rejim, Mach/hız, mesh kalitesi, viskoz/inviscid, referans) deterministik
olarak seçer. "Öner + onayla": bir plan + gerekçe döner; GUI gösterir, kullanıcı
onaylayınca koşar. LLM yorumcu opsiyonel (model yoksa şablon fallback).
================================================================================
Karar mantığı kural-tabanlıdır (LLM değil): CFD ayarları tekrarlanabilir ve
savunulabilir olmalı. LLM yalnız SONUCU yorumlar, ayar SEÇMEZ.
"""
from __future__ import annotations

import math
from pathlib import Path

from vehicle_pipeline import inspect_geometry, prepare_geometry


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
    return {"tip": vtype, "guven": round(conf, 2),
            "metrik": {"L_D": round(slender, 2), "planform_frontal": round(planform_ratio, 2),
                       "W_L": round(span_ratio, 2), "H_L": round(compact, 2),
                       "govde": bodies},
            "gerekce": reasons}


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
           "su_gecirmez": geo.get("su_gecirmez"), "lmax_m": lmax,
           "olcek_notu": info.get("birim_olcek")}

    if tip == "roket":
        cfg.update(rejim="supersonic", mach_listesi=[0.8, 1.2, 2.0, 3.0],
                   viscous=dogrulama_modu, analiz="cd_mach")
        plan = (f"Roket (güven %{cls['guven']*100:.0f}) → süpersonik Cd-Mach taraması "
                f"M={cfg['mach_listesi']}, {quality} mesh, "
                f"{'viskoz kΩ-SST' if dogrulama_modu else 'inviscid + analitik sürtünme'}.")
    elif tip == "ucak":
        cfg.update(rejim="subsonic", hiz_ms=25.0, aoa_listesi=[0, 2, 4, 6, 8],
                   analiz="polar")
        plan = (f"Sabit-kanat (güven %{cls['guven']*100:.0f}) → ses-altı polar tarama "
                f"AoA={cfg['aoa_listesi']}°, U∞=25 m/s, {quality} mesh (kaldırma-ilgili).")
    elif tip == "multikopter":
        cfg.update(rejim="subsonic", hiz_ms=12.0, analiz="tekil")
        plan = (f"Multikopter (güven %{cls['guven']*100:.0f}) → ses-altı tekil analiz "
                f"U∞=12 m/s, {quality} mesh (frontal referans).")
    else:
        cfg.update(rejim="subsonic", hiz_ms=20.0, analiz="tekil")
        plan = (f"Genel cisim (düşük güven) → muhafazakâr ses-altı tekil analiz "
                f"U∞=20 m/s, {quality} mesh. Tip belirsiz; gerekirse elle ayarlayın.")

    uyarilar = []
    if not geo.get("su_gecirmez"):
        uyarilar.append("Geometri su-geçirmez değil; dış-aero için sorun değil ama "
                        "ıslak alan (sürtünme) bir üst-tahmin olabilir.")
    if cls["guven"] < 0.45:
        uyarilar.append("Sınıflandırma güveni düşük — planı kontrol edin.")
    if info.get("birim_olcek"):
        uyarilar.append(f"Birim ölçeği uygulandı: {info['birim_olcek']} (Lmax={lmax:.2f} m).")
    cfg["plan"] = plan
    cfg["uyarilar"] = uyarilar
    cfg["gerekce"] = cls["gerekce"]
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
