"""Başarım matrisinin geometri kısıtı — ölçüldü, açıklanmadı.

NEDEN: rapor çekirdek ölçeklenmesini TEK geometriyle (küp) ölçüp bunu sınır
olarak yazıyordu: "Bu bir kıyaslama değildir (tek geometri, tek makine)".
Sınırı yazmak onu ölçmek değildir. Küp, snappyHexMesh'e yüzey işi neredeyse
hiç vermez (12 üçgen, keskin kenar, kavis yok); gerçek bir gövdede yüzey
yakalama ve katman ekleme payı çok daha büyüktür. Ölçeklenme eğrisinin
geometriyle değişip değişmediği BİLİNMİYORDU.

ÖNCEDEN SABİTLENEN İDDİA (rapor §Çekirdek ölçeklenmesi'nden aynen):
    İ1  Hızlanma her satırda idealin ALTINDADIR.
    İ2  Hızlanma hücre sayısıyla ARTAR.
    İ3  En küçük ağda 8 çekirdek 4 çekirdekten YAVAŞTIR.
İddialar ölçümden önce yazıldı; sonuç onları doğrulasa da yalanlasa da olduğu
gibi kaydedilir.

ÖLÇÜT DÜZELTMESİ (aynı gün, ikinci geometri koşulurken bulundu): raporun
yayımladığı hızlanmalar AŞAMA DUVAR SÜRESİNDEN hesaplanmıştı. O süre WSL süreç
başlatma, ortam kurulumu ve `mpirun` açılışını içerir; bu yük hücre sayısından
BAĞIMSIZDIR (~8-10 s). MiniHawk'ın en küçük ağında üç çekirdek sayısı da
12,1 s vermişti --- 10 ms içinde aynı, ki bu hesaplama değil sabit yük demektir.
`foamRun`'un kendi `ExecutionTime`'ı 4,32 / 2,03 / 2,01 s. Yani İ1--İ3 artık
ÇÖZÜCÜ süresinden sınanır; duvar süresinden gelen sayı da tutulur, çünkü
kullanıcının beklediği süre odur ve ikisinin farkı bulgunun kendisidir.

TEK MAKİNE KISITI DEVAM EDER: ikinci donanım yok. Kapatılan sınır GEOMETRİ
sınırıdır, makine sınırı değil.

ÖNKOŞUL: iki matris de koşulmuş olmalı
    python experiments/basarim_matrisi.py
    python experiments/basarim_matrisi.py --geometri minihawk

    python experiments/basarim_geometri_bagimliligi.py
Çıktı: basarim_geometri_bagimliligi.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

KAYNAKLAR = {
    "kup": KOK / "basarim_matrisi.json",
    "minihawk": KOK / "basarim_matrisi_minihawk.json",
}


def _egri(rec: dict) -> dict:
    """Bütçe -> {çekirdek: ...}. Hızlanma ExecutionTime'DAN hesaplanır.

    Aşama duvar süresi WSL/mpirun açılışını içerir ve bu yük hücre sayısından
    bağımsızdır; ondan hesaplanan hızlanma paralelliği değil sabit yükün
    seyrelmesini ölçer. `hizlanma_duvar` yine de tutulur --- kullanıcının
    gördüğü süre odur ve iki sayının FARKI raporlanacak bulgudur.
    """
    out: dict = {}
    for s in rec.get("satirlar", []):
        if s.get("durum") != "ok" or not s.get("cells"):
            continue
        if not s.get("cozucu_exec_s") or not s.get("cozucu_s"):
            continue
        out.setdefault(s["butce"], {})[s["cekirdek"]] = s
    egri = {}
    for b, grup in sorted(out.items()):
        taban = grup.get(1)
        if not taban:
            continue
        egri[b] = {}
        for c, s in sorted(grup.items()):
            toplam = (s.get("cozucu_s") or 0) + (s.get("mesh_s") or 0)
            egri[b][c] = {
                "hucre": s["cells"],
                "cozucu_exec_s": s["cozucu_exec_s"],
                "asama_s": s["cozucu_s"],
                "sabit_yuk_s": round(s["cozucu_s"] - s["cozucu_exec_s"], 1),
                "mesh_s": s.get("mesh_s"),
                "hizlanma": round(taban["cozucu_exec_s"] / s["cozucu_exec_s"], 2),
                "hizlanma_duvar": round(taban["cozucu_s"] / s["cozucu_s"], 2),
                "mesh_payi_pct": (round(100 * (s.get("mesh_s") or 0) / toplam, 1)
                                  if toplam else None),
            }
    return egri


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    eksik = [a for a, p in KAYNAKLAR.items() if not p.exists()]
    if eksik:
        print(f"matris yok: {eksik} — önce basarim_matrisi.py koşulmalı")
        return 1

    egriler = {a: _egri(json.loads(p.read_text(encoding="utf-8")))
               for a, p in KAYNAKLAR.items()}

    hukumler, ihlal = [], []
    for ad, e in egriler.items():
        if not e:
            hukumler.append({"geometri": ad, "durum": "kullanılabilir satır YOK"})
            continue
        tum_h = [v["hizlanma"] for g in e.values() for c, v in g.items() if c > 1]
        cekirdek = sorted({c for g in e.values() for c in g})
        # I1: ideal ustu var mi?
        ideal_asan = [(b, c, g[c]["hizlanma"]) for b, g in e.items()
                      for c in g if c > 1 and g[c]["hizlanma"] > c]
        # I2: hizlanma hucre sayisiyla artiyor mu (en buyuk cekirdekte)?
        enb = max(cekirdek)
        seri = [(g[enb]["hucre"], g[enb]["hizlanma"])
                for b, g in sorted(e.items()) if enb in g]
        artan = all(seri[i][1] <= seri[i + 1][1] + 1e-9
                    for i in range(len(seri) - 1)) if len(seri) > 1 else None
        # I3: en kucuk agda 8 cekirdek 4'ten yavas mi?
        enk = min(e)
        g0 = e[enk]
        i3 = (g0[8]["cozucu_exec_s"] > g0[4]["cozucu_exec_s"]
              if 4 in g0 and 8 in g0 else None)
        i3_duvar = (g0[8]["asama_s"] > g0[4]["asama_s"]
                    if 4 in g0 and 8 in g0 else None)
        h = {
            "geometri": ad,
            "butce_sayisi": len(e),
            "en_yuksek_hizlanma": max(tum_h) if tum_h else None,
            "I1_idealin_altinda": not ideal_asan,
            "I1_ihlal": [{"butce": b, "cekirdek": c, "hizlanma": s}
                         for b, c, s in ideal_asan],
            "I2_hucreyle_artan": artan,
            "I2_seri": [{"hucre": h_, "hizlanma": s} for h_, s in seri],
            "I3_8cekirdek_4ten_yavas": i3,
            "I3_duvar_suresinde": i3_duvar,
            "sabit_yuk_s": {str(b): g[min(g)]["sabit_yuk_s"]
                            for b, g in sorted(e.items())},
            "mesh_payi_pct": {
                str(b): g[min(g)]["mesh_payi_pct"] for b, g in sorted(e.items())},
        }
        hukumler.append(h)
        if not h["I1_idealin_altinda"]:
            ihlal.append(f"{ad}: İ1 (idealin altında) SAĞLANMADI")
        if h["I2_hucreyle_artan"] is False:
            ihlal.append(f"{ad}: İ2 (hücreyle artan) SAĞLANMADI")
        if i3 is False:
            ihlal.append(f"{ad}: İ3 (8 çekirdek 4'ten yavaş) SAĞLANMADI — "
                         f"duvar süresinde {i3_duvar}, çözücüde False")

    rec = {
        "vaka": "Başarım matrisi — geometri bağımlılığı",
        "_neden": ("Rapor cekirdek olceklenmesini TEK geometriyle olcup bunu "
                   "sinir diye yazmisti. Siniri YAZMAK onu OLCMEK degildir."),
        "_onceden_sabitlenen_iddia": {
            "I1": "Hizlanma her satirda idealin ALTINDADIR.",
            "I2": "Hizlanma hucre sayisiyla ARTAR.",
            "I3": "En kucuk agda 8 cekirdek 4'ten YAVASTIR.",
            "_not": "Iddialar olcumden ONCE yazildi (bkz. modul docstring).",
            "_olcut": ("Hizlanma foamRun ExecutionTime'dan hesaplanir. Raporun "
                       "yayimladigi sayilar ASAMA DUVAR SURESINDEN geliyordu ve "
                       "icinde hucreden BAGIMSIZ ~8-10 s WSL/mpirun acilis yuku "
                       "vardi; o yuk kucuk aglarda hizlanmayi bastirir."),
        },
        "geometriler": hukumler,
        "egriler": {a: {str(b): {str(c): v for c, v in g.items()}
                        for b, g in e.items()} for a, e in egriler.items()},
        "_kisit": ("TEK MAKINE kisiti DEVAM EDER — ikinci donanim yok. Burada "
                   "kapatilan yalnizca GEOMETRI sinridir. Ayrica iki matris "
                   "farkli oturumlarda kosuldu; mutlak sureler oturumlar arasi "
                   "karsilastirilmaz, HIZLANMA orani karsilastirilir."),
        "_uretim": "Üretim: python experiments/basarim_geometri_bagimliligi.py",
    }
    kup = next((h for h in hukumler if h["geometri"] == "kup"), {})
    mh = next((h for h in hukumler if h["geometri"] == "minihawk"), {})
    if ihlal:
        rec["verdikt"] = ("Önceden sabitlenen iddia SAĞLANMADI: "
                          + "; ".join(ihlal) + ". Raporun ölçeklenme cümlesi "
                          "geometriye bağlıdır ve öyle yazılmalıdır.")
    else:
        rec["verdikt"] = (
            f"İki geometride de İ1–İ3 sağlandı. En yüksek hızlanma küp "
            f"{kup.get('en_yuksek_hizlanma')}×, MiniHawk "
            f"{mh.get('en_yuksek_hizlanma')}× — ölçeklenme eğiliminin "
            f"geometriyle değişmediği ÖLÇÜLDÜ (iki gövde, tek makine).")

    import ortam
    ortam.damgala(rec)
    (KOK / "basarim_geometri_bagimliligi.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(rec["vaka"] + "\n" + "=" * 74)
    for h in hukumler:
        if "durum" in h:
            print(f"{h['geometri']:<12} {h['durum']}")
            continue
        print(f"{h['geometri']:<12} en yüksek hızlanma "
              f"{h['en_yuksek_hizlanma']}×  İ1={h['I1_idealin_altinda']}  "
              f"İ2={h['I2_hucreyle_artan']}  "
              f"İ3={h['I3_8cekirdek_4ten_yavas']} "
              f"(duvar: {h['I3_duvar_suresinde']})")
        for s in h["I2_seri"]:
            print(f"    {s['hucre']:>9,} hücre -> {s['hizlanma']}×")
        print(f"    sabit yük (1 çekirdek): {h['sabit_yuk_s']}")
    print("=" * 74)
    print(rec["verdikt"])
    print("-> basarim_geometri_bagimliligi.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
