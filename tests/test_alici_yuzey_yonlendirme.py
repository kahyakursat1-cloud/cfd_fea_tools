"""Yüzey normalleri TOPLUCA yönlendirilir --- yüz başına DEĞİL.

BU BİR ÜRETİM KUSURUYDU VE SESSİZDİ. `vehicle_fea._map_pressure_to_tet`
alıcı yüzeyin normallerini yüz başına şu ölçütle çeviriyordu:

    cg = P.mean(axis=0)
    flip = np.einsum("ij,ij->i", normals, centers - cg) < 0
    normals[flip] *= -1

Ölçüt yalnız YILDIZ-ŞEKİLLİ cisimlerde doğrudur. İnce/uzun bir gövdede
merkez--cg vektörüne veter ya da açıklık yönü hükmeder: hücum kenarında
merkez--cg ~ +x iken dış normal ~ -x'tir ve ölçüt onu ters çevirir.

ÖLÇÜLDÜ (gmsh'in kendi tutarlı sarımından başlayarak kaç yüzü bozduğu):
roket %0,5 · çiftkuyruk %18,7 · gripen %29,8 · A320 %42,6.

BEDELİ TOPLAM YÜKTE: `ciftkuyruk_kucuk`, aynı basınç alanı ve aynı ağ ---
sarım normalleriyle |F| = 15,58 N (çözücünün sürüklemesi 15,653 N, %0,9),
centroid ölçütüyle |F| = 4,65 N. Yapıya aerodinamik yükün DÖRTTE BİRİ
uygulanıyordu.

HİÇBİR MEVCUT KAPI ÖTMEDİ: ağ kaliteliydi, çözüm yakınsamıştı, `.inp`
geçerliydi, gerilme alanı düzgündü. Çünkü hiçbiri UYGULANAN YÜKÜ bağımsız
bir sayıyla karşılaştırmıyordu. Bu dosya hem yönlendirmeyi hem o kapıyı
bağlar.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))


def _kup(ters: bool = False):
    """Birim küp: 12 üçgen, sarımı DIŞA (ters=True ise içe)."""
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
    tris = np.array([
        [0, 2, 1], [0, 3, 2],      # z-
        [4, 5, 6], [4, 6, 7],      # z+
        [0, 1, 5], [0, 5, 4],      # y-
        [2, 3, 7], [2, 7, 6],      # y+
        [1, 2, 6], [1, 6, 5],      # x+
        [0, 4, 7], [0, 7, 3],      # x-
    ])
    if ters:
        tris = tris[:, ::-1]
    v1 = P[tris[:, 1]] - P[tris[:, 0]]
    v2 = P[tris[:, 2]] - P[tris[:, 0]]
    cr = np.cross(v1, v2)
    A = 0.5 * np.linalg.norm(cr, axis=1)
    n = cr / (2 * A[:, None] + 1e-30)
    c = P[tris].mean(axis=1)
    return P, tris, n, A, c


def test_DISA_SARIMDA_HIC_DOKUNMUYOR():
    from vehicle_fea import _disa_yonlendir
    P, tris, n, A, c = _kup()
    yeni, yon = _disa_yonlendir(P, tris, n.copy(), A, c)
    assert np.allclose(yeni, n), "dışa sarımda normaller değişmemeli"
    assert "dışa" in yon


def test_ICE_SARIMDA_TUMU_CEVRILIYOR():
    from vehicle_fea import _disa_yonlendir
    P, tris, n, A, c = _kup(ters=True)
    yeni, yon = _disa_yonlendir(P, tris, n.copy(), A, c)
    assert np.allclose(yeni, -n), "içe sarımda TÜMÜ çevrilmeli"
    assert "çevrildi" in yon


def test_YONLENDIRME_KISMI_OLMUYOR():
    """MEKANİZMANIN KENDİSİ. Çıktı ya girdinin aynısı ya da tam tersi
    olmalı; bir alt kümeyi çevirmek yüzeyin tutarlılığını bozar ve asıl
    kusur buydu."""
    from vehicle_fea import _disa_yonlendir
    for ters in (False, True):
        P, tris, n, A, c = _kup(ters=ters)
        yeni, _ = _disa_yonlendir(P, tris, n.copy(), A, c)
        ayni = np.allclose(yeni, n)
        tersi = np.allclose(yeni, -n)
        assert ayni or tersi, "normallerin bir ALT KÜMESİ çevrilmiş"


def test_DISBUKEY_OLMAYAN_GOVDEDE_ESKI_OLCUT_BOZUYOR():
    """KUSURUN YENİDEN ÜRETİMİ --- ve önce yanlış kurdum.

    İlk denemem ince bir LEVHAYDI ve eski ölçütü hiç kırmadı: levha
    dışbükeydir, dışbükey bir cisimde ``normal, ağırlık merkezinden dışarı
    baksın'' ölçütü HER ZAMAN doğrudur. Kusur DIŞBÜKEY OLMAYAN gövdede
    doğuyor --- gerçek uçaklarda kanat/kuyruk/gövde birleşimleri.

    En yalın üretim: iki AYRIK küp. Ağırlık merkezi aradaki boşluğa düşer,
    dolayısıyla sol küpün +x yüzünün dış normali merkeze DOĞRU bakar ve
    eski ölçüt onu ters çevirir.
    """
    from vehicle_fea import _disa_yonlendir
    P0, tris0, _, _, _ = _kup()
    P = np.vstack([P0, P0 + np.array([3.0, 0, 0])])
    tris = np.vstack([tris0, tris0 + len(P0)])
    v1, v2 = P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]]
    cr = np.cross(v1, v2)
    A = 0.5 * np.linalg.norm(cr, axis=1)
    n = cr / (2 * A[:, None] + 1e-30)
    c = P[tris].mean(axis=1)

    cg = P.mean(axis=0)
    eski_cevirir = int((np.einsum("ij,ij->i", n, c - cg) < 0).sum())
    assert eski_cevirir > 0, (
        "bu geometri eski ölçütü kırmalı, yoksa test bir şey sınamıyor")

    yeni, _ = _disa_yonlendir(P, tris, n.copy(), A, c)
    assert np.allclose(yeni, n), (
        "yeni ölçüt dışbükey olmayan gövdede de dokunmamalı")


def test_ESKI_CENTROID_OLCUTU_GERI_GELMIYOR():
    """Desen METİNDE değil AĞAÇTA aranır. `_map_pressure_to_tet` içinde
    normallere maskeyle atama yapan bir satır olmamalı."""
    agac = ast.parse((KOK / "vehicle_fea.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef)
              and n.name == "_map_pressure_to_tet")
    for d in ast.walk(fn):
        if not isinstance(d, ast.AugAssign):
            continue
        hedef = ast.unparse(d.target)
        assert "normals[" not in hedef, (
            f"normallere yüz-başına atama geri gelmiş: {hedef}")


# ───────────────────────────── uygulanan yük kapısı ─────────────────────

def _g(F, drag, pay):
    from vehicle_fea import _uygulanan_yuk_denetimi
    return _uygulanan_yuk_denetimi(F, {"drag_N": drag}, pay)


def test_KAPI_BUGUNKU_KUSURU_YAKALIYOR():
    """Ölçütün yanlış-negatif tarafı GERÇEK sayılarla. Kusurlu aktarımın
    ürettiği 3,22 N, 15,653 N çapaya karşı reddedilmeli."""
    assert _g([3.2248, -0.19, 3.35], 15.653, 3.0)["hukum"] == "TUTMUYOR"


def test_KAPI_DUZELTILMIS_DEGERI_GECIRIYOR():
    """Yanlış-pozitif tarafı: doğru aktarım (15,44 N) geçmeli."""
    assert _g([15.4385, 0.05, 2.09], 15.653, 3.0)["hukum"] == "TUTUYOR"


def test_VISKOZ_PAYI_BILINMIYORSA_HUKUM_YOK():
    """'Bilinmiyor' ile 'tutmuyor' AYRI. İnce bir roket gövdesinde
    sürüklemenin %80'i sürtünme olabilir ve basınç-yalnız aktarımın o
    kadar düşük kalması DOĞRU davranıştır (ölçüldü: clean_rocket -%81,5).
    Kaba bir banda vurup 'tutmuyor' demek doğru sonucu kusurlu
    gösterirdi."""
    r = _g([0.08, -0.073, 0.084], 0.432, None)
    assert r["hukum"] == "KARAR YOK"
    assert r["sapma_pct"] < -50


def test_FIZIKSEL_SINIRLAR_PAYDAN_BAGIMSIZ():
    """Viskoz sürükleme daima pozitiftir; basınç payı toplamı AŞAMAZ ve
    işaret değiştiremez. Bu iki sınır viskoz payı bilinmese de hüküm
    verir."""
    assert _g([20.0, 0, 0], 15.653, None)["hukum"] == "TUTMUYOR"
    assert _g([-5.0, 0, 0], 15.653, None)["hukum"] == "TUTMUYOR"


def test_CAPA_YOKSA_OLCULMEDI_DIYOR():
    r = _g([1, 2, 3], None, None)
    assert r["olculdu"] is False and "çapa" in r["neden"]


def test_URETIM_YOLLARININ_HEPSI_KAPIYI_CAGIRIYOR():
    """Bu deponun BASKIN KUSURU. Sehim hükmü veren her statik yol
    uygulanan-yük kapısını da çağırmalı; ölçüt sayıya değil MEKANİZMAYA
    bağlanır."""
    agac = ast.parse((KOK / "vehicle_fea.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef)
              and n.name == "run_structural_check")
    cagri = [getattr(c.func, "id", getattr(c.func, "attr", ""))
             for c in ast.walk(fn) if isinstance(c, ast.Call)]
    assert (cagri.count("_uygulanan_yuk_denetimi")
            == cagri.count("_mechanism_check")), (
        f"_mechanism_check {cagri.count('_mechanism_check')} yerde, "
        f"_uygulanan_yuk_denetimi {cagri.count('_uygulanan_yuk_denetimi')} "
        "yerde")
