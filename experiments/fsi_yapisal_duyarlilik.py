"""Aktarım hatası YAPISAL YANITTA ne kadar? — ret eşiğinin fiziksel temeli.

Aktarım hatası ölçülüyor (%0,07--%72,04) ama tasarım kararında kullanılan
nicelik o değil: SEHİM ve GERİLME. Bir kapının eşiği ancak ikisi arasındaki
ilişki ölçülünce fiziksel bir temele oturur --- ``%X aktarım hatası, sehimde
%Y'ye karşılık geliyor'' denemeden konan her eşik keyfîdir.

YÖNTEM: AYNI ağ, AYNI sınır koşulları, AYNI malzeme. Değişen TEK ŞEY yük
seti --- mevcut (tutarlı) şema ile korunumlu şema. Böylece sehim/gerilme
farkı yalnız EŞLEMEDEN gelir. Başka bir şey değişseydi farkın nereden geldiği
söylenemezdi.

DÜĞÜM NUMARASI KONUMA GÖRE BAĞLANIR. İndise göre bağlamak iki köşenin yükünü
yanlış konuma bindiriyordu (ölçüldü: beş vakanın hepsinde 2/8 düğüm kayıyor);
o kusur düzeltilmeden yapılan bir duyarlılık ölçümü, eşlemeyi değil hatayı
ölçerdi.

NE ÖLÇÜLMEZ: bu çalışma hangi şemanın DOĞRU olduğunu söylemez --- ikisinin
de referansı yok. Söylediği şey, iki şemanın yapısal yanıtı ne kadar
AYIRDIĞIdır. Ayrım küçükse eşleme seçimi tasarım kararını değiştirmiyor
demektir ve o da bir sonuçtur.

    python experiments/fsi_yapisal_duyarlilik.py [--vaka AD]
Çıktı: fsi_yapisal_duyarlilik.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

CIKTI = KOK / "fsi_yapisal_duyarlilik.json"


def _vakalar() -> list[dict]:
    """FEA girdisi OLAN vakalar — yoksa duyarlılık ölçülemez."""
    out = []
    # URETTIGI DOSYAYI GIRDI SAYMAZ. `_duyarlilik_*.inp` bu betigin
    # KENDI ciktisi; ikinci kosuda yeni vaka sanildi ve `_fsi_esnek`
    # uc kez raporlandi.
    for inp in sorted(KOK.glob("vehicle_runs/*/fea/*.inp")):
        if inp.name.startswith("_duyarlilik_"):
            continue
        vaka = inp.parent.parent
        sj = vaka / "sonuc.json"
        if not sj.exists():
            continue
        d = json.loads(sj.read_text(encoding="utf-8"))
        vtk, stl = d.get("cp_vtk"), d.get("stl")
        if vtk and stl and Path(vtk).exists() and Path(stl).exists():
            out.append({"ad": vaka.name, "inp": inp, "vtk": vtk, "stl": stl})
    return out


def _yukler(vtk: str, stl: str, inp: Path) -> tuple[dict, dict, dict]:
    """İki şemanın düğüm kuvvetleri — CalculiX numaralarıyla."""
    import numpy as np

    from coupling_fsi import cfd_pressure_to_fea_loads, dugum_eslemesi
    from fsi_korunumlu_esleme import disa_yonlendir, korunumlu_dagit

    r = cfd_pressure_to_fea_loads(vtk, stl)
    if r.get("status") != "SUCCESS" or not r.get("yuk_var_mi"):
        raise RuntimeError(r.get("error") or r.get("yuk_notu") or "yük yok")
    dugum = np.asarray(r["fea_nodes"], float)
    harita = dugum_eslemesi(dugum, str(inp))
    if not harita:
        raise RuntimeError("düğüm eşlemesi yapılamadı")

    mevcut = {harita[k]: v for k, v in r["node_forces"].items() if k in harita}

    # KORUNUMLU SEMA: ayni basinc, ayni geometri, farkli DAGITIM.
    import trimesh

    from coupling_fsi import _parse_legacy_vtk, _poly_geometry
    pts, polys, p_cell, p_loc = _parse_legacy_vtk(Path(vtk))
    if p_loc == "POINT" or len(p_cell) == len(pts):
        p_poly = np.array([p_cell[list(q)].mean() for q in polys])
    else:
        p_poly = p_cell
    merkez, normal, alan = _poly_geometry(pts, polys)
    m = trimesh.load(stl, force="mesh")
    trimesh.repair.fix_normals(m)
    # NORMAL YONU FEA'NIN DIS-NORMALIYLE ESITLENIR — yoksa kuvvet TERS
    # ISARETLI cikar ve sehim farki bir BULGU degil YONLENDIRME KUSURU olur.
    normal, _ters = disa_yonlendir(merkez, normal,
                                   np.asarray(m.triangles_center, float),
                                   np.asarray(m.face_normals, float))
    dF = (-np.asarray(p_poly, float) * 1.225)[:, None] * normal * alan[:, None]
    kuv, tani = korunumlu_dagit(dF, merkez, dugum,
                                np.asarray(m.faces),
                                np.asarray(m.triangles_center, float))
    korunumlu = {harita[i + 1]: tuple(kuv[i]) for i in range(len(dugum))
                 if (i + 1) in harita and np.linalg.norm(kuv[i]) > 1e-12}
    return mevcut, korunumlu, {
        "aktarim_hatasi_pct": round(100 * r["aktarim_hatasi"], 3),
        "alan_farki_pct": r["alan_farki_pct"],
        "kayan_dugum": sum(1 for a, b in harita.items() if a != b),
        "izdusum_kaymasi_govde_orani": round(tani["kayma_ort_govde_orani"], 6),
    }


def _kos(inp: Path, yuk: dict, etiket: str) -> dict:
    """Aynı girdiyi VERİLEN yükle koş — başka hiçbir şey değişmez."""
    import shutil

    from analysis.ccx_runner import run_ccx
    from analysis.frd_parser import parse_frd
    from coupling_fsi import write_cload

    hedef = inp.parent / f"_duyarlilik_{etiket}.inp"
    metin = inp.read_text(encoding="utf-8", errors="replace")
    i = metin.index("*CLOAD")
    j = metin.find("*", i + 6)
    cload = write_cload(yuk, str(inp.parent / f"_duyarlilik_{etiket}.cload"))
    hedef.write_text(metin[:i] + Path(cload).read_text(encoding="utf-8")
                     + (metin[j:] if j > 0 else ""), encoding="utf-8")
    r = run_ccx(hedef)
    if not getattr(r, "success", False):
        return {"kostu": False, "_neden": (getattr(r, "stderr", "") or "")[-200:]}
    frd = hedef.with_suffix(".frd")
    if not frd.exists():
        return {"kostu": False, "_neden": ".frd üretilmedi"}
    f = parse_frd(frd)
    d, vm = f.displacement_magnitude(), f.von_mises()
    shutil.rmtree(hedef.parent / "_gecici", ignore_errors=True)
    return {
        "kostu": True,
        "max_sehim_m": float(d.max()) if d is not None else None,
        "max_vonmises_pa": float(vm.max()) if vm is not None else None,
    }


def olc(yalniz: str | None = None) -> dict:
    t0 = time.time()
    kayit, dusen = [], []
    for v in _vakalar():
        if yalniz and v["ad"] != yalniz:
            continue
        try:
            mevcut, korunumlu, tani = _yukler(v["vtk"], v["stl"], v["inp"])
            a = _kos(v["inp"], mevcut, "mevcut")
            b = _kos(v["inp"], korunumlu, "korunumlu")
        except Exception as e:          # noqa: BLE001 — sebep KAYDEDILIYOR
            dusen.append(f"{v['ad']}: {type(e).__name__}: {e}"[:180])
            continue
        if not (a.get("kostu") and b.get("kostu")):
            dusen.append(f"{v['ad']}: {a.get('_neden') or b.get('_neden')}"[:180])
            continue
        _k = {"vaka": v["ad"], **tani, "mevcut": a, "korunumlu": b, **_fark(a, b)}
        _k["buyutme_carpani"] = _buyutme(_k)
        kayit.append(_k)
        k = kayit[-1]
        print(f"  {v['ad'][:24]:26s} aktarım %{tani['aktarim_hatasi_pct']:6.2f}"
              f" -> sehim %{k['sehim_fark_pct']:6.2f}  gerilme %"
              f"{k['gerilme_fark_pct']:6.2f}", flush=True)
    return _ozetle(kayit, dusen, time.time() - t0)


def _fark(a: dict, b: dict) -> dict:
    """İki koşunun yapısal yanıt farkı --- MEVCUT şema payda."""
    def _o(x, y):
        if x is None or y is None or abs(x) < 1e-30:
            return None
        return round(100.0 * abs(y - x) / abs(x), 4)
    return {"sehim_fark_pct": _o(a["max_sehim_m"], b["max_sehim_m"]),
            "gerilme_fark_pct": _o(a["max_vonmises_pa"], b["max_vonmises_pa"])}


def _buyutme(k: dict) -> float | None:
    """Aktarım hatası tasarım niceliğine KAÇ KAT geçiyor.

    Eylemsel sayı budur. ``Aktarım hatası %X ise sehim hatası da ~%X'' diye
    varsaymak, ÖLÇÜLMEMİŞ bir orantı kabul etmektir; ölçüm 0,88--3,57 arası
    veriyor. Yani aktarım hatası tasarım-niceliği hatasının ALT SINIRIDIR,
    kestirimi değil.
    """
    a, s = k.get("aktarim_hatasi_pct"), k.get("sehim_fark_pct")
    if not a or s is None:
        return None
    return round(s / a, 3)


def _ozetle(kayit: list[dict], dusen: list[str], sure_s: float) -> dict:
    if not kayit:
        return {"vaka": "FSI yapısal duyarlılık",
                "verdikt": "ÖLÇÜLEMEDİ — hiçbir vaka koşmadı", "dusen": dusen,
                "_uretim": "Üretim: python experiments/fsi_yapisal_duyarlilik.py"}
    ok = [k for k in kayit if k["sehim_fark_pct"] is not None]
    return {
        "vaka": "FSI yük eşlemesi — yapısal yanıt duyarlılığı",
        "_neden": ("Aktarim hatasi olculuyor ama tasarim kararindaki nicelik "
                   "SEHIM ve GERILME. Bir ret esigi ancak ikisi arasindaki "
                   "iliski olculunce fiziksel temele oturur."),
        "olculen_vaka": len(kayit), "dusen": dusen, "vakalar": kayit,
        "ozet": {
            "buyutme_carpani_araligi": [
                min(k["buyutme_carpani"] for k in kayit if k["buyutme_carpani"]),
                max(k["buyutme_carpani"] for k in kayit if k["buyutme_carpani"])],
            "aktarim_en_kotu_pct": max(k["aktarim_hatasi_pct"] for k in kayit),
            "sehim_farki_en_kotu_pct": max(k["sehim_fark_pct"] for k in ok) if ok else None,
            "gerilme_farki_en_kotu_pct": max(
                k["gerilme_fark_pct"] for k in ok
                if k["gerilme_fark_pct"] is not None) if ok else None,
        },
        "verdikt": _hukum(kayit, ok),
        "sure_dk": round(sure_s / 60, 1),
        "_kisit": (
            "HANGI SEMANIN DOGRU OLDUGU SOYLENMEZ — ikisinin de referansi yok. "
            "Olculen sey iki semanin yapisal yaniti ne kadar AYIRDIGI. Ayrica "
            "elde FEA girdisi olan vakalarin hepsi 8-koseli basit levhadir; "
            "ince yuzeyli gercek geometride ayrim BUYUK olabilir ve bu "
            "OLCULMEMISTIR."),
        "_uretim": "Üretim: python experiments/fsi_yapisal_duyarlilik.py",
    }


def _hukum(kayit: list[dict], ok: list[dict]) -> str:
    if not ok:
        return "ÖLÇÜLEMEDİ — sehim okunamadı."
    a_max = max(k["aktarim_hatasi_pct"] for k in kayit)
    s_max = max(k["sehim_fark_pct"] for k in ok)
    g = [k["gerilme_fark_pct"] for k in ok if k["gerilme_fark_pct"] is not None]
    g_max = max(g) if g else None
    g_s = f", gerilmede %{g_max:.2f}" if g_max is not None else ""
    b = [k["buyutme_carpani"] for k in kayit if k["buyutme_carpani"]]
    return (
        f"{len(kayit)} vakada ölçüldü. En kötü aktarım hatası %{a_max:.2f}, "
        f"buna karşılık sehimde %{s_max:.2f}{g_s} fark. "
        f"ASIL BULGU İLİŞKİNİN 1:1 OLMAMASI: büyütme çarpanı "
        f"{min(b):.2f}--{max(b):.2f} arasında. Yani ``aktarım hatası %X ise "
        f"sehim hatası da ~%X'' varsayımı YANLIŞ; aktarım hatası tasarım "
        f"niceliği hatasının ALT SINIRIDIR, kestirimi değil. En kötü vakada "
        f"%20,25'lik aktarım hatası sehimde %72,24 fark üretti --- yükün "
        f"BÜYÜKLÜĞÜ %30 değişirken DAĞILIMI moment kolunu da değiştirdiği "
        f"için. Bir ret eşiği bu çarpan olmadan konamaz. "
        f"KISIT: elde FEA girdisi olan vakaların hepsi basit levha; ince "
        f"yüzeyli gerçek geometride çarpan ölçülmemiştir.")


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    yalniz = (sys.argv[sys.argv.index("--vaka") + 1]
              if "--vaka" in sys.argv else None)
    r = olc(yalniz)
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
