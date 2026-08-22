"""FSI yük aktarımında korunum — hangi metrik NEYİ ölçüyor.

Mevcut iki metrik (kuvvet, moment) makine hassasiyetinde çıkıyordu ve bu bir
başarı gibi okunuyordu. Oysa ikisi de FEA yüzü→düğüm dağıtımını ölçer ve
eşit-üçtebir şemasında YAPI GEREĞİ kesindir --- yani ölçülen şey gerçekten
korunmayan adım değildi. Korunmayan adım: basıncın CFD yüzlerinden FEA
yüzlerine EN-YAKIN-KOMŞU ile taşınması.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))


def _yamuk_yuzey(tmp_path: Path, p_degeri, n=4):
    """Basit bir düzlem yama: n×n dörtgen, tek yönlü normal."""
    xs = np.linspace(0.0, 1.0, n + 1)
    pts, polys = [], []
    idx = {}
    for i, x in enumerate(xs):
        for j, y in enumerate(xs):
            idx[(i, j)] = len(pts)
            pts.append((x, y, 0.0))
    for i in range(n):
        for j in range(n):
            polys.append([idx[(i, j)], idx[(i + 1, j)],
                          idx[(i + 1, j + 1)], idx[(i, j + 1)]])
    p = np.full(len(polys), p_degeri, dtype=float) if np.isscalar(p_degeri) \
        else np.asarray(p_degeri, dtype=float)
    satir = ["# vtk DataFile Version 3.0", "t", "ASCII", "DATASET POLYDATA",
             f"POINTS {len(pts)} float"]
    satir += [f"{a} {b} {c}" for a, b, c in pts]
    satir.append(f"POLYGONS {len(polys)} {5 * len(polys)}")
    satir += ["4 " + " ".join(str(k) for k in q) for q in polys]
    satir += [f"CELL_DATA {len(polys)}", "FIELD FieldData 1", f"p 1 {len(polys)} float"]
    satir += [f"{v}" for v in p]
    f = tmp_path / "yuzey.vtk"
    f.write_text("\n".join(satir) + "\n", encoding="utf-8")
    return f


def _stl(tmp_path: Path, n=4):
    import trimesh
    xs = np.linspace(0.0, 1.0, n + 1)
    v, faces = [], []
    idx = {}
    for i, x in enumerate(xs):
        for j, y in enumerate(xs):
            idx[(i, j)] = len(v)
            v.append((x, y, 0.0))
    for i in range(n):
        for j in range(n):
            a, b, c, d = idx[(i, j)], idx[(i + 1, j)], idx[(i + 1, j + 1)], idx[(i, j + 1)]
            faces += [[a, b, c], [a, c, d]]
    m = trimesh.Trimesh(vertices=np.array(v), faces=np.array(faces), process=False)
    f = tmp_path / "yuzey.stl"
    m.export(f)
    return f


def test_SIFIR_yukte_korunum_TANIMSIZ_sifir_degil(tmp_path):
    """Ölçüldü (minihawk_v2): p≡0 olan bir VTK üç metriği de 0.0 yapıyordu ve
    aktarım artığı %0,0 çıkıyordu --- hiçbir veri yokken "kusursuz korunum".

    Kanıt zaten kayıttaydı (`n_loaded_nodes`=0); eksik olan onu OKUYAN yoldu.
    """
    from coupling_fsi import cfd_pressure_to_fea_loads
    r = cfd_pressure_to_fea_loads(str(_yamuk_yuzey(tmp_path, 0.0)),
                                  str(_stl(tmp_path)))
    assert r["status"] == "SUCCESS"
    assert r["yuk_var_mi"] is False
    assert r["conservation_error"] is None
    assert r["moment_conservation_error"] is None
    assert r["arayuz_isi_hatasi"] is None
    assert r["aktarim_hatasi"] is None
    assert "TANIMSIZ" in r["yuk_notu"]
    assert r["n_loaded_nodes"] == 0


def test_YUK_varken_uc_metrik_de_SAYI_donuyor(tmp_path):
    from coupling_fsi import cfd_pressure_to_fea_loads
    r = cfd_pressure_to_fea_loads(str(_yamuk_yuzey(tmp_path, -50.0)),
                                  str(_stl(tmp_path)))
    assert r["yuk_var_mi"] is True
    for k in ("conservation_error", "moment_conservation_error",
              "arayuz_isi_hatasi", "aktarim_hatasi"):
        assert isinstance(r[k], float), k


def test_ARAYUZ_ISI_kuvvet_ve_momentten_GUCLU():
    """x×F, F⊗x'in yalnız ANTİSİMETRİK kısmıdır.

    Bu testin işi cebiri bağlamak: simetrik kısmı bozan bir dağıtım, kuvvet ve
    moment sınavlarını GEÇER ama arayüz işi sınavını GEÇEMEZ. Geçseydi üçüncü
    metriği eklemenin bir anlamı olmazdı.
    """
    rng = np.random.default_rng(7)
    x = rng.normal(size=(6, 3))
    F = rng.normal(size=(6, 3))

    # Simetrik kismi bozan, kuvveti ve momenti KORUYAN bir pertürbasyon:
    # dF_k = eps * x_k  (F -> F + eps*x). Moment degisimi Σ x×(eps x) = 0,
    # kuvvet degisimi eps*Σx — onu telafi etmek icin merkezlenmis x kullan.
    xc = x - x.mean(axis=0)
    F2 = F + 0.3 * xc

    assert np.allclose(F2.sum(axis=0), F.sum(axis=0)), "kuvvet korunmali"
    assert np.allclose(np.cross(x, F2).sum(axis=0), np.cross(x, F).sum(axis=0),
                       atol=1e-9), "moment korunmali"
    T1 = np.einsum("ki,kj->ij", F, x)
    T2 = np.einsum("ki,kj->ij", F2, x)
    assert not np.allclose(T1, T2), (
        "birinci moment tensörü DEĞİŞMELİ — değişmezse üçüncü metrik "
        "kuvvet+momentten fazlasını sınamıyor demektir")


def test_KANIT_yapi_geregi_kesin_olani_KESIN_olarak_olcuyor():
    p = KOK / "fsi_korunum.json"
    if not p.exists():
        pytest.skip("fsi_korunum.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["olculen_vaka"] >= 10, "kanıt çok az vakadan üretilmiş"
    for v in d["vakalar"]:
        for k in ("kuvvet_hatasi", "moment_hatasi", "arayuz_isi_hatasi"):
            assert v[k] <= 1e-12, (
                f"{v['vaka']}: {k}={v[k]:.2e} — bu metrik eşit-üçtebir "
                f"şemasında YAPI GEREĞİ kesin olmalıydı; uygulama teoriden "
                f"sapmış ya da kayan-nokta birikimi zararsız değil")


def test_KANIT_aktarim_artigini_ALAN_farkindan_AYIRIYOR():
    """İki sebep tek sayıya karışırsa hüküm verilemez."""
    p = KOK / "fsi_korunum.json"
    if not p.exists():
        pytest.skip("fsi_korunum.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    temiz = [v for v in d["vakalar"] if v["alan_farki_pct"] <= 0.5]
    assert temiz, "alanı tutan hiç vaka yok — artık saf örneklemeye izole edilemez"
    # Alani tutan vakalarda bile artik SIFIR DEGIL: olculen sey gercek.
    assert max(v["aktarim_hatasi_pct"] for v in temiz) > 0.5, (
        "alanı tutan vakalarda aktarım artığı ölçülemeyecek kadar küçük — "
        "metrik bir şey söylüyor mu?")
    assert "SAF ÖRNEKLEME" in d["verdikt"]


def test_KANIT_sifir_yuklu_vakayi_OLCULEN_saymiyor():
    p = KOK / "fsi_korunum.json"
    if not p.exists():
        pytest.skip("fsi_korunum.json üretilmemiş")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert any("YÜK YOK" in x for x in d["olculemeyen"]), (
        "sıfır-yüklü vaka ölçülemeyenler arasında gerekçesiyle durmalı")
    for v in d["vakalar"]:
        assert v["aktarim_hatasi_pct"] > 0.0 or v["alan_farki_pct"] > 0.0
