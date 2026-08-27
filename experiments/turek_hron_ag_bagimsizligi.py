"""Turek--Hron CFD1: ağ-bağımsızlığı --- kayıtta bir turdur açık duran kısıt.

NEDEN. CFD1 sürüklemeyi %0,05, taşımayı %0,86 içinde tutturdu ve o gün
not düşüldü: ``bu bir çapa değil, bir eğilimdir --- ağ-bağımsızlığı
SINANMADI''. Bu betik o notu kapatır.

ÇALIŞMA BİR HATA AVI SIRASINDA YAZILDI VE AV YANLIŞ YERDEYDİ. O sırada
iki-yönlü FSI1 koşusu düşey sehimi referansın %77 üstünde veriyordu; ağ,
en güçlü şüphelilerden biriydi. Sonradan görüldü ki kusur ağda değil,
iki-yönlü döngünün kendisindeydi (tur artıkları temizlenmediği için her
tur bayat basıncı okuyordu). Düzeltilince FSI1 %2,3'e oturdu.

ÖLÇÜMÜN DEĞERİ BUNDAN ETKİLENMEZ: soru ``ağ yeterli mi'' idi ve cevap
alındı. Yanlış olan gerekçe değil, o gün hangi sorunun ACİL olduğuna dair
tahminimdi.

NE ÖLÇER. Aynı geometriden dört seviyeli bir aile üretir (hücre boyu
ölçeklenir, sabit oran), her seviyede CFD1'i koşar ve sürükleme ile
taşımayı ayrı ayrı raporlar. Üç en ince seviyeden Richardson/GCI, dördü
birden varsa Eça--Hoekstra en-küçük-kareler bandı hesaplanır.

NE ÖLÇMEZ. Bu bir CFD1 (rijit) çalışmasıdır. FSI1'in kendi ağ duyarlılığı
buradan TÜRETİLMEZ; deforme ağda dağılım başka türlü davranabilir.
Yapısal ağ da bu ailenin dışındadır.

    python experiments/turek_hron_ag_bagimsizligi.py
Çıktı: turek_hron_ag_bagimsizligi.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from turek_hron_cfd1 import REF, _kos, _kur, _kuvvet_oku, _rezidueller  # noqa: E402
from turek_hron_gmsh import msh_yaz  # noqa: E402

from report_generator import least_squares_gci  # noqa: E402
from validation_gci import gci_richardson  # noqa: E402

CIKTI = KOK / "turek_hron_ag_bagimsizligi.json"
IS = KOK / "turek_hron_ag_ailesi"

# HUCRE BOYU OLCEKLERI. Sabit oran r = 1,3 (h cinsinden), yani 2B'de hucre
# sayisi ~1,69 kat artar. Uretim agi olcek 1,0'dir ve aileye DAHILDIR ---
# boylece bugune kadar yayimlanan sayinin ailenin neresinde durdugu
# gorulur. En ince seviye 0,77 uretim aginin ~1,7 kati hucre demektir ve
# bu makinede dakikalar mertebesindedir.
OLCEKLER = (1.6, 1.3, 1.0, 0.77)
R = 1.3


def _seviye(olcek: float) -> dict:
    msh = IS / f"th_{olcek:g}.msh"
    vaka = IS / f"case_{olcek:g}"
    bilgi = msh_yaz(msh, olcek)
    if not bilgi.get("uretildi", True) and "hucre_boyu_govde_m" not in bilgi:
        return {"olcek": olcek, "kosdu": False, "neden": bilgi.get("neden")}
    _kur(vaka, msh)
    adim = _kos(vaka, "gmshToFoam turek_hron_2b.msh > log.gmshToFoam 2>&1")
    if adim["rc"] != 0:
        return {"olcek": olcek, "kosdu": False, "neden": "gmshToFoam düştü"}
    b = vaka / "constant" / "polyMesh" / "boundary"
    b.write_text(re.sub(r"(yanlar\s*\{[^}]*?type\s+)\w+;", r"\1empty;",
                        b.read_text(errors="replace"), flags=re.S),
                 encoding="utf-8")
    adim = _kos(vaka, "simpleFoam > log.simpleFoam 2>&1", tmo=7200)
    if adim["rc"] != 0:
        return {"olcek": olcek, "kosdu": False, "neden": "simpleFoam düştü"}
    kuvvet = _kuvvet_oku(vaka)
    rez = _rezidueller(vaka)
    hucre = _hucre_say(vaka)
    return {
        "olcek": olcek, "kosdu": bool(kuvvet.get("okundu")),
        "hucre": hucre,
        # KARAKTERISTIK BOY 2B'de sqrt(A/N) ile olculur; alan sabit oldugu
        # icin h ~ 1/sqrt(N). GCI/LSR bunu ister.
        "h": None if not hucre else (1.0 / hucre) ** 0.5,
        "hucre_boyu_govde_m": bilgi.get("hucre_boyu_govde_m"),
        "surukleme_N_m": kuvvet.get("surukleme_N"),
        "tasima_N_m": kuvvet.get("tasima_N"),
        "surukleme_band_N_m": kuvvet.get("surukleme_band_N"),
        "tasima_band_N_m": kuvvet.get("tasima_band_N"),
        "yakinsadi": rez.get("yakinsadi"),
        "iterasyon": rez.get("iterasyon"),
    }


def _hucre_say(vaka: Path) -> int | None:
    o = vaka / "constant" / "polyMesh" / "owner"
    if not o.exists():
        return None
    m = re.search(r"nCells:(\d+)", o.read_text(errors="replace")[:2000])
    return int(m.group(1)) if m else None


def _bant(sev: list, alan: str) -> dict:
    """Bir nicelik için GCI (3 seviye) ve LSR (>=4 seviye)."""
    iyi = [s for s in sev if s.get("kosdu") and s.get(alan) is not None
           and s.get("h")]
    iyi.sort(key=lambda s: s["h"])          # ince -> kaba
    d: dict = {"n_seviye": len(iyi),
               "degerler": [{"h": round(s["h"], 8), "hucre": s["hucre"],
                             "deger": round(s[alan], 5)} for s in iyi]}
    if len(iyi) >= 3:
        f1, f2, f3 = (iyi[0][alan], iyi[1][alan], iyi[2][alan])
        d["gci"] = gci_richardson(f1, f2, f3, R)
    if len(iyi) >= 4:
        d["lsr"] = least_squares_gci([s["h"] for s in iyi],
                                     [s[alan] for s in iyi])
    # YAYILIM HER ZAMAN VERILIR: GCI mertebe tanimsiz kalirsa (salinimli ya
    # da gurultu mertebesinde fark) elde en azindan cıplak yayilim kalir ve
    # "band yok" ile "band sifir" karistirilmaz.
    if iyi:
        v = [s[alan] for s in iyi]
        d["yayilim_pct"] = round(100 * (max(v) - min(v)) / abs(v[0]), 3)
    return d


def olc() -> dict:
    IS.mkdir(parents=True, exist_ok=True)
    sev = [_seviye(o) for o in OLCEKLER]
    return _ozetle(sev)


def _ozetle(sev: list) -> dict:
    sur = _bant(sev, "surukleme_N_m")
    tas = _bant(sev, "tasima_N_m")
    return {
        "vaka": "Turek-Hron CFD1 — ağ-bağımsızlığı ailesi",
        "_neden": ("CFD1 kaydinda 'ag-bagimsizligi SINANMADI' notu bir "
                   "turdur duruyordu. Tasima bu geometride 5 mm'lik eksen "
                   "kacikligindan dogar ve ayriklastirmaya suruklemeden "
                   "cok daha duyarlidir; not bu yuzden bos degildi."),
        "olcekler": list(OLCEKLER), "inceltme_orani": R,
        "seviyeler": sev,
        "surukleme": sur, "tasima": tas,
        "referans": REF,
        "verdikt": _hukum(sev, sur, tas),
        "_kisit": (
            "CFD1 (RIJIT) calismasidir. FSI1'in kendi ag duyarliligi "
            "buradan TURETILMEZ --- deforme agda dagilim baska turlu "
            "davranabilir. Yapisal ag bu ailenin DISINDADIR. Aile hucre "
            "boyunu tekduze olcekler; yerel inceltme dagilimi sabit kalir, "
            "yani 'daha akilli bir ag' bu aileyle SINANMAZ. Kuyruk "
            "ortalamasi alinir; yakinsamayan bir seviye kayitta "
            "isaretlenir ama banttan DISLANMAZ."),
        "_uretim": "Üretim: python experiments/turek_hron_ag_bagimsizligi.py",
    }


def _hukum(sev, sur, tas) -> str:
    dusen = [s["olcek"] for s in sev if not s.get("kosdu")]
    if dusen:
        return (f"EKSİK AİLE: {dusen} ölçeklerinde koşu düştü; band "
                f"hesaplanamaz ya da eksik seviyeyle hesaplanmıştır.")
    yak = [s["olcek"] for s in sev if s.get("yakinsadi") is False]
    s = (f"{len(sev)} seviye koşuldu ({sev[-1]['hucre']}-{sev[0]['hucre']} "
         f"hücre). ")
    if yak:
        s += f"UYARI: {yak} ölçeklerinde rezidüel eşiği geçmedi. "
    s += (f"Sürükleme yayılımı %{sur.get('yayilim_pct')}, taşıma yayılımı "
          f"%{tas.get('yayilim_pct')}. ")
    g_s, g_t = sur.get("gci") or {}, tas.get("gci") or {}
    s += (f"GCI (en ince): sürükleme %{g_s.get('gci_fine_pct')} "
          f"(p={g_s.get('p_order')}, monoton={g_s.get('monotonic')}), "
          f"taşıma %{g_t.get('gci_fine_pct')} (p={g_t.get('p_order')}, "
          f"monoton={g_t.get('monotonic')}). ")
    if sur.get("lsr") or tas.get("lsr"):
        s += (f"LSR: sürükleme {(sur.get('lsr') or {}).get('u_pct')}, "
              f"taşıma {(tas.get('lsr') or {}).get('u_pct')}. ")
    yay_t = tas.get("yayilim_pct")
    if yay_t is None:
        return s + "Taşıma yayılımı hesaplanamadı."
    if yay_t > 20.0:
        return s + (
            "TAŞIMA AĞA GÜÇLÜ BAĞLI: bu ailedeki yayılım tek başına "
            "iki-yönlü FSI1'in referansa uzaklığıyla aynı mertebede, yani "
            "o sonucun bandı ağ tarafından belirleniyor demektir.")
    return s + (
        f"TAŞIMA AĞA GÜÇLÜ BAĞLI DEĞİL (%{yay_t}) ve bu bir ELEMEDİR: "
        "iki-yönlü FSI1'de görülen sapma bu aileyle açıklanamaz. Nitekim "
        "açıklanmadı --- kusur ağda değil, o döngünün kendi bayat-veri "
        "yolundaydı. Bu ailenin kalıcı değeri, CFD1 kaydında bir turdur "
        "duran 'ağ-bağımsızlığı SINANMADI' notunu kapatmasıdır.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
