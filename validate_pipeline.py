"""Pipeline validasyon koşusu: bilinen-doğru çapaları (validation_anchors.ANCHORS)
run_vehicle_analysis'ten geçirip ÖLÇÜLEN hata bandını üretir → validation_band.json.
Bu dosya yazıldığında model_uncertainty_pct literatür-öncülü bırakıp ölçülen bandı kullanır.

CFD GEREKTİRİR (her çapa 3-mesh GCI ile dakikalar). Koşu meşgulken çalıştırma.
Kullanım: python validate_pipeline.py [--hiz 30] [--anchor sphere]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from validation_anchors import _BAND_FILE, ANCHORS  # noqa: E402
from vehicle_pipeline import run_vehicle_analysis  # noqa: E402


def ahmed_body() -> trimesh.Trimesh:
    """Ahmed gövdesi, SAE standart ölçüler (Ahmed 1984): L=1.044 m, W=0.389, H=0.288,
    ön yuvarlatma R=0.100, arka slant 0.222 m @ 25°. Gövde konvekstir → yoğun kenar/
    yuvarlatma örneklemesinin konveks zarfı geçerli yüzeydir. Ayaklar (stilts) CFD
    konvansiyonu gereği ihmal. Burun x=0'da (akış +x), taban z=0 (zemin clearance
    run_vehicle_analysis(ground_clearance=0.05) ile verilir)."""
    L, W, H, R = 1.044, 0.389, 0.288, 0.100
    ang = math.radians(25.0)
    sx, sz = 0.222 * math.cos(ang), 0.222 * math.sin(ang)
    pts: list[tuple[float, float, float]] = []
    for t in np.linspace(0.0, math.pi / 2, 16):
        x, d = R * (1 - math.cos(t)), R * math.sin(t)
        w = W / 2 - R + d
        for z in (R, H - R):                       # dikey ön kenar yuvarlatması
            pts += [(x, -w, z), (x, w, z)]
        for y in (-(W / 2 - R), W / 2 - R):        # yatay ön kenar yuvarlatması
            pts += [(x, y, R - d), (x, y, H - R + d)]
    for cy in (-(W / 2 - R), W / 2 - R):           # ön köşe küre-oktantları
        for cz, sgn in ((R, -1.0), (H - R, 1.0)):
            for t in np.linspace(0.0, math.pi / 2, 8):
                for u in np.linspace(0.0, math.pi / 2, 8):
                    pts.append((R - R * math.cos(t),
                                cy + math.copysign(R * math.sin(t) * math.cos(u), cy),
                                cz + sgn * R * math.sin(t) * math.sin(u)))
    for x in (R, L - sx):                          # ana gövde + slant başlangıcı
        for y in (-W / 2, W / 2):
            pts += [(x, y, 0.0), (x, y, H)]
    for y in (-W / 2, W / 2):                      # taban (base) köşeleri
        pts += [(L, y, 0.0), (L, y, H - sz)]
    return trimesh.convex.convex_hull(np.asarray(pts, float)).subdivide()


def disk_body() -> trimesh.Trimesh:
    """Akışa dik dairesel disk (t/D=0.1): keskin-kenar ayrılması → Re-duyarsız ve
    türbülans-modeli-toleranslı bluff çapa (Hoerner Cd≈1.17). Silindir ekseni +x'e döndürülür."""
    m = trimesh.creation.cylinder(radius=0.05, height=0.01, sections=64)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    return m


# çapa → (geometri üreteci, pipeline araç-tipi, koşu-parametreleri).
# Hız seçimi çapanın Re bandına oturur: Ahmed 40 m/s → Re_L≈2.8e6 (Meile 2011);
# küp/disk keskin-kenarlı, Re-duyarsız → varsayılan hız.
_GEOM = {
    # cube: y⁺-hedef 1 katmanları keskin kenarda KISMÎ çöküyordu (ölçülen y⁺=68) →
    # katmansız hassas_nl (v4'te Cd tekrarlanabilir oldu ama dizi mixed kaldı) + v5:
    # yakın-iz kutusu (ayrılma-bölgesi çözünürlüğü — mixed dizinin kalan şüphelisi).
    # Kutu bütçesi: 0.2×0.14×0.14 m³ @ L2 (2.8mm) ≈ 180k hücre (tavan 2.5M içinde).
    "cube": (lambda: trimesh.creation.box(extents=(0.1, 0.1, 0.1)), "genel",
             {"quality": "hassas_nl",
              "refinement_regions": [
                  {"ad": "izBolgesi", "min": (0.05, -0.07, -0.07),
                   "max": (0.25, 0.07, 0.07), "level": 2}]}),
    "disk": (disk_body, "genel", {}),
    # ahmed: katmanlar y⁺=30 hedefiyle DE örülmedi (v4: y⁺=5238; ilk-katman/yüzey-hücresi
    # ~0.01 — snappy kalınlık-kısıtı). v5: bütçe gövde-altı boşluğa + yakın-ize yığılır:
    # gap kutusu L4 (7.3mm → 50mm boşlukta ~7 hücre) ≈160k, iz kutusu L3 ≈85k.
    "ahmed_25": (ahmed_body, "genel", {"velocity": 40.0, "ground_clearance": 0.05,
                                       "n_layers": 8, "yplus_target": 30.0,
                                       "refinement_regions": [
                                           {"ad": "altBosluk", "min": (-0.05, -0.22, -0.051),
                                            "max": (1.10, 0.22, 0.07), "level": 4},
                                           {"ad": "yakinIz", "min": (1.04, -0.30, -0.051),
                                            "max": (2.10, 0.30, 0.35), "level": 3}]}),
}

# Koşulamayan çapalar — gerekçesiyle (dürüst V&V: setup-uyumsuz koşu validasyon değildir).
_SKIP_REASON = {
    "sphere": ("subkritik küre GEÇİŞ-BASKIN (laminer sınır tabakası + türbülanslı iz); "
               "tam-türbülanslı kOmegaSST ile setup-uyumsuz — 2026-07-06 kampanyası "
               "Cd=0.349 (türbülanslı-BL davranışı) ölçtü, ref 0.47 laminer-BL. "
               "LM geçiş-modeli yolu gerekir (TMR/standalone)."),
    "naca0012_a0": "2B airfoil → TMR yolu kapsar (tmr_cfd/), 3B pipeline değil.",
}

# LSR-kabul eşiği: sayısal band model-öncül bandından (bluff %10-20) küçük olmalı ki
# çapa model hatasını AYIRT EDEBİLSİN; daha geniş sayısal band validasyon yapamaz.
LSR_U_MAX_PCT = 15.0


def _accept(gci: dict, lsr: dict | None, cd_richardson, cd_fine):
    """Çapa kabul kararı: (kabul_mü, cd_pred, yontem). Öncelik: asimptotik 3-mesh GCI;
    yoksa LSR bandı yeterince darsa (U<%15) LSR-ekstrapolasyonu; yoksa RED."""
    asy = gci.get("asymptotic") if gci else None
    gci_ok = bool(gci) and gci.get("monotonic") and gci.get("p_in_range") \
        and gci.get("gci_fine_pct", 1e9) < 5.0 and asy is not None and 0.5 <= asy <= 2.0
    if gci_ok and cd_richardson and cd_richardson > 0:
        return True, cd_richardson, "GCI (3-mesh, asimptotik)"
    if lsr and lsr.get("u_pct", 1e9) < LSR_U_MAX_PCT and lsr.get("f_exact", 0) > 0:
        return True, lsr["f_exact"], f"LSR ({lsr['n']}-seviye, U=%{lsr['u_pct']})"
    return False, cd_fine, None


def _run_anchor(name: str, velocity: float, out_root: str) -> dict | None:
    spec = ANCHORS[name]
    if name not in _GEOM:
        return {"atlandi": _SKIP_REASON.get(name, "geometri üreteci yok")}
    gen, vtype, kw = _GEOM[name]
    v = kw.get("velocity", velocity)
    stl = HERE / out_root / f"_anchor_{name}.stl"
    stl.parent.mkdir(parents=True, exist_ok=True)
    gen().export(stl)
    r = run_vehicle_analysis(str(stl), vehicle_type=vtype, velocity=v,
                             quality=kw.get("quality", "hassas"),
                             n_layers=kw.get("n_layers", 0),
                             yplus_target=kw.get("yplus_target", 30.0),
                             mesh_sensitivity=True, mesh_levels=4,
                             out_root=out_root, ground_clearance=kw.get("ground_clearance"),
                             refinement_regions=kw.get("refinement_regions"))
    if r.status != "ok" or r.cd is None:
        return {"durum": "koşu başarısız", "hata": r.error[-400:]}   # kuyruk: asıl hata sonda
    # GUARD (dürüst V&V): mesh-bağımsızlık kanıtı olmadan banda yazılmaz. Kanıt yolu iki:
    # asimptotik 3-mesh GCI YA DA 4-seviye LSR dar-bandı (U<%15 — model-öncülünden küçük,
    # yoksa çapa model hatasını ayırt edemez).
    md = r.mesh_duyarlilik or {}
    converged, cd_pred, yontem = _accept(md.get("gci") or {}, md.get("lsr"),
                                         r.cd_richardson, r.cd)
    if not converged or cd_pred is None or cd_pred <= 0:
        return {"durum": "REDDEDİLDİ — mesh-bağımsızlığı gösterilemedi (banda yazılmaz)",
                "regime": spec["regime"], "Cd_ref": spec["Cd"], "Cd_ince": r.cd,
                "hiz_ms": v, "verdikt": md.get("verdikt"), "lsr": md.get("lsr"),
                "kaynak_ref": spec["ref"]}
    err = abs(cd_pred - spec["Cd"]) / spec["Cd"] * 100
    return {"regime": spec["regime"], "Cd_ref": spec["Cd"], "Cd_pipeline": round(cd_pred, 5),
            "hata_pct": round(err, 2), "hiz_ms": v, "yontem": yontem,
            "u_sayisal_pct": (r.belirsizlik or {}).get("u_sayisal_pct"),
            "kaynak_ref": spec["ref"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hiz", type=float, default=30.0)
    ap.add_argument("--anchor", default="all")
    ap.add_argument("--out", default="validation_anchors_runs")
    args = ap.parse_args()
    names = list(ANCHORS) if args.anchor == "all" else [args.anchor]
    results = {n: _run_anchor(n, args.hiz, args.out) for n in names}

    # rejim-başına en kötü ölçülen hatayı duvar-çözünür band olarak yaz (muhafazakâr)
    by_regime = defaultdict(list)
    for n, res in results.items():
        if res and res.get("hata_pct") is not None:
            by_regime[res["regime"]].append(res["hata_pct"])
    band = {}
    if _BAND_FILE.exists():
        try:
            band = json.loads(_BAND_FILE.read_text(encoding="utf-8"))
        except Exception:
            band = {}
    for regime, errs in by_regime.items():
        eski = band.get(regime, {}).get("wall_resolved")
        yeni = max(errs + ([eski] if eski is not None else []))   # tarihsel maksimum korunur
        band.setdefault(regime, {})["wall_resolved"] = round(yeni, 2)
    if by_regime:
        _BAND_FILE.write_text(json.dumps(band, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"sonuclar": results, "yazilan_band": band}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
