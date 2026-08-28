"""İki-hızlı katman ölçeri --- aynı sözleşmeyi paylaşan yollar ayrışıyor mu.

NEDEN VAR. 2026-08-28'de araç yolunda ölçülmüş bir yük kusuru bulundu:
yüzey normalleri YÜZ BAŞINA ters çevriliyordu ve yapıya aerodinamik yükün
dörtte biri uygulanıyordu. Kusurun HAYATTA KALMA sebebi yapısaldı: FSI
sürücüsünün eşleme modülü aynı ölçütü çoktan çürütmüş ve gerekçesini kendi
gövdesine yazmıştı. İki yol yan yana; biri dersi öğrenmiş, öteki hiç
duymamış.

ÖLÇERİN ASIL DEĞERİ KAYITSIZ ADAY TARAMASINDADIR. Bugünkü kusur kayıtlı
bir uygulama DEĞİLDİ --- ham bir maske atamasıydı. Yalnız kayıtlı
uygulamaları sınayan bir ölçer onu göremezdi.

BU DOSYA ÖLÇÜTÜN İKİ TARAFINI DA BAĞLAR. Aday dedektörü ilk yazımda fazla
genişti ve üç yanlış pozitif üretti (döngüde dizi doldurma, düğüm normali
toplama, birim vektör kurma). Kusurun imzası DOLDURMA değil İŞARET
ÇEVİRMEDİR; ölçüt işleme bağlandı.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))


# ─────────────────────────── aday dedektörü ────────────────────────────

def _tara(src: str):
    from iki_hiz import _normal_maskeli_atama
    return _normal_maskeli_atama(ast.parse(src))


def test_ADAY_ESKI_KUSURLU_KODU_YAKALIYOR():
    """POZİTİF KONTROL --- gerçek kusurun sözdizimi, birebir."""
    src = (
        "def _map(P, tris, normals, centers):\n"
        "    cg = P.mean(axis=0)\n"
        "    flip = np.einsum('ij,ij->i', normals, centers - cg) < 0\n"
        "    normals[flip] *= -1\n"
        "    return normals\n")
    assert _tara(src), "asıl kusur yakalanmıyor — ölçer bir şey sınamıyor"


def test_ADAY_IKINCI_YAZILISI_DA_YAKALIYOR():
    """Aynı kusur `= -normals[...]` diye de yazılabilir; ölçüt SÖZDİZİMİNE
    değil İŞLEME bağlı olmalı."""
    src = ("def _m(normals, flip):\n"
           "    normals[flip] = -normals[flip]\n")
    assert _tara(src)


def test_ADAY_MESRU_DOLDURMAYI_YAKALAMIYOR():
    """YANLIŞ-POZİTİF TARAFI. Bu üç desen depoda GERÇEKTEN var ve üçü de
    meşru; ilk ölçütüm üçünü de suçlamıştı."""
    dongude_doldurma = (
        "def _f(normals, polys, points):\n"
        "    for idx, poly in enumerate(polys):\n"
        "        normals[idx] = nrm / 2.0\n")
    dugum_toplama = (
        "def _g(normals, faces):\n"
        "    for i, face in enumerate(faces):\n"
        "        for nid in face:\n"
        "            normals[nid] += fn\n")
    birim_vektor = (
        "def _h(ext):\n"
        "    normal = [0.0, 0.0, 0.0]\n"
        "    normal[int(np.argmin(ext))] = 1.0\n")
    for ad, src in (("döngüde doldurma", dongude_doldurma),
                    ("düğüm toplama", dugum_toplama),
                    ("birim vektör", birim_vektor)):
        assert _tara(src) == [], f"meşru desen suçlandı: {ad}"


def test_ADAY_BILESEN_YAZIMINI_YAKALAMIYOR():
    """`n[:, 2] = -n[:, 2]` bir bileşen işlemidir, yüz-başına karar
    değil."""
    assert _tara("def _f(normals):\n    normals[:, 2] = -normals[:, 2]\n") == []


def test_ADAY_ISARETSIZ_MASKELI_ATAMAYI_YAKALAMIYOR():
    """Maske VAR ama işaret çevirme YOK --- ikisi ayrı ayrı masum."""
    assert _tara("def _f(normals, m):\n    normals[m] = 0.0\n") == []


# ─────────────────────────── sözleşme sınavı ───────────────────────────

def test_SOZLESME_BUTUNSEL_OLMAYANI_REDDEDIYOR():
    """Sınavın kendisi sınanır: bir ALT KÜME çeviren sahte uygulama
    reddedilmeli, yoksa 'hepsi geçti' hiçbir şey demez."""
    from iki_hiz import _sozlesme_butunsel

    def kotu(P, tris, n, A, c):
        cg = P.mean(axis=0)
        yeni = n.copy()
        yeni[np.einsum("ij,ij->i", n, c - cg) < 0] *= -1
        return yeni

    r = _sozlesme_butunsel(kotu)
    assert not r["tutuyor"], "sahte uygulama sözleşmeyi geçti"
    assert any("BÜTÜNSEL değil" in k for k in r["kusurlar"])


def test_SOZLESME_BUTUNSEL_OLANI_GECIRIYOR():
    from iki_hiz import _sozlesme_butunsel
    assert _sozlesme_butunsel(lambda P, t, n, A, c: n)["tutuyor"]
    assert _sozlesme_butunsel(lambda P, t, n, A, c: -n)["tutuyor"]


def test_SINAV_DISBUKEY_OLMAYAN_GOVDE_ICERIYOR():
    """KRİTİK: dışbükey bir kutuda eski ölçüt ZATEN doğrudur, yani sınav
    yalnız kutu kullansaydı kusuru GÖREMEZDİ. İki ayrık küp şart."""
    from iki_hiz import _iki_ayrik_kup
    P, tris, n, A, c = _iki_ayrik_kup()
    cg = P.mean(axis=0)
    assert int((np.einsum("ij,ij->i", n, c - cg) < 0).sum()) > 0, (
        "sınav geometrisi eski ölçütü kırmıyor — kusuru gösteremez")


def test_KAYITLI_UYGULAMALARIN_HEPSI_TUTUYOR():
    import iki_hiz
    o = iki_hiz.olc()
    ayrisan = [a for s in o["sozlesmeler"] for a in s["ayrisan"]]
    assert ayrisan == [], f"sözleşmeyi tutmayan uygulama: {ayrisan}"


def test_DEPODA_KAYITSIZ_ADAY_YOK():
    import iki_hiz
    aday = iki_hiz.olc()["kayitsiz_adaylar"]
    assert aday == [], f"kayıtsız aday: {aday}"


# ───────────────────────────── tüketici bağı ───────────────────────────

def test_OLCER_SAGLIGA_BAGLI():
    """Öksüz bir ölçer, ölçtüğü kusurun kendisi olurdu."""
    import saglik
    assert any(ad == "iki_hiz" for ad, _, _ in saglik.OLCERLER), (
        "iki_hiz saglik.py'ye kayıtlı değil")


def test_SAGLIK_HUKMU_OLCER_SAYISINI_SAYIYOR():
    """Hüküm sayıyı ELLE yazıyordu ve altıncı ölçer eklenince yanlış oldu.
    Sayı sayılır, yazılmaz.

    ÖLÇÜT AÇIKLAMA SATIRINI SUÇLAMAMALI: `saglik.py` eski metni bir
    yorumda BELGELİYOR ve ilk ölçütüm ("kaynakta 'Beş ölçer' geçmesin")
    tam onu yakaladı. Bu depoda aynı hata birkaç kez yapıldı; ölçüt
    yorumları değil DİZGİLERİ görmeli, o yüzden AST kullanılıyor.
    """
    import ast as _a

    import saglik
    agac = _a.parse((KOK / "saglik.py").read_text(encoding="utf-8"))
    for d in _a.walk(agac):
        if isinstance(d, _a.Constant) and isinstance(d.value, str):
            assert "Beş ölçer" not in d.value, (
                "ölçer sayısı bir dizgide elle yazılı")
    assert len(saglik.OLCERLER) >= 6
    assert "len(OLCERLER)" in (KOK / "saglik.py").read_text(encoding="utf-8")
