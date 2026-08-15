"""Aynı geometri, aynı ayar, iki ORTAM: host-WSL ve konteyner. Cd'ler örtüşüyor mu?

NEDEN GEREKLİ: `docker/Dockerfile.hizmet` ile masaüstü `Dockerfile` BİLEREK aynı
taban imaj digest'ini taşıyor; gerekçe "iki ortam aynı çözücüyü koşsun, üretilen
bantlar karşılaştırılabilir olsun" idi. Bu bir VARSAYIM ve şimdiye dek hiç
ölçülmedi. Ölçülmeden "okulda/bulutta koşan sonuç masaüstündekiyle aynıdır"
denemez — ki başsız dağıtımın tüm gerekçesi tam olarak bu cümledir.

Kıyas TEK GİRİŞ NOKTASINDAN yapılır (`cli.py`), böylece iki koşu arasında
DEĞİŞEN tek şey `CFD_BACKEND` olur: aynı kod, aynı ayar, aynı STL.

Sıralı koşar. Eşzamanlı koşmaz: makine 14,7 GB RAM taşıyor ve iki OpenFOAM
vakası aynı anda ayağa kalkarsa ölçüm bellek baskısına bulaşır.

    python experiments/ortam_capraz_olcumu.py --kalite standart

Çıktı: ortam_capraz_olcumu.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

# İki Cd arasında hangi fark "aynı ortam" sayılır. Bu bir ORTAM tutarlılığı
# eşiğidir, ağ-yakınsaması eşiği DEĞİL: aynı ağ + aynı çözücü + aynı iterasyon
# sayısı, kayan-nokta ve MPI-toplama sırası dışında farklı sonuç ÜRETMEMELİ.
# %1 üstü fark ortamların farklı çözücü/kütüphane taşıdığına işarettir.
ESIK_YUZDE = 1.0


def _damga() -> dict:
    """Ölçümün HANGİ imaj ve HANGİ kaynak üzerinde yapıldığı.

    Damgasız bir kıyas ölçümü, kapı için işe yaramaz: dosya diskte durur ve
    "iki ortam örtüşüyor" der, ama imaj yeniden inşa edildiğinde ya da kaynak
    değiştiğinde o cümle artık bugünün ikilisi hakkında bir şey söylemez. Bu
    deponun tekrar tekrar ölçtüğü kusur --- yeşil işaret yalnızca gerçekten
    kontrol ettiği şeyi kanıtlar --- burada da geçerli.
    """
    def _kabuk(argv: list[str]) -> str | None:
        try:
            r = subprocess.run(argv, cwd=KOK, capture_output=True, text=True, timeout=60)
            return r.stdout.strip() or None if r.returncode == 0 else None
        # sessiz-yutma: kabul — damga alanı `None` kalır ve bu GÖRÜNÜRDÜR:
        # ortam kapısı damgasız/eksik damgalı ölçümü REDDEDER. Yani burada
        # yutulan bilgi kaybolmuyor, kapıya "belirlenemedi" olarak taşınıyor.
        except (OSError, subprocess.SubprocessError):
            return None

    kap = _kabuk(["docker", "compose", "-f", "docker/compose.yaml", "ps", "-q", "worker"])
    imaj = _kabuk(["docker", "inspect", "--format", "{{.Image}}", kap]) if kap else None
    return {
        "olcum_zamani": time.strftime("%Y-%m-%d %H:%M"),
        "kaynak_islemesi": _kabuk(["git", "rev-parse", "--short=7", "HEAD"]),
        "kaynak_kirli": bool(_kabuk(["git", "status", "--porcelain"])),
        "konteyner_imaji": imaj,
    }


def _cd_al(cikti: str) -> tuple[float | None, str | None, dict]:
    """cli.py stdout'undaki JSON'dan (cd, sınıf, ham) çek."""
    try:
        d = json.loads(cikti)
    except json.JSONDecodeError:
        return None, None, {"ayrıştırılamadı": cikti[-400:]}
    if d.get("durum") != "ok":
        return None, None, d
    return (d.get("sonuc", {}).get("cd"),
            d.get("gecerlilik", {}).get("genel"), d)


def host_kosusu(stl: Path, ayar: dict) -> dict:
    komut = [sys.executable, "cli.py", "--stl", str(stl),
             "--tip", ayar["tip"], "--hiz", str(ayar["hiz"]),
             "--kalite", ayar["kalite"]]
    t0 = time.time()
    r = subprocess.run(komut, cwd=KOK, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=ayar["tmo"])
    cd, sinif, ham = _cd_al(r.stdout)
    return {"ortam": "host-wsl", "cd": cd, "sinif": sinif,
            "sure_s": round(time.time() - t0), "donus_kodu": r.returncode,
            "stderr_kuyruk": (r.stderr or "")[-500:], "ham": ham}


def konteyner_kosusu(stl: Path, ayar: dict, servis: str = "worker") -> dict:
    kap = subprocess.run(["docker", "compose", "-f", "docker/compose.yaml",
                          "ps", "-q", servis], cwd=KOK,
                         capture_output=True, text=True).stdout.strip()
    if not kap:
        return {"ortam": "konteyner", "cd": None, "hata": f"{servis} ayakta değil"}
    ic_yol = "/veri/capraz_olcum.stl"
    subprocess.run(["docker", "cp", str(stl), f"{kap}:{ic_yol}"], check=True)
    komut = ["docker", "exec", "-w", "/uygulama", kap, "python", "cli.py",
             "--stl", ic_yol, "--tip", ayar["tip"], "--hiz", str(ayar["hiz"]),
             "--kalite", ayar["kalite"]]
    t0 = time.time()
    r = subprocess.run(komut, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=ayar["tmo"])
    cd, sinif, ham = _cd_al(r.stdout)
    return {"ortam": "konteyner", "cd": cd, "sinif": sinif,
            "sure_s": round(time.time() - t0), "donus_kodu": r.returncode,
            "stderr_kuyruk": (r.stderr or "")[-500:], "ham": ham}


def _yuz_sayisi(kosu: dict) -> int | None:
    """Gövde yaması kaç yüz — sayının geometriyi temsil edip etmediğinin ön koşulu."""
    m = (kosu.get("ham") or {}).get("mesh") or {}
    return m.get("cells")


def main() -> int:
    # Windows konsolu cp1254; ölçüm bittikten SONRA özet satırı UnicodeEncodeError
    # ile patlıyordu (ölçüldü 2026-08-15). Sonuç JSON'a yazılmış olduğu için veri
    # kaybı yoktu ama başarılı bir koşu çöküyor gibi göründü — teşhis maliyeti
    # gerçek. Boru hattına yazarken sorun çıkmıyordu, o yüzden ancak doğrudan
    # konsolda görüldü.
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stl", default="test_sphere.stl")
    ap.add_argument("--tip", default="roket")
    ap.add_argument("--hiz", type=float, default=20.0)
    ap.add_argument("--kalite", default="standart")
    ap.add_argument("--tmo", type=int, default=5400)
    a = ap.parse_args()

    stl = (KOK / a.stl) if not Path(a.stl).is_absolute() else Path(a.stl)
    if not stl.exists():
        print(f"STL yok: {stl}", file=sys.stderr)
        return 2
    ayar = {"tip": a.tip, "hiz": a.hiz, "kalite": a.kalite, "tmo": a.tmo}

    print(f"[1/2] host-WSL koşusu ({a.kalite})…", file=sys.stderr, flush=True)
    h = host_kosusu(stl, ayar)
    print(f"      cd={h['cd']} sinif={h.get('sinif')} {h['sure_s']} s",
          file=sys.stderr, flush=True)

    print("[2/2] konteyner koşusu…", file=sys.stderr, flush=True)
    k = konteyner_kosusu(stl, ayar)
    print(f"      cd={k['cd']} sinif={k.get('sinif')} {k.get('sure_s')} s",
          file=sys.stderr, flush=True)

    ozet: dict = {"damga": _damga(),
                  "ayar": {k2: v for k2, v in ayar.items() if k2 != "tmo"},
                  "stl": stl.name, "kosular": [h, k], "esik_yuzde": ESIK_YUZDE}
    if h["cd"] and k["cd"]:
        fark = abs(h["cd"] - k["cd"]) / abs(h["cd"]) * 100.0
        ozet["fark_yuzde"] = round(fark, 3)
        ozet["ortamlar_ortusuyor"] = fark <= ESIK_YUZDE
        ozet["hucre_sayilari"] = {"host": _yuz_sayisi(h), "konteyner": _yuz_sayisi(k)}
        # Aynı sınıf dönmesi de şart: sayı örtüşüp GÜVENİLİRLİK SINIFI ayrışırsa
        # iki ortam aynı sonucu vermiyor demektir — sınıf sonucun parçasıdır.
        ozet["sinif_ayni"] = h.get("sinif") == k.get("sinif")
    else:
        ozet["ortamlar_ortusuyor"] = False
        ozet["neden"] = "en az bir koşu Cd üretmedi"

    (KOK / "ortam_capraz_olcumu.json").write_text(
        json.dumps(ozet, indent=2, ensure_ascii=False), encoding="utf-8")

    if ozet.get("ortamlar_ortusuyor") and ozet.get("sinif_ayni"):
        print(f"\n✅ ORTAMLAR ÖRTÜŞÜYOR — fark %{ozet['fark_yuzde']} "
              f"(eşik %{ESIK_YUZDE}), sınıf ikisinde de {h['sinif']}")
        return 0
    print(f"\n❌ ÖRTÜŞMÜYOR — {json.dumps(ozet, ensure_ascii=False)[:400]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
