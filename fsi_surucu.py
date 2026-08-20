"""İki-yönlü FSI sürücüsü — doğrulanmış dört parçayı bir kuplaj turuna bağlar.

NEDEN: parçaların hepsi VAR ve doğrulanmış, ama üretim yolu hiçbirini sürmüyordu.
Depo bunu iki yerde kayıtlı tutuyordu (`analysis/openfoam_runner.py:146`,
`coupling_fsi.py:262`): "`fsi_twoway.partitioned_fsi` DOGRULANMIS ama YALNIZ
TESTLERDEN". Eksik olan yeni fizik değil, `map_fn`'di.

KUPLAJ TURU (Dirichlet-Neumann):
    x  = FEA yüzey düğümlerinin yer değiştirmesi (K×3, düzleştirilmiş)
    ├─ fea_displacement_to_cfd_points  → CFD yama noktalarına taşı
    ├─ write_point_displacement        → 0/pointDisplacement
    ├─ CFD çöz (hareketli ağ)          → yüzey basıncı VTK
    ├─ cfd_pressure_to_fea_loads       → düğüm kuvvetleri
    ├─ write_cload → run_ccx → parse_frd
    └─ yeni x

`partitioned_fsi` bu turu sabit-noktaya sürer (Aitken Δ², Küttler-Wall 2008).

DOĞRULAMA SÖZLEŞMESİ: sentetik girdiyle "çalışıyor" demek bu depoda YETMEZ.
`--kuru` kipi yalnız TESİSATI sınar (parçalar birbirine uyuyor mu, boyutlar
tutuyor mu) ve çıktısında bunu AÇIKÇA söyler; fiziksel yakınsama iddiası
GERÇEK kuplaj turundan gelir ve artık geçmişiyle birlikte kanıta yazılır.

    python fsi_surucu.py --kuru <run_dir>     # tesisat denetimi (CFD koşmaz)
    python fsi_surucu.py <run_dir>            # gerçek kuplaj
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))


@dataclass
class KuplajVakasi:
    """Bir FSI koşusunun tüm girdileri — sürücü BUNDAN başkasını varsaymaz."""
    run_dir: Path
    yama: str = "gövde"                  # CFD gövde yaması
    malzeme: str = "aluminum_6061"
    kisit: str = "y_min"
    rho: float = 1.225
    max_dis_iter: int = 8                # Aitken ile 3-6 tipik; tavan güvenlik
    tol: float = 1e-6                    # [m] arayüz yer değiştirme artığı
    kuru: bool = False
    gecmis: list = field(default_factory=list)


def _fea_yuzey(vaka: KuplajVakasi):
    """FEA yüzey düğümleri (K,3) ve onları taşıyan STL yolu."""
    import trimesh
    stl = next(vaka.run_dir.glob("*_prep.stl"), None) or next(
        vaka.run_dir.glob("*.stl"), None)
    if stl is None:
        raise FileNotFoundError(f"{vaka.run_dir}: FEA yüzey STL'i yok")
    m = trimesh.load(str(stl), force="mesh")
    return np.asarray(m.vertices, float), stl


def _cfd_yama_noktalari(vaka: KuplajVakasi):
    """CFD gövde yamasının noktaları (M,3) — VTK'dan okunur."""
    from coupling_fsi import _parse_legacy_vtk
    vtk = _son_vtk(vaka)
    points, _polys, _p, _loc = _parse_legacy_vtk(Path(vtk))
    return np.asarray(points, float), vtk


def _son_vtk(vaka: KuplajVakasi) -> str:
    """En güncel yüzey-basınç VTK'sı. YOKSA HATA — sessizce sıfır dönmez."""
    from vehicle_fea import resolve_cp_vtk
    sonuc = {}
    sj = vaka.run_dir / "sonuc.json"
    if sj.exists():
        sonuc = json.loads(sj.read_text(encoding="utf-8"))
    v = resolve_cp_vtk(vaka.run_dir, sonuc)
    if not v:
        raise FileNotFoundError(
            f"{vaka.run_dir}: yüzey-basınç VTK'sı bulunamadı — kuplaj turu "
            "CFD sonucu OLMADAN başlayamaz (önce tek-yönlü koşu gerekir)")
    return v


def tesisat_denetimi(vaka: KuplajVakasi) -> dict:
    """Parçalar birbirine UYUYOR mu — CFD koşmadan ölçülebilen her şey.

    Fiziksel yakınsama İDDİA ETMEZ; yalnız boyutların, dosyaların ve
    taşıma operatörünün tutarlı olduğunu söyler. `--kuru` bunu koşar.
    """
    fea_nodes, fea_stl = _fea_yuzey(vaka)
    cfd_points, vtk = _cfd_yama_noktalari(vaka)
    from coupling_fsi import fea_displacement_to_cfd_points

    # RIJIT OTELEME SINAMASI: sabit bir alan HATASIZ tasinmali (birim-bolunum).
    # Bu, tasima operatorunun bu VAKA GEOMETRISINDE de dogru oldugunu olcer —
    # birim testi sentetik noktalarla yapiyor, burada gercek ag kullaniliyor.
    sabit = np.tile(np.array([1e-3, -2e-3, 3e-4]), (len(fea_nodes), 1))
    tasinan = fea_displacement_to_cfd_points(fea_nodes, sabit, cfd_points)
    rijit_hata = float(np.abs(tasinan - sabit[0]).max())

    return {
        "fea_dugum": int(len(fea_nodes)), "cfd_nokta": int(len(cfd_points)),
        "fea_stl": str(fea_stl), "vtk": str(vtk),
        "rijit_oteleme_hatasi_m": rijit_hata,
        "tesisat": "UYUMLU" if rijit_hata < 1e-12 else "TAŞIMA HATALI",
        "_kapsam": ("YALNIZ TESİSAT — parçalar uyuşuyor ve taşıma operatörü bu "
                    "geometride rijit ötelemeyi hatasız taşıyor. Fiziksel "
                    "yakınsama İDDİA EDİLMİYOR; o GERÇEK kuplaj turundan gelir."),
    }


def kuplaj_haritasi(vaka: KuplajVakasi):
    """`partitioned_fsi`'ye verilecek map_fn: x → bir tam kuplaj turu → x_yeni."""
    from analysis.ccx_runner import run_ccx
    from analysis.frd_parser import parse_frd
    from coupling_fsi import (
        cfd_pressure_to_fea_loads,
        fea_displacement_to_cfd_points,
        write_cload,
        write_point_displacement,
    )

    fea_nodes, fea_stl = _fea_yuzey(vaka)
    cfd_points, _ = _cfd_yama_noktalari(vaka)
    K = len(fea_nodes)

    def map_fn(x):
        d_fea = np.asarray(x, float).reshape(K, 3)

        # 1) Yapi -> akiskan: deplasmani CFD noktalarina tasi ve aga yaz
        d_cfd = fea_displacement_to_cfd_points(fea_nodes, d_fea, cfd_points)
        write_point_displacement(vaka.run_dir, vaka.yama, d_cfd)

        # 2) CFD'yi HAREKETLI AGDA yeniden coz.
        #
        # EKSIK PARCA — ADIYLA SOYLENIYOR: `run_cfd(case, out_dir)` vakayi
        # SIFIRDAN kurar; mevcut bir vakayi yer degistirmis agla YENIDEN cozen
        # bir giris noktasi yok. Kuplaj turunun her adimi bunu ister.
        # Gereken: moveDynamicMesh (ya da cozucunun kendi ag hareketi) +
        # latestTime'dan devam + yeni yuzey VTK'si.
        # Sessizce atlanmiyor: burasi ACIKCA duser, cunku CFD'yi kosmadan
        # donen bir map_fn "yakinsadi" der ve bu, bu deponun reddettigi
        # sahte-kesinligin ta kendisi olurdu.
        from analysis import openfoam_runner as _of
        if not hasattr(_of, "run_cfd_yeniden"):
            raise NotImplementedError(
                "analysis.openfoam_runner.run_cfd_yeniden YOK — kuplaj turu "
                "hareketli agda CFD yeniden-cozumu gerektiriyor. Tesisatin "
                "geri kalani `--kuru` ile dogrulanabilir.")
        _r = _of.run_cfd_yeniden(vaka.run_dir)
        if _r.get("durum") != "ok":
            raise RuntimeError(f"CFD yeniden-cozumu dustu: {_r.get('durum')}")
        # Yuzey VTK'si BU katmanda uretilir (analysis/ kendi icinde kapali).
        from vehicle_pipeline import export_surface_vtk
        export_surface_vtk(_r["case"], _r["govde_yamasi"])

        # 3) Akiskan -> yapi: yuzey basinci -> dugum kuvvetleri -> CalculiX
        yukler = cfd_pressure_to_fea_loads(_son_vtk(vaka), str(fea_stl),
                                           rho=vaka.rho)
        if yukler.get("status") == "FAILED":
            raise RuntimeError(f"yük aktarımı düştü: {yukler.get('error')}")
        cload = write_cload(yukler["node_forces"], str(vaka.run_dir / "fsi.cload"))
        inp = next(vaka.run_dir.glob("*.inp"))
        run_ccx(inp, timeout=1800)

        # 4) Yeni deplasman
        frd = parse_frd(inp.with_suffix(".frd"))
        yeni = np.asarray(frd.displacements, float)[:K]
        vaka.gecmis.append({"tur": len(vaka.gecmis) + 1,
                            "max_disp_mm": float(np.abs(yeni).max() * 1000),
                            "cload": cload})
        return yeni.ravel()

    return map_fn, K


def fsi_kos(vaka: KuplajVakasi) -> dict:
    from fsi_twoway import partitioned_fsi

    tesisat = tesisat_denetimi(vaka)
    if tesisat["tesisat"] != "UYUMLU":
        return {"vaka": "FSI kuplaj", "verdikt": "❌ TESİSAT UYUMSUZ",
                "tesisat": tesisat}
    if vaka.kuru:
        return {"vaka": "FSI kuplaj — KURU KOŞU",
                # Kuru dal da kanit uretiyor; depo kurali burada da gecerli
                # (saglik olceri bu eksigi hemen yakaladi).
                "_uretim": f"Üretim: python fsi_surucu.py --kuru {vaka.run_dir}",
                "verdikt": ("⚠️ YALNIZ TESİSAT DENETLENDİ — CFD koşulmadı, "
                            "fiziksel yakınsama İDDİA EDİLMİYOR"),
                "tesisat": tesisat}

    map_fn, K = kuplaj_haritasi(vaka)
    x0 = np.zeros(K * 3)
    x, bilgi = partitioned_fsi(map_fn, x0, tol=vaka.tol,
                               max_iter=vaka.max_dis_iter, aitken=True)
    yakinsadi = bool(bilgi["converged"])
    return {
        "vaka": "FSI kuplaj — iki yönlü (Aitken)",
        "_uretim": f"Üretim: python fsi_surucu.py {vaka.run_dir}",
        "verdikt": (f"{'✅ YAKINSADI' if yakinsadi else '⚠️ YAKINSAMADI'} — "
                    f"{bilgi['iters']} dış iterasyon, son artık "
                    f"{bilgi['res_history'][-1]:.3e} m (tol {vaka.tol:.0e})"),
        "tesisat": tesisat, "yakinsadi": yakinsadi,
        "iterasyon": bilgi["iters"],
        "artik_gecmisi": bilgi["res_history"],
        "omega_gecmisi": bilgi["omega_history"],
        "tur_gecmisi": vaka.gecmis,
        "max_disp_mm": float(np.abs(x).max() * 1000),
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip().splitlines()[-2].strip())
        return 2
    vaka = KuplajVakasi(run_dir=Path(args[0]), kuru="--kuru" in sys.argv)
    r = fsi_kos(vaka)
    print(json.dumps(r, indent=2, ensure_ascii=False)[:2000])
    (KOK / "fsi_kuplaj.json").write_text(
        json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("-> fsi_kuplaj.json")
    return 0 if r.get("yakinsadi") or vaka.kuru else 1


if __name__ == "__main__":
    raise SystemExit(main())
