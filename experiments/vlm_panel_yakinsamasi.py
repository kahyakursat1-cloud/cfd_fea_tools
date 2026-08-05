"""GERÇEK araç geometrisinde VLM panel yakınsaması — çapa TEMİZ kanatta geçmişti.

NEDEN AYRI BİR ÖLÇÜM: `vlm_capa.py` sade dikdörtgen kanatta VLM'i doğruladı
(lifting-line kesişimi %1.22, panel ile e monoton 1'in altına indi). Ama o çapa
TEMİZ bir geometriydi. Gerçek araçta gövde + ana kanat + yatay/dikey kuyruk
birlikte çözülüyor ve yakınsama davranışı AYNI OLMAK ZORUNDA DEĞİL.

ÖLÇÜLDÜ (MiniHawk, AR=5.00, α=0/4/8):
    panel   Cl(4)     Cl(8)     CDi(8)     e(8)      ΔCl(8)
      20   0.08095   0.14173   0.017322   0.0738      —
      40   0.19272   0.38661   0.011472   0.8294   +172.8%
      60   0.19412   0.38149   0.010531   0.8798     -1.3%
      80   0.21254   0.43241   0.014411   0.8260    +13.4%

40→60 neredeyse oturuyor (%1.3) ama 60→80 yeniden %13.4 sıçrıyor: dizi MONOTON
DEĞİL, yani bu geometride VLM'in YAKINSAMIŞ bir Cl'i YOK. Çapadaki %1.22'lik
doğrulama bandı buraya TAŞINAMAZ; taşınırsa olduğundan kesin bir sayı yayınlanır.

Dürüst kullanım: Cl bir SINIRLAMA olarak alınır, bandı da panel saçılmasıdır.

    conda run -n openvsp python experiments/vlm_panel_yakinsamasi.py [--sablon mini_hawk]
Çıktı: vlm_panel_yakinsamasi.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

PANELLER = (20, 40, 60, 80)
ALFALAR = (0.0, 4.0, 8.0)


def calistir(sablon: str = "mini_hawk") -> dict:
    import openvsp_bridge as ob
    from aircraft_geometry import AircraftLibrary
    ac = AircraftLibrary().get_template(sablon)()
    ar = ac.wing.span ** 2 / ac.wing.area

    kayit = []
    for panel in PANELLER:
        ob.VLM_SPAN_PANEL = panel
        p = ob.run_vspaero_polar(ac, alphas=ALFALAR)
        d = {round(x["alpha"], 1): x for x in p}
        satir = {"panel": panel, "uygulanan": (p[0].get("panel_uygulanan_kanat")
                                               if p else None)}
        for a in ALFALAR:
            x = d.get(round(a, 1), {})
            satir[f"Cl_{a:g}"] = x.get("Cl")
            satir[f"CDi_{a:g}"] = x.get("Cd_i")
            if x.get("Cl") and x.get("Cd_i"):
                satir[f"e_{a:g}"] = round(
                    x["Cl"] ** 2 / (math.pi * ar * x["Cd_i"]), 4)
        kayit.append(satir)

    # YAKINSAMA HÜKMÜ: son iki kademe arasındaki değişim küçük OLSA BİLE dizi
    # monoton değilse yakınsama YOKTUR — tek bir çift, salınan bir diziyi
    # "oturmuş" gösterebilir (bu depoda GCI tarafında da aynı ders alındı).
    ref = f"Cl_{max(ALFALAR):g}"
    seri = [k[ref] for k in kayit if k.get(ref)]
    monoton = degisim = sacilma = None
    if len(seri) >= 3:
        d1 = [b - a for a, b in zip(seri, seri[1:])]
        monoton = all(x > 0 for x in d1) or all(x < 0 for x in d1)
        degisim = round(abs(seri[-1] - seri[-2]) / abs(seri[-2]) * 100, 2)
        # Band = en ince ÜÇ kademenin saçılması (en kaba kademe genelde
        # temsil-dışıdır; MiniHawk'ta 20 panel e=0.07 veriyor).
        son3 = seri[-3:]
        sacilma = round((max(son3) - min(son3)) / abs(son3[-1]) * 100, 2)

    rec = {
        "vaka": f"VLM panel yakınsaması — {sablon} (GERÇEK araç, AR={ar:.2f})",
        "_neden": ("vlm_capa TEMIZ dikdortgen kanatta VLM'i dogruladi (%1.22). "
                   "Gercek aracta govde + kanat + kuyruk birlikte cozuluyor ve "
                   "yakinsama davranisi ayni olmak ZORUNDA DEGIL. Capadaki bandi "
                   "buraya tasimak, olmayan bir kesinlik yayinlamak olurdu."),
        "sablon": sablon, "AR": round(ar, 3),
        "paneller": list(PANELLER), "alfalar": list(ALFALAR),
        "kayitlar": kayit,
        "yakinsama": {"referans": ref, "seri": seri, "monoton": monoton,
                      "son_kademe_degisimi_pct": degisim,
                      "son3_sacilma_pct": sacilma},
        "_uretim": (f"Üretim: conda run -n openvsp python "
                    f"experiments/vlm_panel_yakinsamasi.py --sablon {sablon}"),
    }
    if monoton is None:
        rec["verdikt"] = "Yetersiz kademe — hüküm verilemez."
        rec["vlm_band_pct"] = None
    elif monoton and degisim is not None and degisim < 2.0:
        rec["verdikt"] = (f"✅ Panel yakinsamis: dizi monoton, son kademe degisimi "
                          f"%{degisim}. VLM Cl'i bu geometride kullanilabilir.")
        rec["vlm_band_pct"] = degisim
    else:
        rec["verdikt"] = (
            f"⚠️ Panel YAKINSAMAMIS: dizi {'monoton DEGIL' if not monoton else 'monoton'}"
            + (f", son kademe degisimi %{degisim}" if degisim is not None else "")
            + f". En ince uc kademenin sacilmasi %{sacilma}. VLM Cl'i bu geometride "
              "YAKINSAMIS bir deger DEGILDIR; band olarak bu sacilma tasinmalidir.")
        rec["vlm_band_pct"] = sacilma
    return rec


def main() -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--sablon", default="mini_hawk")
    a = ap.parse_args()
    rec = calistir(a.sablon)
    (KOK / "vlm_panel_yakinsamasi.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{rec['vaka']}")
    ref = rec["yakinsama"]["referans"]
    print(f"{'panel':>7} {'Cl(4)':>9} {'Cl(8)':>9} {'e(8)':>8}")
    for k in rec["kayitlar"]:
        print(f"{k['panel']:7d} {k.get('Cl_4') or float('nan'):9.5f} "
              f"{k.get('Cl_8') or float('nan'):9.5f} "
              f"{k.get('e_8') or float('nan'):8.4f}")
    print(f"\n{ref} serisi: {rec['yakinsama']['seri']}  "
          f"monoton={rec['yakinsama']['monoton']}")
    print(rec["verdikt"])
    print(f"-> vlm_panel_yakinsamasi.json  (band %{rec['vlm_band_pct']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
