"""Güvenilirlik taraması — "N geometriden kaçı savunulabilir Cd üretiyor?"

NEDEN: bugüne kadar uygulamanın başarı oranı BİLİNMİYORDU. Tek tek vakalar
biliniyordu (küp ✅, MiniHawk ⚠️ GCI %379) ama "rastgele bir geometri verirsem ne
olur" sorusunun ölçülmüş cevabı yoktu. Bir analiz mühendisinin "bu aracı
kullanabilir miyim" sorusu tam olarak bu orana dayanır.

KRİTİK: bu tarama güvenilirliği İYİLEŞTİRMEZ, ÖLÇER. Ve ölçüm ancak KAPILAR
varsa anlamlıdır — kapısız bir boru hattı her koşuda bir sayı üretir ve tarama
"%100 başarı" derdi. Bu yüzden tarama şu kapılardan SONRA yazıldı:
  * seviye yakınsama kapısı (GCI'ya yakınsamamış seviye girmez)
  * katman ölçümü (istenen vs snappy'nin ördüğü)
  * fizik kapısı + sonuç kapısı (validity_envelope)

"Savunulabilir" TANIMI BENİM YARGIM DEĞİL, mevcut kapıların birleşimidir:
  1. koşu tamamlandı ve Cd üretti
  2. sonuc_kapisi seviyesi "ok" (fizik + yakınsama + salınım yok)
  3. duvar çözünürlüğü savunulabilir: y⁺ duvar-fonksiyonu bandında (30-300)
     VEYA katman ÖLÇÜLEREK örülmüş ve y⁺ ≲ 5
Üçü de sağlanmazsa sonuç RAPORLANIR ama "savunulabilir" sayılmaz.

    python experiments/guvenilirlik_taramasi.py --n 12 --kalite hizli
    python experiments/guvenilirlik_taramasi.py --stl a.stl b.stl

Çıktı: guvenilirlik_taramasi.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")

from validity_envelope import sonuc_kapisi  # noqa: E402
from vehicle_pipeline import run_vehicle_analysis  # noqa: E402

# Duvar-fonksiyonu log-bölgesi. Dışındaysa sürtünme bileşeni çözülmüyor demektir.
YPLUS_BANDI = (30.0, 300.0)
YPLUS_DUVAR_COZUNUR = 5.0

AILELER = ("experiments/nx_geo", "experiments/nx_geo_egitim",
           "experiments/nx_geo_kor", "experiments/real_geo")


def geometri_havuzu(kok: Path) -> list[Path]:
    out = []
    for a in AILELER:
        out += sorted((kok / a).glob("*.stl"))
    return out


def duvar_hukmu(sinir: dict | None) -> tuple[bool, str]:
    """Duvar çözünürlüğü savunulabilir mi? İki MEŞRU yol var, ikisi de kabul."""
    s = sinir or {}
    yp = (s.get("yplus") or {})
    ort = yp.get("ort") if isinstance(yp, dict) else None
    kat = s.get("katman_olcumu") or {}
    if ort is None:
        return False, f"y+ ölçülemedi ({yp.get('neden') if isinstance(yp, dict) else 'yok'})"
    if kat.get("durum") == "COKTU":
        return False, (f"katman ÇÖKTÜ ({kat.get('istenen')} istendi, 0 örüldü) — "
                       f"duvar-çözünür iddiası geçersiz, y+={ort:.0f}")
    if kat.get("durum") == "ok" and ort <= YPLUS_DUVAR_COZUNUR:
        return True, f"duvar-çözünür: {kat['eklenen']} katman, y+={ort:.1f}"
    if YPLUS_BANDI[0] <= ort <= YPLUS_BANDI[1]:
        return True, f"duvar fonksiyonu bandında: y+={ort:.0f}"
    return False, (f"y+={ort:.0f} duvar-fonksiyonu bandının ({YPLUS_BANDI[0]:.0f}-"
                   f"{YPLUS_BANDI[1]:.0f}) dışında — sürtünme çözülmüyor")


def savunulabilir_mi(r) -> dict:
    """Tek koşunun hükmü — TÜM gerekçeler toplanır, ilkinde durulmaz."""
    ret = {"savunulabilir": False, "gerekce": []}
    if getattr(r, "status", None) != "ok" or r.cd is None:
        ret["gerekce"].append(f"koşu tamamlanmadı (status={getattr(r, 'status', '?')})")
        return ret
    # NİTELİK ADI KRİTİK: `fizik` yazmak sessizce None döndürür ve sonuc_kapisi
    # eksik veriyi "ok" sayar — fizik kapısı fark edilmeden DEVRE DIŞI kalırdı.
    # (İlk sürümde tam bu hata yapıldı; test_fizik_kabul_NITELIK_ADI onu bağlar.)
    kapi = sonuc_kapisi(getattr(r, "fizik_kabul", None), r.convergence)
    ret["kapi"] = kapi["etiket"]
    if kapi["seviye"] != "ok":
        ret["gerekce"].append(f"{kapi['etiket']}: {'; '.join(kapi['gerekce'])[:160]}")
    duvar_ok, duvar_not = duvar_hukmu(getattr(r, "sinir_tabaka", None))
    ret["duvar"] = duvar_not
    if not duvar_ok:
        ret["gerekce"].append(duvar_not)
    ret["savunulabilir"] = not ret["gerekce"]
    return ret


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--kalite", default="hizli")
    # ref_bump: yuzey iyilestirme kademesi. MiniHawk'ta OLCULDU —
    #   +1 -> y+ 340 (band disi) | +2 -> y+ 112 | +3 -> y+ 61 (ikisi de BAND ICI)
    # y+ ilk hucre yuksekligiyle dogru orantili; tek gercek kaldirac budur.
    ap.add_argument("--ref-bump", type=int, default=0)
    ap.add_argument("--hiz", type=float, default=15.0)
    ap.add_argument("--tohum", type=int, default=20260728)
    ap.add_argument("--stl", nargs="*", default=None)
    ap.add_argument("--out", default="guvenilirlik_taramasi.json")
    a = ap.parse_args()

    kok = HERE.parent
    if a.stl:
        sec = [Path(s) for s in a.stl]
    else:
        havuz = geometri_havuzu(kok)
        if not havuz:
            print("HAVUZ BOŞ — STL ailesi bulunamadı", flush=True)
            return 1
        random.Random(a.tohum).shuffle(havuz)
        sec = havuz[:a.n]

    print(f"Tarama: {len(sec)} geometri, kalite={a.kalite}, V={a.hiz} m/s", flush=True)
    kayitlar, t0 = [], time.time()
    for i, stl in enumerate(sec, 1):
        print(f"[{i}/{len(sec)}] {stl.name} ...", flush=True)
        t1 = time.time()
        try:
            r = run_vehicle_analysis(str(stl), velocity=a.hiz, quality=a.kalite,
                                     ref_bump=a.ref_bump, out_root="vehicle_runs")
            h = savunulabilir_mi(r)
            k = {"stl": stl.name, "aile": stl.parent.name,
                 "Cd": r.cd, "hucre": (r.mesh or {}).get("cells"),
                 "sure_dk": round((time.time() - t1) / 60, 1), **h}
        # sessiz-yutma: kabul — ÇÖKEN koşu da bir SONUÇTUR ve orana girer; yutulursa
        # başarı oranı sistematik olarak şişer (yalnız koşabilenler sayılırdı).
        except Exception as e:
            k = {"stl": stl.name, "aile": stl.parent.name, "savunulabilir": False,
                 "gerekce": [f"ÇÖKTÜ: {type(e).__name__}: {str(e)[:160]}"],
                 "sure_dk": round((time.time() - t1) / 60, 1)}
        kayitlar.append(k)
        print(f"    -> {'SAVUNULABILIR' if k['savunulabilir'] else 'HAYIR'}"
              f"  Cd={k.get('Cd')}  ({k['sure_dk']} dk)"
              + ("" if k["savunulabilir"] else f"  [{'; '.join(k['gerekce'])[:110]}]"),
              flush=True)

    gecen = [k for k in kayitlar if k["savunulabilir"]]
    # Neden başarısız oldukları KATEGORİK olarak sayılır — tek bir oran "neyi
    # düzelteceğim" sorusuna cevap vermez.
    sebepler: dict[str, int] = {}
    for k in kayitlar:
        for g in k.get("gerekce", []):
            anahtar = ("duvar/y+" if "y+" in g or "katman" in g else
                       "fizik-dışı" if "fizik" in g else
                       "yakınsama/salınım" if ("yakınsa" in g or "salın" in g
                                               or "sınırda" in g) else
                       "çöktü" if "ÇÖKTÜ" in g else "koşu tamamlanmadı")
            sebepler[anahtar] = sebepler.get(anahtar, 0) + 1

    rec = {
        "vaka": (f"Güvenilirlik taraması — {len(kayitlar)} geometri, kalite={a.kalite}, "
                 f"V={a.hiz} m/s, ref_bump={a.ref_bump}"),
        "_neden": ("Uygulamanin BASARI ORANI olculmemisti. 'Savunulabilir' tanimi "
                   "mevcut kapilarin birlesimidir (sonuc_kapisi + duvar cozunurlugu), "
                   "yazarin yargisi degil."),
        "geometri_sayisi": len(kayitlar),
        "savunulabilir_sayisi": len(gecen),
        "oran_pct": round(100 * len(gecen) / max(len(kayitlar), 1), 1),
        "basarisizlik_sebepleri": dict(sorted(sebepler.items(),
                                              key=lambda x: -x[1])),
        "kosular": kayitlar,
        "sure_dk": round((time.time() - t0) / 60, 1),
        "olcut": {"yplus_bandi": list(YPLUS_BANDI),
                  "yplus_duvar_cozunur": YPLUS_DUVAR_COZUNUR,
                  "kapi": "validity_envelope.sonuc_kapisi seviyesi 'ok' olmali"},
        "verdikt": "",
        "_uretim": f"Üretim: python experiments/guvenilirlik_taramasi.py --n {a.n} "
                   f"--kalite {a.kalite} --ref-bump {a.ref_bump} --tohum {a.tohum}",
    }
    rec["verdikt"] = (
        f"{len(gecen)}/{len(kayitlar)} geometri savunulabilir Cd uretti (%{rec['oran_pct']}). "
        + (f"Baskin basarisizlik sebebi: {next(iter(rec['basarisizlik_sebepleri']))} "
           f"({next(iter(rec['basarisizlik_sebepleri'].values()))} vaka). "
           if sebepler else "")
        + "Bu oran uygulamanin OLCULMUS guvenilirligidir; kapilar olmadan olculemezdi.")
    (kok / a.out).write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print("\n" + rec["verdikt"])
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
