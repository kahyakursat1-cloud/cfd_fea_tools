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


# ──────────────────── sözleşme 2: yük aktarımı korunumlu ────────────────

def test_KORUNUM_SOZLESMESI_ESKI_SEMAYI_REDDEDIYOR():
    """NEGATİF KONTROL --- bu olmadan '5/5 geçti' hiçbir şey demez.

    Eski şema basıncı taşıyıp kuvveti ALICI yüzeyde yeniden integre
    ediyordu; alanlar farklıysa toplam da farklı çıkar. Sözleşme bunu
    reddetmeli.
    """
    from scipy.spatial import cKDTree

    from iki_hiz import _sozlesme_korunumlu

    def eski_sema(dF, cfd_c, P, tris, c):
        # alici ucgenin KENDI alani/normaliyle yeniden integrasyon:
        # en yakin CFD yuzunun "basincini" al, alici alanla carp
        v1, v2 = P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]]
        cr = np.cross(v1, v2)
        A = 0.5 * np.linalg.norm(cr, axis=1)
        _, en_yakin = cKDTree(cfd_c).query(c, k=1)
        dF_fea = dF[en_yakin] * (A / A.mean())[:, None]
        F = np.zeros_like(P, dtype=float)
        for k in range(3):
            np.add.at(F, tris[:, k], dF_fea / 3.0)
        return F

    r = _sozlesme_korunumlu(eski_sema)
    assert not r["tutuyor"], "eski şema korunum sözleşmesini geçti"
    assert any("KORUNMUYOR" in k for k in r["kusurlar"])


def test_KORUNUM_SOZLESMESI_ORTUSMEYEN_YUZEYDE_SINANIYOR():
    """Sınavın kendisi: CFD yüzleri alıcı üçgenlerle BİREBİR örtüşürse
    korunum bedavaya sağlanır ve sınav hiçbir şey sınamaz. Sınav noktaları
    kaydırılmış olmalı."""
    import inspect

    import iki_hiz
    src = inspect.getsource(iki_hiz._sozlesme_korunumlu)
    assert "rng.normal" in src and "cfd_c = c +" in src, (
        "sınav noktaları kaydırılmıyor — korunum bedavaya sağlanır")


def test_T6_SEKIL_BIRLIGE_TOPLANIYOR():
    """Korunum T6'da da KİMLİKTİR --- şekil fonksiyonları 1'e toplanır."""
    from vehicle_fea import t6_sekil
    rng = np.random.default_rng(0)
    N = t6_sekil(rng.dirichlet([1, 1, 1], size=3000))
    assert float(np.abs(N.sum(axis=1) - 1).max()) < 1e-12


def test_T6_UNIFORM_BASINCTA_ESKI_KURALA_INIYOR():
    """T6 dağıtımı eski kuralın GENELLEMESİ olmalı: üniform basınçta köşe
    0, kenar-orta 1/3. Aksi halde çember çapasının doğruladığı davranış
    (%1,3) bozulurdu."""
    from vehicle_fea import t6_sekil
    rng = np.random.default_rng(1)
    N = t6_sekil(rng.dirichlet([1, 1, 1], size=200000)).mean(axis=0)
    assert np.abs(N[:3]).max() < 5e-3, f"köşe payı sıfır değil: {N[:3]}"
    assert np.abs(N[3:] - 1 / 3).max() < 5e-3, f"kenar-orta ≠ 1/3: {N[3:]}"


def test_URETIM_YOLU_KORUNUM_ARTIGINI_OLCUYOR():
    """Korunum bir İDDİA değil ÖLÇÜM olmalı: iki eşleme yolu da artığı
    hesaplayıp döndürmeli."""
    import ast
    agac = ast.parse((KOK / "vehicle_fea.py").read_text(encoding="utf-8"))
    for ad in ("_map_pressure_to_tet", "_map_pressure_to_shell"):
        fn = next(n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef)
                  and n.name == ad)
        assert "korunum_artigi" in ast.unparse(fn), f"{ad} artığı ölçmüyor"


def test_KORUNUM_SINAVI_ALANLARI_FARKLI_YUZEY_ICERIYOR():
    """SINAVIN KENDİ YETERLİLİĞİ. Küpün on iki üçgeni EŞİT alanlıdır ve
    alan-farkı etkisi orada yok olur --- eski (korunumsuz) şema küpte
    sınavı GEÇMİŞTİ. Sınav kusuru işletmelidir.

    (Aynı oturumda ikinci kez: yönlendirme sınavında da dışbükey bir kutu
    seçilmiş ve eski ölçütü kırmamıştı.)
    """
    from iki_hiz import _bozuk_alanli, _kup
    _, _, _, A_kup, _ = _kup()
    _, _, _, A_bozuk, _ = _bozuk_alanli()
    assert np.ptp(A_kup) < 1e-12, "küp artık eşit-alanlı değil mi?"
    assert A_bozuk.max() / A_bozuk.min() > 3.0, (
        "sınav yüzeyinin alanları yeterince dağılmamış — alan-farkı "
        "kusurunu işletemez")
