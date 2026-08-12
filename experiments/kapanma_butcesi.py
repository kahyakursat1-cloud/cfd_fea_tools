"""Kapanmayan hücre için "ne gerekir" — gerekçe değil, SAYI.

NEDEN: model-form tablosunun boş hücreleri gerekçe taşıyor ama gerekçeler
NİTELİKSEL. "Referans belirsizliği baskın", "ağ inceltmekle kapanmaz" gibi
cümleler doğrulanabilir değil; oysa ASME V&V 20 ayrılabilirlik ölçütü
kapalı formda ve tersi alınabilir:

    ayrılabilir  ⟺  |E| > u_val = √(u_num² + u_D²)

Buradan hücrenin kapanması için GEREKEN sayısal band doğrudan çıkar:

    u_num* = √(E² − u_D²)      (E > u_D ise; değilse hiçbir ağ kapatmaz)

u_num* TEK BAŞINA YANILTICIDIR ve bu betiğin asıl kattığı şey bu uyarıdır:
o bandda marj tam olarak SIFIRDIR (tanım gereği |E| = u_val). Kullanılabilir
bir hüküm için paydan pay istemek gerekir --- burada |E| ≥ 1{,}2·u_val, yani

    u_num** = √((E/1,2)² − u_D²)

ve iki sayı arasındaki fark küçük değildir: NACA0012 AR6 kanadında u_num* = %10
iken u_num** = %1,1'dir. Yani "ağ %10'a inerse kapanır" cümlesi doğru ama
pratikte işe yaramaz; kapanmanın ANLAMLI olması için band on altı kat düşmeli.

NE BULUNMADI: bu betik yazılırken "gerekçe yanlıştı, baskın terim u_num'du"
diye bir bulgu iddia edildi ve GERİ ALINDI. Rapor §Ayrılabilirlik zaten aynı
hesabı yapmış ve %10 eşiğini türetmiş durumda; betik onun yerine geçmez,
hesabı tek çapadan ON BİR çapaya taşır ve marjı ekler.

ÖNKOŞUL: model_form_bandi.json güncel olmalı
    python experiments/model_form_bandi.py

    python experiments/kapanma_butcesi.py
Çıktı: kapanma_butcesi.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

KAYNAK = KOK / "model_form_bandi.json"
CIKTI = KOK / "kapanma_butcesi.json"

# Kullanilabilir ayrilabilirlik icin istenen pay. 1.0 = sifir marj (tanim
# geregi |E| = u_val) ve o noktada hukum tek bir olcum gurultusuyle donebilir.
# 1.2 kesin degil, BEYAN EDILMIS bir secimdir; ciktida acikca tasinir.
MARJ = 1.2


def butce(E_pct: float | None, u_num_pct: float | None,
          u_D_pct: float | None) -> dict:
    """Bir çapa için kapanma bütçesi. Hüküm ÜRETİR, açıklama değil."""
    if E_pct is None or u_num_pct is None:
        return {"durum": "ölçülemedi", "neden": "|E| veya u_num yok"}
    if u_D_pct is None:
        return {"durum": "referans belirsizliği BEYAN EDİLMEMİŞ",
                "neden": ("u_D bilinmeden kapanma bütçesi hesaplanamaz; "
                          "u_val yalnız sayısal banda dayanır ve gerçek "
                          "u_val bundan BÜYÜKTÜR")}
    E, un, uD = abs(float(E_pct)), float(u_num_pct), float(u_D_pct)
    u_val = math.hypot(un, uD)
    if uD >= E:
        return {"durum": "AĞ ÇARE DEĞİL", "u_val_pct": round(u_val, 2),
                "ayrilabilir_mi": False, "gereken_u_num_pct": None,
                "baskin_terim": "u_D" if uD >= un else "u_num",
                "neden": (f"|E|={E:.2f} ≤ u_D={uD:.2f}: sayısal band sıfır olsa "
                          f"bile u_val ≥ u_D ve fark ayırt edilemez. "
                          f"REFERANS değişmeli.")}
    gereken = math.sqrt(E * E - uD * uD)
    # MARJLI esik: u_num* bandinda marj tam olarak SIFIRDIR (|E| = u_val).
    # Kullanilabilir hukum icin |E| >= MARJ * u_val istenir.
    hedef = (E / MARJ) ** 2 - uD * uD
    marjli = math.sqrt(hedef) if hedef > 0 else None
    out = {
        "durum": "ayrılabilir" if u_val < E else "AĞ ÇARE OLABİLİR",
        "u_val_pct": round(u_val, 2),
        "ayrilabilir_mi": bool(u_val < E),
        "gereken_u_num_pct": round(gereken, 2),
        "marjli_u_num_pct": round(marjli, 2) if marjli else None,
        "mevcut_u_num_pct": round(un, 2),
        "kac_kat_azalmali": round(un / gereken, 2) if gereken > 0 else None,
        "marjli_kac_kat": round(un / marjli, 1) if marjli else None,
        "baskin_terim": "u_num" if un > uD else "u_D",
    }
    if u_val < E:
        out["neden"] = f"|E|={E:.2f} > u_val={u_val:.2f}: hücre zaten ayrılabilir."
        return out
    if marjli is None:
        out["durum"] = "AĞ KURTARMAZ (marj yok)"
        out["neden"] = (
            f"|E|={E:.2f} > u_D={uD:.2f} ama pay yok: u_num sıfır olsa bile "
            f"|E| < {MARJ}·u_D. Sıfır-marjlı eşik u_num<%{gereken:.2f} "
            f"matematiksel, kullanılabilir değil. REFERANS değişmeli.")
        return out
    out["neden"] = (
        f"|E|={E:.2f} > u_D={uD:.2f}: ağ inceltmek hücreyi KAPATABİLİR. "
        f"Sıfır-marjlı eşik u_num<%{gereken:.2f}; {MARJ}× paylı eşik "
        f"u_num<%{marjli:.2f} (şu an %{un:.2f}, {un / marjli:.1f}× azalma).")
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not KAYNAK.exists():
        print("model_form_bandi.json yok — önce o betik koşulmalı")
        return 1
    d = json.loads(KAYNAK.read_text(encoding="utf-8"))

    satirlar = []
    for c in d.get("capalar", []):
        b = butce(c.get("ham_sapma_pct"), c.get("u_sayisal_pct"),
                  c.get("u_ref_pct"))
        satirlar.append({"capa": c.get("capa"), "rejim": c.get("rejim"),
                         "ham_sapma_pct": c.get("ham_sapma_pct"),
                         "u_sayisal_pct": c.get("u_sayisal_pct"),
                         "u_ref_pct": c.get("u_ref_pct"), **b})

    kapatilabilir = [s for s in satirlar if s.get("durum") == "AĞ ÇARE OLABİLİR"]
    referans_bekleyen = [s for s in satirlar
                         if s.get("durum") in ("AĞ ÇARE DEĞİL",
                                               "AĞ KURTARMAZ (marj yok)")]
    beyansiz = [s for s in satirlar
                if s.get("durum") == "referans belirsizliği BEYAN EDİLMEMİŞ"]
    rec = {
        "vaka": "Kapanma bütçesi — hangi hücreyi AĞ, hangisini REFERANS kapatır",
        "_neden": ("Bos hucrelerin gerekcesi NITELIKSELDI ('referans baskin', "
                   "'ag kapatmaz'). ASME V&V 20 olcutu tersine cevrilince ayni "
                   "soru SAYIYLA cevaplaniyor."),
        "_formul": ("ayrilabilir <=> |E| > sqrt(u_num^2 + u_D^2); "
                    f"u_num* = sqrt(E^2 - u_D^2); "
                    f"u_num** = sqrt((E/{MARJ})^2 - u_D^2)"),
        "_marj": MARJ,
        "satirlar": satirlar,
        "ag_kapatabilir": [s["capa"] for s in kapatilabilir],
        "referans_bekleyen": [s["capa"] for s in referans_bekleyen],
        "u_D_beyan_edilmemis": [s["capa"] for s in beyansiz],
        "_kisit": ("u_num* GEREK sarti verir, YETER sarti degil: ag inceltmek "
                   "u_num'u o bandin altina indirebilirse hucre kapanir; "
                   "indiremeyecegi de olcumle gorulur. Ayrica |E| ag ile birlikte "
                   "DEGISIR (model hatasi sabit degil, olculen sapma degisir) --- "
                   "hedef sabit bir esik degil, hareketli bir hedeftir."),
        "_uretim": "Üretim: python experiments/kapanma_butcesi.py",
    }
    rec["verdikt"] = (
        f"{len(satirlar)} çapa incelendi. {len(kapatilabilir)} çapada ağ inceltmek "
        f"hücreyi kapatabilir; {len(referans_bekleyen)} çapada kapatamaz "
        f"(|E| ≤ u_D ya da {MARJ}× pay bırakacak band yok) — orada REFERANS "
        f"değişmeli. {len(beyansiz)} çapada u_D HİÇ BEYAN EDİLMEMİŞ: onların "
        f"ayrılabilirlik hükmü yalnız sayısal banda dayanıyor ve gerçek u_val "
        f"bundan büyüktür.")

    import ortam
    ortam.damgala(rec)
    CIKTI.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")

    print(rec["vaka"] + "\n" + "=" * 78)
    for s in satirlar:
        if s.get("gereken_u_num_pct") is None and "u_val_pct" not in s:
            print(f"{s['capa']:<28} {s['durum']}")
            continue
        print(f"{s['capa']:<28} |E|={s['ham_sapma_pct']:>6.2f} "
              f"u_num={s['u_sayisal_pct']:>6.2f} u_D={s['u_ref_pct']}  "
              f"-> {s['durum']}")
        if s.get("gereken_u_num_pct") is not None and not s["ayrilabilir_mi"]:
            m = (f"{MARJ}× paylı %{s['marjli_u_num_pct']} "
                 f"({s['marjli_kac_kat']}× azalma)"
                 if s.get("marjli_u_num_pct") else "paylı eşik YOK")
            print(f"{'':<28} sıfır-marjlı %{s['gereken_u_num_pct']} · {m}")
    print("=" * 78)
    print(rec["verdikt"])
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
