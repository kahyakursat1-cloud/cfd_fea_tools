"""Yüzey-basınç Cd ile iz-momentum Cd'nin AYRIŞMASI — kaç, nerede, ne kadar.

NEDEN: makale (§5.2 ve §Tartışma) uzak-alan çapraz kontrolünün ince cisimlerde
``~\\%18'' ayrıştığını iki yerde yazıyor ama bu sayının arkasında bir kanıt
dosyası YOKTU; 36 iddialık denetimde de yer almıyordu. Elle taşınan bir sayı,
kanıt yenilendiğinde sessizce eskir --- bu deponun tekrar tekrar ölçtüğü kusur.

Betik depodaki TÜM araç koşularını tarar ve iki bağımsız sürükleme kestirimini
eşleştirir. İkisi de aynı çözümden gelir, yani bu bir DOĞRULAMA değil, yöntem
tutarlılığı ölçümüdür: yüzey integrali (≈1. mertebe, firar-kenarı ve
çözünürlüğe duyarlı) ile kontrol-hacmi iz-momentum integrali (2. mertebe)
uyuşmuyorsa ağ o gövdeyi çözmüyor demektir.

    python experiments/farfield_capraz_kontrol.py
Çıktı: farfield_capraz_kontrol.json
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent

# Gövde biçimi ekseni: eksenel-narin (roket) ve kanat-baskın (ucak) INCE;
# genel gövdeler ve multikopter çerçevesi KÜT. Bu ayrım ÖNCEDEN yapılır ve
# sonuca göre seçilmez --- aksi halde ölçüm kendi hipotezini onaylar.
INCE_TIPLER = {"roket", "ucak"}

# İz çıkarımının BAŞARISIZ sayıldığı eşik: iki kestirim bu kadar ayrışıyorsa
# ölçüm değil, arıza vardır (iz düzlemi gövdeyi kesmemiş ya da maske tutmamış).
ARIZA_ESIGI_PCT = 100.0


def _tip(d: dict, yol: Path) -> str:
    t = (d.get("vehicle_type") or "").strip().lower()
    return t or yol.parent.name.split("_")[0]


def topla() -> dict:
    kayitlar = []
    okunamayan: list[str] = []
    for f in sorted((KOK / "vehicle_runs").rglob("sonuc.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            # SESSİZCE ATLAMAK korpusu yanlı hale getirir: okunamayan dosya
            # sayılmazsa "108 vakada medyan %7,1" ifadesi kaç vakanın düştüğünü
            # gizler. Dosya sayılır ve çıktıya yazılır.
            okunamayan.append(f"{f.relative_to(KOK)}: {type(e).__name__}")
            continue
        cd, cw = d.get("cd"), d.get("cd_wake")
        if not cd or not cw or cd <= 0:
            continue
        fark = abs(cd - cw) / cd * 100.0
        kayitlar.append({
            "vaka": str(f.parent.relative_to(KOK / "vehicle_runs")).replace("\\", "/"),
            "tip": _tip(d, f), "cd_yuzey": round(cd, 5), "cd_iz": round(cw, 5),
            "fark_pct": round(fark, 2),
            "isaretli_pct": round((cw - cd) / cd * 100.0, 2),
            "ariza": fark > ARIZA_ESIGI_PCT,
        })

    saglam = [k for k in kayitlar if not k["ariza"]]
    ince = [k for k in saglam if k["tip"] in INCE_TIPLER]
    kut = [k for k in saglam if k["tip"] not in INCE_TIPLER]

    def ozet(g: list[dict]) -> dict:
        f = sorted(k["fark_pct"] for k in g)
        if not f:
            return {"n": 0}
        # İŞARETLİ fark ayrıca verilir. Mutlak fark "ne kadar ayrışıyor" der ama
        # YÖNÜ gizler; ölçüldüğünde küt gövdelerde iz-integralinin yüzey
        # integralini neredeyse HER vakada aştığı görüldü. Yönlü bir sapma
        # saçılmadan farklı bir şeydir: nedeni vardır ve aranabilir.
        s = sorted(k["isaretli_pct"] for k in g)
        return {"n": len(f), "medyan_pct": round(statistics.median(f), 2),
                "ortalama_pct": round(statistics.fmean(f), 2),
                "p90_pct": round(f[min(len(f) - 1, int(0.9 * len(f)))], 2),
                "maks_pct": round(f[-1], 2),
                "esik10_ustu_oran": round(sum(x > 10 for x in f) / len(f), 3),
                "isaretli_medyan_pct": round(statistics.median(s), 2),
                "iz_buyuk_sayisi": sum(x > 0 for x in s),
                "iz_buyuk_orani": round(sum(x > 0 for x in s) / len(s), 3)}

    return {
        "_neden": ("Makale iz-momentum ayrışmasını '~%18' diye iki yerde yazıyordu; "
                   "arkasında kanıt dosyası yoktu. Bu dosya o sayıyı ölçüme bağlar."),
        "_uretim": "python experiments/farfield_capraz_kontrol.py",
        "ariza_esigi_pct": ARIZA_ESIGI_PCT,
        "ince_tipler": sorted(INCE_TIPLER),
        "n_toplam": len(kayitlar),
        "n_ariza": sum(k["ariza"] for k in kayitlar),
        "n_okunamayan": len(okunamayan),
        "okunamayanlar": okunamayan,
        "tumu": ozet(saglam), "ince_govde": ozet(ince), "kut_govde": ozet(kut),
        # Tip bazında da verilir: ikili ince/küt ayrımı bir YORUMDUR,
        # tip kırılımı ise ham gözlemdir. Okuyucu yorumu denetleyebilsin.
        "tip_bazinda": {t: ozet([k for k in saglam if k["tip"] == t])
                        for t in sorted({k["tip"] for k in saglam})},
        "kayitlar": kayitlar,
    }


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    d = topla()

    # KORPUS DONDURULUR. Tarama "bugün vehicle_runs'ta ne varsa" üzerinden
    # çalışır ve depo sahibi bir analiz koştuğunda BÜYÜR: ölçüldü (2026-08-15),
    # tek bir tesisat koşusu vaka sayısını 108'den 109'a, ince-gövde medyanını
    # \\%6,38'den \\%6,62'ye taşıdı. Makalede yayımlanan bir sayı yazarın
    # gelişigüzel koşularına bağlı olamaz --- hakem onu yeniden üretemez.
    # `--dondur` o anki vaka listesini ve istatistikleri ayrı bir dosyaya yazar;
    # makalenin kanıt denetimi DONDURULMUŞ dosyayı okur. Canlı tarama ile
    # dondurulmuş dosya arasındaki fark bir SAPMA sinyalidir, sessiz bir
    # güncelleme değil.
    (KOK / "farfield_capraz_kontrol.json").write_text(
        json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    if "--dondur" in sys.argv:
        d["_dondurma_notu"] = (
            "Makale bu dosyayı okur. Canlı tarama (farfield_capraz_kontrol.json) "
            "yeni koşularla büyür; bu dosya YALNIZ --dondur ile güncellenir ve "
            "yayımlanan sayıların kaynağıdır.")
        (KOK / "farfield_korpus_dondurulmus.json").write_text(
            json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        print("-> farfield_korpus_dondurulmus.json (makale bunu okur)")
    print(f"vaka: {d['n_toplam']} (arıza {d['n_ariza']})")
    for ad in ("tumu", "ince_govde", "kut_govde"):
        o = d[ad]
        if o.get("n"):
            print(f"  {ad:11s} n={o['n']:3d}  medyan %{o['medyan_pct']:5.2f}  "
                  f"p90 %{o['p90_pct']:5.2f}  maks %{o['maks_pct']:6.2f}  "
                  f"| işaretli %{o['isaretli_medyan_pct']:+6.2f}  "
                  f"iz>yüzey {o['iz_buyuk_sayisi']}/{o['n']}")
    print("-> farfield_capraz_kontrol.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
