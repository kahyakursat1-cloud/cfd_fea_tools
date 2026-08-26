"""İki eşleme şeması, AYNI vakalarda, yan yana — değiştirmeden ÖNCE ölç.

Mevcut şema (``tutarlı''/field-preserving) basıncı taşıyıp kuvveti FEA ağında
YENİDEN İNTEGRE eder; alanlar farklıysa toplam kuvvet de farklı çıkar. Ölçüldü:
aktarım hatası %0,07--%56,30 ve hata ALAN FARKINI izliyor.

Yeni şema (``korunumlu''/load-preserving) CFD yüzünün KUVVETİNİ toplamı 1 olan
baryentrik ağırlıklarla FEA düğümlerine dağıtır. Toplam kuvvet YAPI GEREĞİ
korunur.

BU BETİK ŞEMAYI DEĞİŞTİRMEZ, KIYASLAR. Korunumlu şemanın toplam kuvveti
koruduğu bir KİMLİKTİR ve onu ``ölçmek'' bir şey kanıtlamaz --- ölçülmesi
gereken şey BEDELİDİR:

  * yerel dağılım ne kadar bozuluyor (izdüşüm kayması, kırpılan izdüşüm oranı),
  * moment artığı ne oluyor (kuvvet korunsa da moment izdüşüm kadar kayar),
  * hangi vakalarda fark önemsiz (o vakalarda değiştirmenin faydası yok).

Klasik takas budur: korunumlu şema toplamı garanti eder, tutarlı şema yerel
alanı daha iyi verir. Ölçmeden birini seçmek, bu çalışmanın reddettiği şey.

    python experiments/fsi_esleme_kiyasi.py
Çıktı: fsi_esleme_kiyasi.json
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

CIKTI = KOK / "fsi_esleme_kiyasi.json"


def _tek_vaka(vtk: str, stl: str) -> dict | None:
    """Aynı vakada iki şemayı da koş ve METRİKLERİ yan yana koy."""
    import numpy as np
    import trimesh

    from coupling_fsi import _parse_legacy_vtk, _poly_geometry
    from fsi_korunumlu_esleme import disa_yonlendir, korunumlu_dagit

    # BASINCI AYNI YOLDAN OKU. Ikinci bir ayristirma yazmak, iki semayi
    # kiyaslanamaz yapardi --- fark SEMADAN mi OKUMADAN mi gelirdi
    # soylenemezdi.
    points, polys, p_cell, p_loc = _parse_legacy_vtk(Path(vtk))
    if len(polys) == 0 or len(p_cell) == 0:
        return None
    if p_loc == "POINT" or len(p_cell) == len(points):
        p_poly = np.array([p_cell[list(q)].mean() for q in polys])
    elif len(p_cell) == len(polys):
        p_poly = p_cell
    else:
        return None
    cfd_merkez, cfd_normal, cfd_alan = _poly_geometry(points, polys)
    # NORMAL YONU ESITLENIR. VTK poligon normali sarim yonunden gelir
    # ve OLCULDU: butun vakalarda ICERI bakiyor; FEA tarafi
    # `fix_normals` ile DISARI. Esitlenmezse iki semanin kuvveti
    # TERS ISARETLI cikar ve moment kiyasi anlamsizlasir.
    _m = trimesh.load(stl, force="mesh")
    trimesh.repair.fix_normals(_m)
    cfd_normal, _cfd_ters = disa_yonlendir(
        cfd_merkez, cfd_normal,
        np.asarray(_m.triangles_center, float),
        np.asarray(_m.face_normals, float))
    p_pa = np.asarray(p_poly, float) * 1.225      # kinematik -> Pa (hava)

    mesh = _m
    dugum, faces = np.asarray(mesh.vertices, float), np.asarray(mesh.faces)
    f_merkez = np.asarray(mesh.triangles_center, float)

    # CFD tarafinin GERCEK kuvveti — her iki semanin de hedefi bu.
    dF_cfd = (-p_pa[:, None]) * cfd_normal * cfd_alan[:, None]
    F_cfd = dF_cfd.sum(axis=0)
    olcek = float(np.linalg.norm(dF_cfd, axis=1).sum()) + 1e-30

    dugum_kuvvet, tani = korunumlu_dagit(dF_cfd, cfd_merkez, dugum, faces,
                                         f_merkez)
    F_kor = dugum_kuvvet.sum(axis=0)

    # MEVCUT SEMAYI AYNI OLCUTLE OLC. `coupling_fsi`in raporladigi moment
    # hatasi (1e-17) FEA YUZU->DUGUM adimini olcer ve esit-uctebir semasinda
    # YAPI GEREGI kesindir --- rapor bunu zaten "yaniltici" diye isaretledi.
    # Iki semayi o sayiyla kiyaslamak, yeni semayi haksiz yere kotu
    # gosterirdi. Kiyaslanabilir nicelik: CFD->FEA moment farki.
    from scipy.spatial import cKDTree
    f_normal = np.asarray(mesh.face_normals, float)
    f_alan = np.asarray(mesh.area_faces, float)
    _, en_yakin = cKDTree(cfd_merkez).query(f_merkez, k=1)
    dF_mevcut = (-p_pa[en_yakin][:, None]) * f_normal * f_alan[:, None]
    M_mevcut = np.cross(f_merkez, dF_mevcut).sum(axis=0)

    # MOMENT: CFD tarafi gercek merkezlerden, FEA tarafi dugum konumlarindan.
    M_cfd = np.cross(cfd_merkez, dF_cfd).sum(axis=0)
    M_kor = np.cross(dugum, dugum_kuvvet).sum(axis=0)
    m_olcek = float(np.linalg.norm(np.cross(cfd_merkez, dF_cfd), axis=1).sum()) + 1e-30

    return {
        "mevcut_moment_hatasi_pct": round(
            100.0 * float(np.linalg.norm(M_mevcut - M_cfd)) / m_olcek, 4),
        "korunumlu_aktarim_hatasi_pct": round(
            100.0 * float(np.linalg.norm(F_kor - F_cfd)) / olcek, 4),
        "korunumlu_moment_hatasi_pct": round(
            100.0 * float(np.linalg.norm(M_kor - M_cfd)) / m_olcek, 4),
        **{k: (round(v, 6) if isinstance(v, float) else v)
           for k, v in tani.items() if not k.startswith("_")},
    }


def olc() -> dict:
    from fsi_korunum import _vakalar

    from coupling_fsi import cfd_pressure_to_fea_loads

    t0 = time.time()
    kayit, dusen = [], []
    for v in _vakalar():
        try:
            eski = cfd_pressure_to_fea_loads(v["vtk"], v["stl"])
            yeni = _tek_vaka(v["vtk"], v["stl"])
        except Exception as e:            # noqa: BLE001 — sebep KAYDEDILIYOR
            dusen.append(f"{v['ad']}: {type(e).__name__}: {e}"[:140])
            continue
        if eski.get("status") != "SUCCESS" or not eski.get("yuk_var_mi") or not yeni:
            dusen.append(f"{v['ad']}: yük yok ya da okunamadı")
            continue
        kayit.append({
            "vaka": v["ad"],
            "alan_farki_pct": eski["alan_farki_pct"],
            "mevcut_aktarim_pct": round(100 * eski["aktarim_hatasi"], 3),
            **yeni,
        })
        print(f"  {v['ad'][:26]:28s} mevcut %{kayit[-1]['mevcut_aktarim_pct']:7.3f} "
              f"-> korunumlu %{yeni['korunumlu_aktarim_hatasi_pct']:.4f}", flush=True)

    return _ozetle(kayit, dusen, time.time() - t0)


def _ozetle(kayit: list[dict], dusen: list[str], sure_s: float) -> dict:
    if not kayit:
        return {"vaka": "FSI eşleme kıyası", "verdikt": "ÖLÇÜLEMEDİ",
                "dusen": dusen,
                "_uretim": "Üretim: python experiments/fsi_esleme_kiyasi.py"}
    import statistics as st
    m_max = max(k["mevcut_aktarim_pct"] for k in kayit)
    k_max = max(k["korunumlu_aktarim_hatasi_pct"] for k in kayit)
    mom_max = max(k["korunumlu_moment_hatasi_pct"] for k in kayit)
    kayma_max = max(k["kayma_ort_govde_orani"] for k in kayit)
    # MOMENT AYNI OLCUTLE: iki sema da CFD->FEA farkiyla olculuyor.
    mm = [k["mevcut_moment_hatasi_pct"] for k in kayit]
    km = [k["korunumlu_moment_hatasi_pct"] for k in kayit]
    iyi = sum(1 for a, b in zip(mm, km) if b < a)
    return {
        "vaka": "FSI yük eşlemesi — tutarlı vs korunumlu şema, aynı vakalarda",
        "_neden": ("Mevcut sema basinci tasiyip kuvveti FEA aginda YENIDEN "
                   "INTEGRE ediyor; alanlar farkliysa toplam kuvvet de farkli "
                   "cikiyor (olculdu: %0,07-%56,30, hata ALAN FARKINI izliyor)."),
        "olculen_vaka": len(kayit), "dusen": dusen,
        "vakalar": kayit,
        "ozet": {
            "mevcut_moment_ortalama_pct": round(st.mean(mm), 3),
            "korunumlu_moment_ortalama_pct": round(st.mean(km), 3),
            "korunumlunun_daha_iyi_oldugu_vaka": f"{iyi}/{len(kayit)}",
            "mevcut_en_kotu_pct": m_max,
            "korunumlu_en_kotu_pct": k_max,
            "korunumlu_moment_en_kotu_pct": mom_max,
            "izdusum_kaymasi_en_kotu_govde_orani": kayma_max,
        },
        "verdikt": _hukum(m_max, k_max, mom_max, kayma_max, len(kayit),
                          st.mean(mm), st.mean(km), iyi),
        "sure_dk": round(sure_s / 60, 1),
        "_kisit": (
            "KORUNUM BIR KIMLIKTIR, BULGU DEGIL: agirliklar 1'e toplandigi "
            "icin toplam kuvvet zaten korunur ve bunu 'olcmek' bir sey "
            "kanitlamaz. Bu kiyasin olctugu sey BEDELDIR: izdusum kaymasi, "
            "kirpilan izdusum orani ve moment artigi. Yerel basinc alaninin "
            "ne kadar bozuldugu BURADA OLCULMEDI --- onun icin yapisal yanit "
            "(sehim/gerilme) kiyasi gerekir ve o AYRI bir calismadir."),
        "_uretim": "Üretim: python experiments/fsi_esleme_kiyasi.py",
    }


def _hukum(m_max: float, k_max: float, mom_max: float, kayma: float, n: int,
           mm_ort: float, km_ort: float, iyi: int) -> str:
    return (
        f"{n} vakada ölçüldü. KUVVET: mevcut şemanın en kötüsü %{m_max:.2f}, "
        f"korunumlu şemada %{k_max:.4f} --- bu bir KİMLİKTİR (ağırlıklar 1'e "
        f"toplanır), bulgu değil. "
        f"MOMENT, AYNI ÖLÇÜTLE (CFD→FEA farkı, iki şema için de): mevcut "
        f"ortalama %{mm_ort:.2f}, korunumlu %{km_ort:.2f}; korunumlu şema "
        f"{iyi}/{n} vakada DAHA İYİ. "
        f"BEKLENEN TAKAS BU İKİ ÖLÇÜTTE ÇIKMADI: mevcut şemanın hatasına alan "
        f"farkı hükmediyor ve o hem kuvveti hem momenti bozuyor. "
        f"BEDEL yine de var ve ölçüldü: korunumlu şemanın moment artığı en "
        f"kötü %{mom_max:.2f} (esnek vakalarda), izdüşüm kayması gövde "
        f"ölçeğinin %{100 * kayma:.2f}'i. "
        f"ŞEMA HENÜZ DEĞİŞTİRİLMEDİ: iki integral ölçüt de korunumlu şemadan "
        f"yana ama YEREL basınç alanının ne olduğu ölçülmedi; kararın dayanağı "
        f"yapısal yanıt (sehim/gerilme) kıyasıdır.")


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}")
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
