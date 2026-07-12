"""Analiz iş-kuyruğu — '5 varyantı sıraya at, yemeğe git' iş-akışı.

Bu haftaki elle-PowerShell kampanya orkestratörlerinin genelleştirilmişi: işler
kuyruk.jsonl'e eklenir; TEK worker sırayla koşar (disk bekçisi + iş-başına log).
Worker kilidi dosya-tabanlıdır (kuyruk.lock, PID'li) — ikinci worker başlamaz;
CFD zaten makineyi doyurur, paralel worker anlamsız.

Durumlar: bekliyor → kosuyor → bitti | hata. Her güncelleme dosyayı atomik
yeniden yazar (küçük ölçek; yüzlerce iş için yeterli).

CLI: python kuyruk.py ekle model.stl [--tip roket --hiz 30 --alpha 0 --kalite hassas
                                      --duyarlilik --seviyeler 4]
     python kuyruk.py listele | calis | temizle
GUI: app_analyzer 'Kuyruğa Ekle' + KuyrukDialog.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
KUYRUK = HERE / "kuyruk.jsonl"
KILIT = HERE / "kuyruk.lock"
MIN_DISK_GB = 8.0


def _yukle() -> list[dict]:
    if not KUYRUK.exists():
        return []
    out = []
    for line in KUYRUK.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _kaydet(isler: list[dict]) -> None:
    tmp = KUYRUK.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in isler),
                   encoding="utf-8")
    tmp.replace(KUYRUK)


def ekle(params: dict) -> dict:
    """İş ekle. params = run_vehicle_analysis kwargs'ları (stl_path zorunlu)."""
    if not params.get("stl_path"):
        raise ValueError("stl_path zorunlu")
    is_ = {"id": uuid.uuid4().hex[:8], "ts": time.strftime("%Y-%m-%d %H:%M"),
           "durum": "bekliyor", "params": params}
    isler = _yukle()
    isler.append(is_)
    _kaydet(isler)
    return is_


def listele() -> list[dict]:
    return _yukle()


def temizle(hepsi: bool = False) -> int:
    """bitti/hata işleri (hepsi=True: tümünü) kuyruktan düşür; kalan sayısı döner."""
    isler = [] if hepsi else [i for i in _yukle() if i["durum"] in ("bekliyor", "kosuyor")]
    _kaydet(isler)
    return len(isler)


def _disk_gb() -> float:
    import shutil
    return shutil.disk_usage(HERE).free / 1e9


def _kilit_al() -> bool:
    try:
        fd = os.open(KILIT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _guncelle(is_id: str, **alanlar) -> None:
    isler = _yukle()
    for i in isler:
        if i["id"] == is_id:
            i.update(alanlar)
    _kaydet(isler)


def calis(runner=None, once: bool = False) -> dict:
    """Worker: bekleyen işleri SIRAYLA koş. runner enjekte edilebilir (test);
    varsayılan run_vehicle_analysis. once=True → tek iş koşup çık (test/adım-adım)."""
    if not _kilit_al():
        return {"durum": "kilitli", "mesaj": f"başka worker aktif ({KILIT})"}
    ozet = {"bitti": 0, "hata": 0, "atlandi_disk": 0}
    try:
        if runner is None:
            from vehicle_pipeline import run_vehicle_analysis

            def runner(p):
                r = run_vehicle_analysis(**p)
                return {"status": r.status, "cd": r.cd,
                        "u_pct": (r.belirsizlik or {}).get("u_toplam_pct"),
                        "rapor": r.report, "hata": (r.error or "")[-300:]}
        while True:
            bekleyen = [i for i in _yukle() if i["durum"] == "bekliyor"]
            if not bekleyen:
                break
            is_ = bekleyen[0]
            if _disk_gb() < MIN_DISK_GB:
                _guncelle(is_["id"], durum="hata",
                          sonuc={"hata": f"disk < {MIN_DISK_GB} GB — atlandı"})
                ozet["atlandi_disk"] += 1
                continue
            _guncelle(is_["id"], durum="kosuyor", baslama=time.strftime("%H:%M:%S"))
            t0 = time.time()
            try:
                sonuc = runner(is_["params"])
                durum = "bitti" if sonuc.get("status") == "ok" else "hata"
            except Exception as e:
                sonuc, durum = {"hata": str(e)[-300:]}, "hata"
            _guncelle(is_["id"], durum=durum, sonuc=sonuc,
                      sure_dk=round((time.time() - t0) / 60, 1))
            ozet["bitti" if durum == "bitti" else "hata"] += 1
            if once:
                break
    finally:
        KILIT.unlink(missing_ok=True)
    return ozet


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cli = argparse.ArgumentParser()
    cli.add_argument("komut", choices=["ekle", "listele", "calis", "temizle"])
    cli.add_argument("stl", nargs="?")
    cli.add_argument("--tip", default="ucak")
    cli.add_argument("--hiz", type=float, default=30.0)
    cli.add_argument("--alpha", type=float, default=0.0)
    cli.add_argument("--kalite", default="standart")
    cli.add_argument("--duyarlilik", action="store_true")
    cli.add_argument("--seviyeler", type=int, default=3)
    args = cli.parse_args()
    if args.komut == "ekle":
        if not args.stl:
            sys.exit("ekle için STL yolu gerekli")
        is_ = ekle({"stl_path": args.stl, "vehicle_type": args.tip, "velocity": args.hiz,
                    "alpha_deg": args.alpha, "quality": args.kalite,
                    "mesh_sensitivity": args.duyarlilik, "mesh_levels": args.seviyeler})
        print(json.dumps(is_, indent=2, ensure_ascii=False))
    elif args.komut == "listele":
        for i in listele():
            p = i["params"]
            print(f"[{i['durum']:>8}] {i['id']}  {Path(p['stl_path']).name}  "
                  f"tip={p.get('vehicle_type')} V={p.get('velocity')} "
                  f"kalite={p.get('quality')}  {i.get('sure_dk', '')}"
                  + (f"  Cd={i['sonuc'].get('cd')}" if i.get("sonuc") else ""))
    elif args.komut == "temizle":
        print("kalan:", temizle())
    else:
        print(json.dumps(calis(), indent=2, ensure_ascii=False))
