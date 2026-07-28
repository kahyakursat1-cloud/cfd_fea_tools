"""NX EĞİTİM ailesini auto_pilot öğrenme kütüphanesine tohum olarak yazar.

Kütüphanedeki 241 kaydın hiçbirinde `donel_simetri` yok (özellik sonradan eklendi), bu
yüzden kNN gerçek bir multikopteri gördüğünde komşu bulamıyor ve kanatlı tiplere
kayıyor — kural doğru hüküm verse bile onu geçersiz kılıyordu. Bu tohum, kütüphaneye
dönel simetrisi ÖLÇÜLMÜŞ referans vakalar koyar.

YALNIZ eğitim ailesi yazılır. Test ailesini (experiments/nx_geo) tohumlamak
değerlendirmeyi geçersiz kılar — ölçüm kendi eğitim verisinde yapılmış olur.

    python experiments/nx_tohum_uret.py

Çıktı: auto_pilot_nx_seed.jsonl
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import trimesh  # noqa: E402

from auto_pilot import NX_SEED, classify_vehicle  # noqa: E402
from vehicle_pipeline import inspect_geometry  # noqa: E402

EGITIM = HERE / "nx_geo_egitim"
TEST = HERE / "nx_geo"


def main() -> int:
    etiket = EGITIM / "etiketler.json"
    if not etiket.exists():
        print("nx_geo_egitim/etiketler.json yok — önce eğitim ailesini üretin:\n"
              '  NX_AILE=egitim run_journal.exe experiments/nx_geometri_uret.py')
        return 1
    d = json.loads(etiket.read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="nx_tohum_"))
    satir = []
    try:
        for g in d["geometriler"]:
            stl = EGITIM / g["stl"]
            if not stl.exists():
                continue
            m = trimesh.load(stl, force="mesh")
            m.apply_scale(1e-3)
            hedef = tmp / g["stl"]
            m.export(hedef)
            geo = inspect_geometry(str(hedef))
            metrik = classify_vehicle(geo)["metrik"]
            satir.append({
                "ts": "2026-07-27 00:00",
                "dosya": f"nx-egitim:{g['ad']}",
                "kaynak": f"NX-parametrik (insa-aninda etiketli): {g['ad']}",
                "metrik": metrik,
                "otopilot_tip": g["etiket"], "onayli_tip": g["etiket"],
                "cd_toplam": None, "rejim": None})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not satir:
        print("hiç geometri okunamadı")
        return 1
    NX_SEED.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in satir),
                       encoding="utf-8")
    n_sim = sum(1 for s in satir if s["metrik"].get("donel_simetri") is not None)
    print(f"{len(satir)} kayıt -> {NX_SEED.name}  (dönel simetri ölçülen: {n_sim})")
    print("UYARI: test ailesi (experiments/nx_geo) BİLEREK tohumlanmadı — "
          "değerlendirme ayrık kalmalı.")
    return 0


def test_ailesi_tohumlanmadi() -> bool:
    """Kazara test setinin tohuma karışmadığını doğrular (kanıt-hijyeni)."""
    if not NX_SEED.exists():
        return True
    test_adlari = set()
    et = TEST / "etiketler.json"
    if et.exists():
        test_adlari = {g["ad"] for g in
                       json.loads(et.read_text(encoding="utf-8"))["geometriler"]}
    for line in NX_SEED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ad = json.loads(line)["dosya"].split(":", 1)[-1]
        if ad in test_adlari:
            return False
    return True


if __name__ == "__main__":
    sys.exit(main())
