"""Yüzey ağı en küçük geometrik özelliği çözüyor mu — TÜM koşu arşivinde ölçüm.

NEDEN: yüzey çözünürlük kapısı sabit bir sayıydı (≥500 yüz). O sayı aynı ölçütü
4 m'lik kanada da 4 cm'lik fine de uygular; geometriyle hiçbir ilişkisi yoktur.
`en_kucuk_boyut_m` parametresi imzada ZATEN VARDI ve gövdede hiç kullanılmıyordu
— ölçülen bir büyüklüğün tüketicisine hiç ulaşmaması, bu depoda tekrar eden
kusur sınıfı.

NE ÖLÇÜLÜR: tipik yüzey hücresi h=√(A/N) ile en küçük özellik arasındaki oran,
yani "özellik boyunca kaç hücre var". <4 ise o özellik geometrik olarak yoktur.

ÖLÇÜT ENGELLEYİCİ DEĞİL: 1 mm'lik firar kenarına 4 hücre istemek 0.7 m'lik bir
kanatta ~13 milyon yüzey yüzü demektir; bu hex-mesh'in bilinen sınırıdır, tek
tek koşuların kusuru değil. Ama sessiz de kalamaz — hangi koşuda hangi özelliğin
temsil edilmediği burada sayıyla durur.

    python experiments/yuzey_ozellik_cozunurlugu.py
Çıktı: yuzey_ozellik_cozunurlugu.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

from analysis.openfoam_runner import (  # noqa: E402
    OZELLIK_BASINA_HUCRE,
    YUZEY_YUZ_ESIGI,
    yuzey_cozunurluk_hukmu,
)


def topla() -> list[dict]:
    kayit = []
    for p in sorted((KOK / "vehicle_runs").glob("*/sonuc.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        g = d.get("geometry") or {}
        yc = (d.get("sinir_tabaka") or {}).get("yuzey_cozunurlugu") or {}
        n = yc.get("yuzey_yuz")
        if not n:
            continue
        h = yuzey_cozunurluk_hukmu(
            "", n, en_kucuk_boyut_m=(g.get("min_ozellik_m") or g.get("ince_kalinlik_m")),
            yuzey_alani_m2=g.get("yuzey_alani_m2"))
        gr = h["geometri_goreli"]
        kayit.append({
            "kosu": p.parent.name, "arac_tipi": d.get("vehicle_type"),
            "yuzey_yuz": n, "yuzey_alani_m2": g.get("yuzey_alani_m2"),
            "lmax_m": g.get("lmax_m"),
            "en_kucuk_ozellik_m": gr.get("en_kucuk_ozellik_m"),
            "h_yuzey_m": gr.get("h_yuzey_m"),
            "ozellik_basina_hucre": gr.get("ozellik_basina_hucre"),
            "ozellik_cozuldu": gr.get("ozellik_cozuldu"),
            "gereken_yuz": gr.get("gereken_yuz"),
            "olculebildi": gr.get("uygulandi", False),
        })
    return kayit


def calistir() -> dict:
    kayit = topla()
    olculen = [k for k in kayit if k["olculebildi"]]
    cozulmeyen = [k for k in olculen if k["ozellik_cozuldu"] is False]
    return {
        "vaka": "Yüzey ağının en küçük geometrik özelliği çözüp çözmediği — koşu arşivi",
        "_neden": ("Kapi sabit >=500 yuzdu ve geometriyle iliskisi yoktu; "
                   "`en_kucuk_boyut_m` imzada VARDI ama govdede hic kullanilmiyordu."),
        "olcut": {"ozellik_basina_hucre_gereken": OZELLIK_BASINA_HUCRE,
                  "mutlak_taban_yuz": YUZEY_YUZ_ESIGI,
                  "h_yuzey": "sqrt(yuzey_alani / yuzey_yuz)"},
        "kosular": kayit,
        "_engelleyici_degil": (
            "1 mm'lik firar kenarina 4 hucre istemek 0.7 m'lik kanatta ~13 milyon "
            "yuzey yuzu demektir; bu hex-mesh'in bilinen siniridir, tek tek "
            "kosularin kusuru degil. Olcum raporlanir, kosu REDDEDILMEZ."),
        "_kisit": ("`min_ozellik_m` STL'den kestirilir ve bazi modellerde gercek "
                   "bir tasarim ozelligi degil, uc nokta ucgeninin artigi olabilir. "
                   "O durumda oran gercekte oldugundan kotu gorunur."),
        "_uretim": "Üretim: python experiments/yuzey_ozellik_cozunurlugu.py",
        "verdikt": (
            f"{len(kayit)} kosu tarandi, {len(olculen)} tanesinde olcum yapilabildi; "
            f"{len(cozulmeyen)} kosuda en kucuk ozellik COZULMEDI ("
            + ", ".join(f"{k['kosu']} {k['ozellik_basina_hucre']} hucre/ozellik"
                        for k in cozulmeyen) + "). "
            "Bu kosularin Cd'si ince ozelligi ICERMEZ ve band bunu kapsamaz."),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rec = calistir()
    (KOK / "yuzey_ozellik_cozunurlugu.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["vaka"] + "\n")
    print(f"{'koşu':<26}{'yüz':>9}{'özellik mm':>12}{'h mm':>9}{'hücre/özellik':>15}")
    for k in rec["kosular"]:
        if not k["olculebildi"]:
            continue
        print(f"{k['kosu']:<26}{k['yuzey_yuz']:>9,}"
              f"{k['en_kucuk_ozellik_m'] * 1000:>12.2f}{k['h_yuzey_m'] * 1000:>9.2f}"
              f"{k['ozellik_basina_hucre']:>13.2f} "
              f"{'✓' if k['ozellik_cozuldu'] else '✗'}")
    print("\n" + rec["verdikt"])
    print("-> yuzey_ozellik_cozunurlugu.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
