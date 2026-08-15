"""Başsız dağıtımın UÇTAN UCA kanıtı — konteyner gerçekten ayağa kalkıyor mu?

NEDEN AYRI BİR BETİK: `tests/test_hizmet.py` SÖZLEŞMEYİ sınar (imaj giriş
noktalarını kopyalıyor mu, iki servis aynı kuyruğu kullanıyor mu, başsız
modüller GUI ithal ediyor mu). Hiçbiri imajın AYAĞA KALKTIĞINI kanıtlamaz;
o kusur inşa zamanında görünmez, imaj kurulur ve ilk istekte patlar.

Bu betik zinciri gerçek konteynerde koşar:
    1. /saglik      — sunucu ayakta mı
    2. /yukle       — geometri gidiyor mu
    3. /analiz      — iş kuyruğa giriyor mu
    4. /is/{id}     — worker koşuyor ve sonuç dönüyor mu
    5. sözleşme     — sınıf sayıyla birlikte mi geldi

Üretim:
    docker compose -f docker/compose.yaml up -d --build
    python experiments/konteyner_duman_testi.py --stl test_sphere.stl
Çıktı: konteyner_duman_testi.json   ·   çıkış 0 = zincir tamam
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KANIT = KOK / "konteyner_duman_testi.json"


def _istek(url: str, veri: bytes | None = None, tip: str = "application/json",
           zaman: int = 30):
    r = urllib.request.Request(url, data=veri, method="POST" if veri else "GET")
    if veri:
        r.add_header("Content-Type", tip)
    with urllib.request.urlopen(r, timeout=zaman) as y:
        return json.loads(y.read().decode("utf-8"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = argparse.ArgumentParser()
    a.add_argument("--url", default="http://localhost:8080")
    a.add_argument("--stl", default="test_sphere.stl")
    a.add_argument("--bekle", type=int, default=1800, help="iş için azami saniye")
    p = a.parse_args()

    adim: list[dict] = []

    def kaydet(ad, ok, ayrinti=""):
        adim.append({"adim": ad, "ok": bool(ok), "ayrinti": str(ayrinti)[:300]})
        print(f"  {'✅' if ok else '❌'} {ad}: {str(ayrinti)[:110]}", flush=True)
        return ok

    # 1 ── sağlık
    try:
        s = _istek(f"{p.url}/saglik")
        kaydet("saglik", s.get("durum") == "ayakta", s)
    except Exception as e:                                        # noqa: BLE001
        kaydet("saglik", False, f"{type(e).__name__}: {e}")
        return _yaz(adim, "sunucuya ulaşılamadı — konteyner ayakta mı?")

    # 2 ── yükleme
    stl = (KOK / p.stl) if not Path(p.stl).is_absolute() else Path(p.stl)
    if not stl.exists():
        return _yaz(adim, f"geometri yok: {stl}")
    try:
        y = _istek(f"{p.url}/yukle?ad={stl.name}", stl.read_bytes(),
                   "application/octet-stream", zaman=120)
        kaydet("yukle", bool(y.get("stl")), f"{y.get('bayt')} bayt -> {y.get('stl')}")
    except Exception as e:                                        # noqa: BLE001
        return _yaz(adim, f"yükleme başarısız: {e}")

    # 3 ── kuyruğa al
    try:
        istek = json.dumps({"stl": y["stl"], "tip": "roket", "hiz": 20.0,
                            "kalite": "hizli"}).encode()
        k = _istek(f"{p.url}/analiz", istek)
        is_id = k.get("is_id")
        kaydet("analiz-kuyruga", bool(is_id), k)
    except Exception as e:                                        # noqa: BLE001
        return _yaz(adim, f"kuyruğa alma başarısız: {e}")

    # 4 ── worker koşuyor mu, sonuç geliyor mu
    bitis, son = time.time() + p.bekle, None
    while time.time() < bitis:
        d = _istek(f"{p.url}/is/{is_id}")
        if d.get("durum") in ("bitti", "hata"):
            son = d
            break
        time.sleep(10)
    if son is None:
        return _yaz(adim, f"iş {p.bekle} sn içinde bitmedi — worker koşuyor mu?")
    kaydet("worker", son["durum"] == "bitti", son["durum"])

    # 5 ── sözleşme: sınıf sayıyla BİRLİKTE mi geldi
    r = son.get("sonuc") or {}
    kaydet("sozlesme-sinif", bool((r.get("gecerlilik") or {}).get("genel")),
           (r.get("gecerlilik") or {}).get("genel"))
    kaydet("sozlesme-sayi", (r.get("sonuc") or {}).get("cd") is not None,
           (r.get("sonuc") or {}).get("cd"))

    return _yaz(adim, None, r)


def _yaz(adim: list[dict], hata: str | None, sonuc: dict | None = None) -> int:
    tamam = all(x["ok"] for x in adim) and not hata
    o = {"zincir_tamam": tamam, "adimlar": adim, "hata": hata,
         "sonuc_ozeti": {k: (sonuc or {}).get(k) for k in ("sonuc", "gecerlilik")},
         "_uretim": "python experiments/konteyner_duman_testi.py"}
    KANIT.write_text(json.dumps(o, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{'✅ ZİNCİR TAMAM' if tamam else '❌ ZİNCİR KIRIK'}"
          + (f" — {hata}" if hata else ""))
    print(f"-> {KANIT.name}")
    return 0 if tamam else 1


if __name__ == "__main__":
    raise SystemExit(main())
