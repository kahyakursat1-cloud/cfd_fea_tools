"""GERÇEK araç geometrisinde VLM panel yakınsaması — çapa TEMİZ kanatta geçmişti.

NEDEN AYRI BİR ÖLÇÜM: `vlm_capa.py` sade dikdörtgen kanatta VLM'i doğruladı
(lifting-line kesişimi %1.22, panel ile e monoton 1'in altına indi). Ama o çapa
TEMİZ bir geometriydi. Gerçek araçta gövde + ana kanat + yatay/dikey kuyruk
birlikte çözülüyor ve yakınsama davranışı AYNI OLMAK ZORUNDA DEĞİL.

ÖLÇÜM 1 — DÜZGÜN ARALIKLI PANEL (OutCluster=1.0), MiniHawk AR=5.00:
    panel   Cl(8)     e(8)      ΔCl(8)
      20   0.14173   0.0738      —
      40   0.38661   0.8294   +172.8%
      60   0.38149   0.8798     -1.3%
      80   0.43241   0.8260    +13.4%
40→60 neredeyse oturuyor ama 60→80 yeniden sıçrıyor: dizi MONOTON DEĞİL, yani
YAKINSAMIŞ bir Cl YOK. Yalnız son iki kademeye bakmak "oturmuş" derdi.

ÖLÇÜM 2 — UÇ KÜMELEMESİ eklendi (OutCluster taraması, 40/60/80 panel):
    1.00 → monoton DEĞİL, saçılma %11.78
    0.50 → monoton, saçılma %4.65   (ama e salınıyor: 0.91/0.92/0.62)
    0.25 → monoton, saçılma %2.07   (e 1.04/0.94/0.93, düzenli)
Düzgün dağılım uç girdabının gradyanını yakalayamıyordu. 0.25 ile:
    panel   Cl(8)     e(8)
      20   0.45664   0.6407
      40   0.41122   1.0369
      60   0.40295   0.9405
      80   0.40288   0.9311
Dizi monoton, son adım %0.02.

BAND KANONİK KURALDAN: son-adım farkı (%0.02) bir band DEĞİLDİR — iki kademenin
yakın olması ayrıklaştırma hatasının sıfıra yakın olduğunu kanıtlamaz. Panel 1B
bir ayrıklaştırma parametresidir (h~1/N), `band_from_levels(boyut=1)` uygulanır:
LSR 4-seviye → U = %2.18.

ÖLÇÜM 3 — KAMBURLUK AÇILDIKTAN SONRA (VLM_KAMBUR=True): yukarıdaki %2.18
KAMBURLUKSUZ koşuya aitti, yani SİMETRİK kesitli bir kanadın bandıydı. Aracın
kanadı NACA2412; kamburluk açılınca dizi SALINIYOR ve inceltmek düzeltmiyor:
    20/40/60/80    → 0.68135 / 0.65259 / 0.64935 / 0.65501,  U=%14.66
    60/80/100/120  → 0.64935 / 0.65501 / 0.64596 / 0.63933,  U=%7.36
Küçük bandı yayınlamak aileyi sonuca göre seçmek olurdu; bütün kademeler tek
ailede toplanır. Doğru geometriyle bandın GENİŞ olması, yanlış geometriyle dar
olmasına yeğdir — ikincisi olmayan bir kesinliktir.

ÖLÇÜM 4 — GÖVDE ÇAPI DÜZELTİLDİKTEN SONRA: salınım GEOMETRİ ARTEFAKTIYMIŞ.
Gövde 2.5 m yerine beyan edilen 0.08 m olarak kurulunca dizi MONOTONLAŞTI:
    20..120 panel → 0.79144 / 0.76179 / 0.74191 / 0.73629 / 0.73287 / 0.72394
Ama hâlâ inişte (son kademe %1.22) ve gözlenen mertebe p<0.5, band %28.32.
NEDENİ ÖLÇÜLDÜ: KİRİŞ yönü (Tess_W 17/25/33/49) Cl(8)'i %1.9 oynatıyor ve
monoton değil. Açıklık serisinin ince kademelerindeki adımlar (%0.5–1.2) bu
gürültünün ALTINDA kalıyor — yani tek yönde inceltmek burada yakınsama
gösteremez; iki yön birlikte inceltilmedikçe band bu tabanın altına inmez.

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

# KADEME AİLESİ BAND'A GÖRE SEÇİLMEZ. Kamburluk açıldıktan sonra dizi salınımlı
# çıktı ve iki aile ölçüldü: 20/40/60/80 → U=%14.66, 60/80/100/120 → U=%7.36.
# Küçük olanı yayınlamak, aileyi sonuca göre seçmek olurdu. Bütün ölçülen
# kademeler TEK ailede toplanır; kanonik kural hepsine uygulanır.
PANELLER = (20, 40, 60, 80, 100, 120)
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
        satir = {"panel": panel,
                 "uc_kumeleme": (p[0].get("uc_kumeleme") if p else None),
                 "uygulanan": (p[0].get("panel_uygulanan_kanat")
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
    # BAND KANONIK KURALDAN, KENDI HEURISTIGIMDEN DEGIL. Ilk surum bandi "son
    # kademe degisimi" olarak veriyordu ve kumeleme duzeltmesinden sonra %0.02
    # cikti — FAZLA IYIMSER: iki kademenin birbirine yakin olmasi ayriklastirma
    # hatasinin sifira yakin oldugunu KANITLAMAZ (GCI'nin emniyet faktoru tam
    # bu yuzden var). `band_from_levels` depodaki TEK kural kaynagi; panel
    # sayisi 1B bir ayriklastirma parametresi oldugu icin boyut=1 (h ~ 1/N).
    # OLCULDU: ayni seride kanonik kural %2.18, heuristik %0.02 diyordu.
    from report_generator import band_from_levels
    kanonik = (band_from_levels(list(PANELLER)[:len(seri)], seri, boyut=1)
               if len(seri) >= 2 else None)
    rec["kanonik_band"] = kanonik

    if monoton is None:
        rec["verdikt"] = "Yetersiz kademe — hüküm verilemez."
        rec["vlm_band_pct"] = None
    elif monoton and kanonik and kanonik["u_pct"] < 5.0:
        rec["verdikt"] = (
            f"✅ Panel yakinsamis: dizi monoton, son kademe degisimi %{degisim}. "
            f"Band KANONIK kuraldan: {kanonik['kaynak']} -> U=%{kanonik['u_pct']} "
            f"(son-adim heuristigi %{degisim} derdi — fazla iyimser). "
            "VLM Cl'i bu geometride kullanilabilir.")
        rec["vlm_band_pct"] = kanonik["u_pct"]
    else:
        rec["verdikt"] = (
            f"⚠️ Panel YAKINSAMAMIS: dizi {'monoton DEGIL' if not monoton else 'monoton'}"
            + (f", son kademe degisimi %{degisim}" if degisim is not None else "")
            + f". En ince uc kademenin sacilmasi %{sacilma}"
            + (f", kanonik kural %{kanonik['u_pct']}" if kanonik else "")
            + ". VLM Cl'i bu geometride YAKINSAMIS bir deger DEGILDIR; band olarak "
              "bunlarin BUYUGU tasinmalidir.")
        rec["vlm_band_pct"] = max([x for x in (sacilma,
                                               kanonik["u_pct"] if kanonik else None)
                                   if x is not None], default=None)
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
