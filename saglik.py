"""Depo sağlık toplayıcısı — beş öz-denetim ölçeri tek komutta.

NEDEN: bu depoda beş ayrı ölçer var ve her biri kendi sorusunu soruyor —
`sessiz_yutma` (hata yutuluyor mu), `oksuz_alan` (üretilen alan okunuyor mu),
`oksuz_savunma` (savunma çağrılıyor mu), `kanal_ayrismasi` (bir kanal söylüyor
öbürü susuyor mu), `kanit` (kanıt üretilebilir ve taze mi). Beşini ayrı ayrı
koşmak, birini unutmayı kolaylaştırır; 2026-08-20'de tam bu oldu — dört
tarayıcının ortak BOM körlüğü ancak beşincisi yazılırken görüldü.

KENDİ KAPSAMINI DA BEYAN EDER. Bir ölçer içe aktarılamaz ya da düşerse
listeden SESSİZCE düşmez: satırı "ÖLÇÜLEMEDİ" olarak kalır ve toplam hüküm
"eksik kapsamla verildi" der. Bu, ölçerlerin kendi öğrettiği kuralın bir
kademe yukarısıdır — "0 açık madde" ancak neyin ölçüldüğü biliniyorsa
dayanaklıdır.

    python saglik.py            # tablo
    python saglik.py --json     # saglik.json
    python saglik.py --kapi     # açık madde varsa çıkış kodu 1 (CI için)
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))


def _sessiz_yutma() -> dict:
    import sessiz_yutma as m
    b = m.tara()
    inc = m.incelenmemis(b)
    return {"toplam": len(b), "acik": len(inc),
            "detay": f"{len(inc)} gerekçesiz / {len(b)} yutma "
                     f"({sum(x['guven_yolu'] for x in inc)} güven yolunda)",
            "taranamayan": list(dict.fromkeys(getattr(m, "ATLANAN", [])))}


def _oksuz_savunma() -> dict:
    import oksuz_savunma as m
    b = m.tara()
    acik = [x for x in b if not x["muaf"]]
    return {"toplam": len(b), "acik": len(acik),
            "detay": f"{len(acik)} çağrılmayan savunma "
                     f"({len(b) - len(acik)} gerekçeli muaf)",
            "taranamayan": list(dict.fromkeys(getattr(m, "ATLANAN", [])))}


def _oksuz_alan() -> dict:
    import oksuz_alan as m
    b = m.tara()
    return {"toplam": len(b), "acik": len(b),
            "detay": f"{len(b)} alan üretilir ama hiç okunmaz",
            "taranamayan": []}


def _kanal_ayrismasi() -> dict:
    import kanal_ayrismasi as m
    o = m.ozet()
    return {"toplam": o["toplam"], "acik": o["incelenmemis"],
            "detay": f"{o['incelenmemis']} gerekçesiz / {o['toplam']} ayrışma "
                     f"({o['kabul']} kabul)",
            "taranamayan": []}


def _kanit() -> dict:
    import kanit as m
    kayit = m.manifest()
    kanitlar = [k for k in kayit if k["sinif"] == "kanit"]
    komutsuz = [k for k in kanitlar if not k.get("uretim")]
    sessiz = [k for k in komutsuz if not k.get("uretim_beyanli")]
    bayat = [k for k in m.bayatlik(kayit) if k.get("bayat")]
    return {"toplam": len(kanitlar), "acik": len(sessiz) + len(bayat),
            "detay": f"{len(sessiz)} beyansız komutsuz, {len(bayat)} bayat "
                     f"/ {len(kanitlar)} kanıt "
                     f"({len(komutsuz) - len(sessiz)} beyanlı komutsuz)",
            "taranamayan": []}


OLCERLER = [
    ("sessiz_yutma", "hata sebebi yutuluyor mu", _sessiz_yutma),
    ("oksuz_savunma", "savunma çağrılıyor mu", _oksuz_savunma),
    ("oksuz_alan", "üretilen alan okunuyor mu", _oksuz_alan),
    ("kanal_ayrismasi", "bir kanal söylüyor öbürü susuyor mu", _kanal_ayrismasi),
    ("kanit", "kanıt üretilebilir ve taze mi", _kanit),
]


def topla() -> dict:
    sonuc = []
    for ad, soru, fn in OLCERLER:
        try:
            r = fn()
            r.update({"olcer": ad, "soru": soru, "olculdu": True})
        except Exception as e:            # noqa: BLE001 — sebebi KAYDEDILIYOR
            # Olcer duserse SESSIZCE listeden dusmez: satir kalir ve toplam
            # hukum "eksik kapsamla verildi" der.
            r = {"olcer": ad, "soru": soru, "olculdu": False,
                 "acik": None, "toplam": None, "taranamayan": [],
                 "detay": f"ÖLÇÜLEMEDİ: {type(e).__name__}: {e}",
                 "iz": traceback.format_exc()[-400:]}
        sonuc.append(r)

    olculemedi = [x for x in sonuc if not x["olculdu"]]
    acik = sum(x["acik"] or 0 for x in sonuc if x["olculdu"])
    kapsam_disi = [y for x in sonuc for y in x.get("taranamayan", [])]

    if olculemedi:
        verdikt = (f"⚠️ EKSİK KAPSAM: {len(olculemedi)} ölçer koşamadı "
                   f"({', '.join(x['olcer'] for x in olculemedi)}) — "
                   f"toplam hüküm onları KAPSAMAZ")
    elif acik or kapsam_disi:
        verdikt = (f"⚠️ {acik} açık madde"
                   + (f", {len(set(kapsam_disi))} dosya taranamadı"
                      if kapsam_disi else ""))
    else:
        verdikt = ("✅ Beş ölçer de sıfır açık madde bildiriyor; "
                   "taranamayan dosya yok")
    return {"vaka": "Depo sağlık toplayıcısı — beş öz-denetim ölçeri",
            "_uretim": "Üretim: python saglik.py --json",
            "verdikt": verdikt, "acik_toplam": acik,
            "olculemeyen": [x["olcer"] for x in olculemedi],
            "kapsam_disi": list(dict.fromkeys(kapsam_disi)),
            "olcerler": sonuc}


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = topla()
    print(f"{'ölçer':<18}{'açık':>6}  soru / detay")
    print("-" * 78)
    for x in r["olcerler"]:
        im = "—" if not x["olculdu"] else ("✅" if not x["acik"] else "❗")
        sayi = "—" if x["acik"] is None else str(x["acik"])
        print(f"{im} {x['olcer']:<16}{sayi:>5}  {x['soru']}")
        print(f"{'':24}{x['detay']}")
    if r["kapsam_disi"]:
        print("\n  ⚠ TARANAMAYAN dosyalar (hüküm bunları kapsamaz):")
        for y in r["kapsam_disi"]:
            print(f"    {y}")
    print(f"\n{r['verdikt']}")

    if "--json" in sys.argv:
        (KOK / "saglik.json").write_text(
            json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("-> saglik.json")
    if "--kapi" in sys.argv and (r["acik_toplam"] or r["olculemeyen"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
