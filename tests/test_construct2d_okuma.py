"""`construct2d_bridge.oku_sonuc` kapıları — çözücü ÇALIŞTIRMADAN.

NEDEN BU DOSYA VAR. Kapsam ölçümü (`experiments/arayuz_kopru_kapsami.py`)
raporun ``köprüler birim testiyle değil çapa koşularıyla sınanır'' cümlesini
sınadı ve köprü katmanında %29,0'ının ne ekran ne çözücü istediğini ölçtü ---
yani cümle o katman için fazla cömertti. En büyük blok bu modülde ve içinde
üç GERÇEK KARAR var:

  1. NaN/inf kapısı --- `float('nan') <= x` daima False olduğu için kirlenmiş
     bir çözüm aşağıdaki her karşılaştırmadan SESSİZCE geçerdi.
  2. Kuyruk ortalaması --- son satır değil; çözüm salınıyorsa tek anlık değer
     salınımın neresinde durulduğuna bağlıdır.
  3. Kord uyuşmazlığı --- çağıranın kordu mesh'inkinden farklıysa referans
     alan da Reynolds da kayar (ölçülmüş: 4 kat).

Üçü de hüküm üretiyordu ve hiçbiri sınanmamıştı.

İLK KOŞUSUNDA BİR KUSUR BULDU. NaN kapısı `nan` yazan bir forces.dat'ta HİÇ
tetiklenmiyordu: sayı deseni yalnız rakamla başlayan belirteci alıyor, `nan`
belirtecini SESSİZCE ATLIYOR ve sütunları bir kaydırıyordu. Sonuç, makul
görünen ama yanlış bir sayı --- kapı vardı, üretim yolu ona ulaşmıyordu.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from construct2d_bridge import oku_sonuc  # noqa: E402

# GERCEK forces.dat BICIMI (OpenFOAM 11):
#   time ((p_fx p_fy p_fz) (v_fx v_fy v_fz)) ((p_mx …) (v_mx …))
# Duzlestirilince nums[1..3]=basinc kuvveti, nums[4..6]=viskoz kuvvet.
# Fikstur BU bicimi taklit eder --- ilk surum duz sutunlar yaziyordu, yani
# testler kodu gercek girdisiyle surmuyordu.
BASLIK = "# Forces\n# Time forces(pressure viscous) moment(pressure viscous)\n"

FOAM_BAS = ("FoamFile\n{{\n version 2.0;\n format ascii;\n"
            " class {sinif};\n object {nesne};\n}}\n")

Q = 0.5 * 1.225 * 50.0 ** 2      # varsayilan rho, V


def _satir(t: float, fx: float, fy: float, viskoz: float = 0.0) -> str:
    """Basinc kuvveti (fx,fy,0), viskoz (viskoz,0,0); moment sifir."""
    return f"{t}\t(({fx} {fy} 0) ({viskoz} 0 0)) ((0 0 0) (0 0 0))"


def _polymesh(case: Path, kord: float, span: float = 0.1) -> None:
    """En kucuk GECERLI polyMesh.

    `FoamFile` basligi SART: `_foam_govde` govdeyi ondan sonra ariyor ve
    basliksiz dosyada olcum sessizce dusuyor. Ilk fikstur boyleydi ve kord
    testleri kordu HIC olcmemis oluyordu --- fikstur eksikligi testi yesil
    degil YANLIS yapar.
    """
    pm = case / "constant" / "polyMesh"
    pm.mkdir(parents=True)
    (pm / "boundary").write_text(
        FOAM_BAS.format(sinif="polyBoundaryMesh", nesne="boundary")
        + "1\n(\nairfoil\n{\n type wall;\n nFaces 1;\n startFace 0;\n}\n)\n",
        encoding="utf-8")
    (pm / "faces").write_text(
        FOAM_BAS.format(sinif="faceList", nesne="faces")
        + "1\n(\n4(0 1 2 3)\n)\n", encoding="utf-8")
    (pm / "points").write_text(
        FOAM_BAS.format(sinif="vectorField", nesne="points")
        + "4\n(\n(0 0 0)\n"
        + f"({kord} 0 0)\n({kord} 0 {span})\n(0 0 {span})\n)\n",
        encoding="utf-8")


def _kur(tmp: Path, satirlar: list[str], *, kord: float | None = None,
         ad: str = "case") -> Path:
    case = tmp / ad
    d = case / "postProcessing" / "forces" / "0"
    d.mkdir(parents=True)
    (d / "forces.dat").write_text(BASLIK + "\n".join(satirlar) + "\n",
                                  encoding="utf-8")
    if kord is not None:
        _polymesh(case, kord)
    return case


def _temiz(n: int = 10, fx: float = 1.0, fy: float = 0.5) -> list[str]:
    return [_satir(i, fx, fy) for i in range(1, n + 1)]


def test_FIKSTUR_gercek_bicimi_veriyor(tmp_path):
    """Fikstür yanlışsa aşağıdaki her test yanlış şeyi sınar.

    Bunu ayrı bir test yapmak gerekti çünkü ilk sürümde tam olarak bu oldu:
    düz sütunlu sahte bir biçim yazıldı ve kod hiç sürülmedi.
    """
    r = oku_sonuc(_kur(tmp_path, _temiz(), kord=0.5))
    assert r.get("kord_olculen") == pytest.approx(0.5), \
        "polyMesh okunamıyor — fikstür geçersiz, testler kordu ölçmüyor"
    assert r["span_olculen"] == pytest.approx(0.1)
    assert r["Cd"] == pytest.approx(1.0 / (Q * 0.5 * 0.1), rel=1e-3)


def test_NAN_kapisi_kirlenmis_cozumu_gecirmez(tmp_path):
    """En sinsi hâl: NaN her karşılaştırmadan sessizce geçer."""
    case = _kur(tmp_path, _temiz(4) + [_satir(5, float("nan"), 0.5)], kord=1.0)
    r = oku_sonuc(case)
    assert r["status"] == "FAILED" and r["step"] == "sayisal"
    assert "NaN/inf" in r["hata"]
    # HUKUM SEBEBIYLE BIRLIKTE: okuyan kisi nereye bakacagini bilmeli
    assert "sigFpe" in r["hata"]


@pytest.mark.parametrize("belirtec", ["nan", "-nan", "inf", "-inf"])
def test_TUM_kirlenme_belirtecleri_yakalanir(tmp_path, belirtec):
    """OpenFOAM dördünü de yazabilir; deseni yalnız `nan` için düzeltmek
    kapıyı yarım açık bırakırdı."""
    satir = f"5\t(({belirtec} 0.5 0) (0 0 0)) ((0 0 0) (0 0 0))"
    case = _kur(tmp_path, _temiz(4) + [satir], kord=1.0,
                ad="c_" + belirtec.replace("-", "m"))
    assert oku_sonuc(case)["status"] == "FAILED"


def test_TEMIZ_kosu_kapiya_TAKILMAZ(tmp_path):
    """Yanlış-pozitif kapısı: kapı sağlam sayıyı reddetmemeli."""
    r = oku_sonuc(_kur(tmp_path, _temiz(), kord=1.0))
    assert r["status"] in ("SUCCESS", "YAKINSAMADI")
    assert math.isfinite(r["Cd"]) and math.isfinite(r["Cl"])


def test_VISKOZ_bilesen_kuvvete_KATILIR(tmp_path):
    """Fx = basınç_x + viskoz_x. Viskoz terim düşerse sürükleme eksik çıkar
    ve bu sessizdir --- sayı yine makul görünür."""
    case = _kur(tmp_path, [_satir(i, 1.0, 0.0, viskoz=0.25)
                           for i in range(1, 11)], kord=1.0)
    assert oku_sonuc(case)["Cd"] == pytest.approx(1.25 / (Q * 0.1), rel=1e-3)


def test_KUYRUK_ORTALAMASI_son_satir_degil(tmp_path):
    """Salınan bir seride son satır ile kuyruk ortalaması FARKLI olmalı;
    aynı çıkıyorsa kural fiilen 'son satır'dır."""
    satirlar = [_satir(i, 1.0, 0.0) for i in range(1, 11)]
    satirlar += [_satir(11, 2.0, 0.0), _satir(12, 4.0, 0.0),
                 _satir(13, 2.0, 0.0), _satir(14, 4.0, 0.0)]
    r = oku_sonuc(_kur(tmp_path, satirlar, kord=1.0))
    son_satir_cd = 4.0 / (Q * 0.1)
    assert r["Cd"] != pytest.approx(son_satir_cd, rel=1e-6), \
        "kuyruk ortalaması son satıra eşit — kural uygulanmıyor"
    # BAND SALINIMI SAYIYA CEVIRIR, gizlemez
    assert r["Cd_band"] > 0
    assert r["kuyruk_ornek"] == max(3, len(satirlar) // 5)


def test_SABIT_seride_band_SIFIR(tmp_path):
    """Band bir belirsizlik ölçüsüdür: salınım yoksa sıfır olmalı, yoksa
    her koşuya sahte bir belirsizlik eklenirdi."""
    r = oku_sonuc(_kur(tmp_path, _temiz(), kord=1.0))
    assert r["Cd_band"] == 0 and r["Cl_band"] == 0


def test_KORD_UYUSMAZLIGI_sessiz_kalmaz(tmp_path):
    """Çağıran 1.0 diyor, mesh 0.25 ölçüyor: referans alan ve Re kayar."""
    r = oku_sonuc(_kur(tmp_path, _temiz(), kord=0.25), chord=1.0)
    assert "kord_uyusmazligi" in r
    assert r["kord_olculen"] == pytest.approx(0.25)
    # REFERANS ALAN OLCULENDEN alinmali, cagirandan degil
    assert r["S_ref"] == pytest.approx(0.25 * 0.1)
    assert r["Re_efektif"] == pytest.approx(50.0 * 0.25 / 1.48e-5, rel=1e-3)


def test_KORD_UYUSUYORSA_uyari_YOK(tmp_path):
    """Yanlış-pozitif kapısı: eşleşen kord uyarı üretmemeli."""
    assert "kord_uyusmazligi" not in oku_sonuc(
        _kur(tmp_path, _temiz(), kord=1.0), chord=1.0)


def test_KORD_OLCULEMEZSE_gerekce_yazilir(tmp_path):
    """Ölçüm düşerse koşu düşmez ama sebep GİZLENMEZ --- sessiz-yutma değil."""
    r = oku_sonuc(_kur(tmp_path, _temiz()), chord=1.0)
    assert "kord_olcum_hatasi" in r, "ölçüm düştü ama gerekçe yazılmadı"
    assert "kord_uyusmazligi" not in r, \
        "ölçüm düşmüşken uyuşmazlık hükmü verilemez"


def test_FORCES_yoksa_ve_BOSSA_ayri_ayri_soylenir(tmp_path):
    bos = tmp_path / "bos"
    (bos / "postProcessing" / "forces" / "0").mkdir(parents=True)
    r1 = oku_sonuc(bos)
    assert r1["status"] == "FAILED" and r1["step"] == "forces"
    r2 = oku_sonuc(_kur(tmp_path, [], ad="bos2"))
    assert r2["status"] == "FAILED" and "bos" in r2.get("hata", "")


def test_TANINMAYAN_BICIM_sessizce_gecmez(tmp_path):
    """Sütun sayısı beklenenden azsa eskiden IndexError ile çökerdi ya da
    yanlış sütunu okurdu; artık gerekçeli ret verir."""
    r = oku_sonuc(_kur(tmp_path, ["5 1.0 0.5"], kord=1.0))
    assert r["status"] == "FAILED" and r["step"] == "sayisal"
    assert "bicim" in r["hata"]
