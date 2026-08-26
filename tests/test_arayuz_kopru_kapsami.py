"""Kapsam sınıflandırıcısının kendisi sınanır — ölçüt iddiaya uymalı.

Bu betik bir İDDİAYI sınıyor: raporun ``arayüz ve köprüler birim testiyle
değil çapa koşularıyla sınanır'' cümlesi doğru mu? Öyleyse ölçütün kendisi
denetlenmeden hükmü kabul edilemez --- çünkü ölçüt iki yönde de bozulabilir
ve ikisi de sessizdir:

  ÇOK DAR  : Qt satırlarını ``sınanabilir'' sayar -> oran şişer -> ``rapor
             cömert'' hükmü HAKSIZ yere tetiklenir.
  ÇOK GENİŞ: saf mantığı ``dış bağımlı'' sayar -> oran düşer -> rapor
             KENDİ savunmasını kendisi doğrulamış olur.

İkinci yön daha tehlikelidir çünkü rahatlatıcıdır. Aşağıdaki testler ölçütü
iki yönden de sıkıştırır.

GERÇEK KUSURLAR (bu testler yazılırken bulundu ve düzeltildi):
  1. `QT_ADI` deseni dosyaya bozuk yazıldı: `\\b` kaçışı geriye-silme
     karakterine (0x08) dönüştü ve desen HİÇBİR ŞEYE uymuyordu. Görünürde
     doğru duruyordu; `grep` kontrol karakterini göstermiyor.
  2. Sınıflandırma satır-yereldi, yani dış çağrıyı SARAN fonksiyonun gövdesi
     ``sınanabilir'' sayılıyordu (`_set_naca_profile`, `tablo = g.stdout`).
     Bu, ölçümü tam da ölçenin işine gelen yöne kaydırıyordu.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "experiments"))

import arayuz_kopru_kapsami as A  # noqa: E402


def _siniflandir(kaynak: str) -> dict[int, str]:
    """Betiğin kovalama kuralını kaynak metne uygula (satır -> kova)."""
    from karar_katmani_kapsami import IO_DESEN, SAVUNMA_DESEN
    satirlar = kaynak.splitlines()
    qt = A._qt_satirlari(kaynak)
    yok = A._ithal_edilemeyenler(kaynak)
    yd = (re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(yok))) + r")\b")
          if yok else None)
    yayilan = A._dis_bagimli_satirlar(kaynak, yd)
    out = {}
    for i, m in enumerate(satirlar, 1):
        if not m.strip() or m.lstrip().startswith("#"):
            continue
        if IO_DESEN.match(m):
            out[i] = "io"
        elif SAVUNMA_DESEN.match(m):
            out[i] = "savunma"
        elif (i in qt or i in yayilan or A.QT_ADI.search(m)
              or A.DIS_SUREC.search(m) or (yd and yd.search(m))):
            out[i] = "dis"
        else:
            out[i] = "sinanabilir"
    return out


def test_QT_ADI_deseni_SAGLAM():
    """Desen bozulursa sessizce hiçbir şeye uymaz ve ölçüm şişer.

    Gerçekten oldu: `\\b` kaçışı dosyaya 0x08 olarak yazıldı, desen
    `'\\x08Q[A-Z]\\\\w+\\x08'` oldu ve `QMessageBox` eşleşmedi.
    """
    assert "\x08" not in A.QT_ADI.pattern, "desende kontrol karakteri var"
    assert A.QT_ADI.search("QMessageBox.critical(None, x)")
    assert A.QT_ADI.search("palette.setColor(QPalette.WindowText, QColor(T))")
    # YANLIS-POZITIF: Q ile baslayan her sey Qt degil
    assert not A.QT_ADI.search("Quick = 1")
    assert not A.QT_ADI.search("q = QQ")


def test_kaynak_dosyada_KONTROL_KARAKTERI_yok():
    """Aynı kusurun betiğin başka bir yerinde tekrarlamasını engeller."""
    ham = (KOK / "experiments" / "arayuz_kopru_kapsami.py").read_text(
        encoding="utf-8")
    kotu = {c for c in ham if ord(c) < 32 and c not in "\n\r\t"}
    assert not kotu, f"kaynakta kontrol karakteri: {[hex(ord(c)) for c in kotu]}"


def test_QT_SINIFI_govdesi_dis_sayilir():
    kaynak = (
        "from PySide6.QtWidgets import QWidget\n"
        "class Panel(QWidget):\n"
        "    def kur(self):\n"
        "        toplam = 1 + 2\n"          # saf mantik AMA widget metodu
        "        self.lay.addLayout(self.row)\n")
    k = _siniflandir(kaynak)
    assert k[4] == "dis", "Qt sınıfının içindeki saf satır da ekran ister"
    assert k[5] == "dis"


def test_MODUL_DUZEYI_saf_mantik_SINANABILIR_sayilir():
    """Ölçüt çok geniş olmamalı: ekran istemeyen mantık öyle sayılmalı."""
    kaynak = ("def kare(x):\n"
              "    y = x * x\n"
              "    return y + 1\n")
    k = _siniflandir(kaynak)
    assert k[2] == "sinanabilir" and k[3] == "sinanabilir"


def test_DIS_CAGRIYI_SARAN_fonksiyon_da_dis_sayilir():
    """Satır-yerel ölçüt bunu kaçırıyordu ve `sinanabilir` şişiyordu."""
    kaynak = ("import subprocess\n"
              "def _kos(cmd):\n"
              "    return subprocess.run(cmd)\n"
              "def sar(x):\n"
              "    sonuc = _kos(x)\n"        # kendisi dis ad ICERMEZ
              "    return sonuc\n")
    k = _siniflandir(kaynak)
    assert k[5] == "dis", "dış çağrıyı saran fonksiyon sınanabilir sayılıyor"
    assert k[6] == "dis"


def test_ITHAL_EDILEMEYEN_modul_olculur_varsayilmaz():
    """`vsp` gibi kurulu olmayan bir API'ye dokunan satır sürülemez --- ama
    bu VARSAYILMAZ, ithal denenerek ölçülür."""
    yok = A._ithal_edilemeyenler(
        "import json\nimport kesinlikle_olmayan_modul_xyz as z\n")
    assert "z" in yok and "json" not in yok
    k = _siniflandir("import kesinlikle_olmayan_modul_xyz as z\n"
                     "def f():\n"
                     "    return z.bir_sey()\n")
    assert k[3] == "dis"


def test_KURULU_paket_dis_sayilmaz():
    """YANLIŞ-POZİTİF kapısı: kurulu bir paket 'dış bağımlı' değildir, yoksa
    numpy kullanan her satır sınanamaz ilan edilirdi."""
    assert A._ithal_edilemeyenler("import numpy as np\n") == set()
    k = _siniflandir("import numpy as np\n"
                     "def f(a):\n"
                     "    return np.sum(a)\n")
    assert k[3] == "sinanabilir"


def _ozet(**katmanlar) -> dict:
    """`_ozetle`yi GERÇEK yoldan çağır --- oran ve hüküm alanlarını o üretir.

    Ilk surum `_hukum`u elle kurulmus sozluklerle cagiriyordu ve `oran_pct`
    alani eksik oldugu icin KeyError verdi. Elle kurmak yalniz testi degil,
    olcumu de gercek yolundan ayirirdi.
    """
    return A._ozetle({ad: {"eksik": e, "eksik_sinanabilir": s,
                           "eksik_io": 0, "eksik_savunma": 0,
                           "eksik_dis_bagimli": e - s, "ifade": e,
                           "_bunun_girisi": 0}
                      for ad, (e, s) in katmanlar.items()}, [])


def test_ESIK_ve_HUKUM_ayni_yone_bakiyor():
    """Hüküm eşiği aşınca 'cömert', altında kalınca 'destekleniyor' demeli.
    Ters kurulmuş bir hüküm cümlesi sessizce yanlış rapor üretir."""
    yuksek = _ozet(K=(100, 90))
    assert "daraltılmalı" in yuksek["verdikt"]
    assert yuksek["iddia_comert_mi"] and yuksek["iddia_comert_katmanlar"] == ["K"]
    dusuk = _ozet(K=(100, 2))
    assert "ÖLÇÜMLE" in dusuk["verdikt"]
    assert not dusuk["iddia_comert_mi"]


def test_HUKUM_TOPLAMDAN_verilmez_katmandan_verilir():
    """GERÇEK VAKA: büyük paydalı katman küçüğü eritiyordu.

    Arayüz 1087/16, köprüler 715/207 --- toplam %12,4 ile eşiğin altında ama
    köprü katmanı %29,0 ile üstünde. Ölçümün ilk sürümü toplamı kullanıyor ve
    ``rapor haklı'' diyordu; yani raporun üç paragraf yukarıda uyardığı kusuru
    (``toplam yüzde tek başına yanıltıcıdır'') ölçümün kendisi işliyordu.
    """
    r = _ozet(Buyuk=(1087, 16), Kucuk=(715, 207))
    assert r["toplam_oran_pct"] < A.COMERTLIK_ESIGI_PCT, "vaka artık geçerli değil"
    assert r["iddia_comert_katmanlar"] == ["Kucuk"], \
        "toplam eşiğin altında diye küçük katman aklandı"
    assert "TOPLAMDAN verilmez" in r["verdikt"]


def test_KATMAN_uyeligi_TEK_KAYNAKTAN():
    """Katman listesi burada yeniden yazılırsa iki liste sessizce ayrışır."""
    from kapsam_katmanlari import KATMANLAR
    for ad, uyeler in A._katmanlar().items():
        assert uyeler is KATMANLAR[ad], f"{ad}: liste kopyalanmış"


def test_RAPORDAKI_sayilar_kanittan_sapmiyor():
    """Rapor bu ölçümün sayılarını taşıyorsa kanıtla aynı olmalı.

    Bu bölüm raporun `sabit metin, değişen veri` kusurunu avlayan bölümün ta
    kendisi; kendi sayısını elle taşımak onu aynı kusura düşürürdü.
    """
    import json

    kanit = KOK / "arayuz_kopru_kapsami.json"
    tex = KOK / "docs" / "teknik_rapor.tex"
    if not (kanit.exists() and tex.exists()):
        import pytest
        pytest.skip("kanıt ya da rapor yok")
    d = json.loads(kanit.read_text(encoding="utf-8"))
    t = tex.read_text(encoding="utf-8")
    for ad, k in d["katmanlar"].items():
        for alan in ("eksik", "eksik_sinanabilir"):
            assert str(k[alan]) in t, f"{ad}/{alan} ({k[alan]}) raporda yok"
        assert f"{k['oran_pct']}".replace(".", "{,}") in t, \
            f"{ad} oranı raporda yok"
    # TOPLAM YAZILI AMA HUKUM VERMEDIGI de yazili olmali
    assert f"{d['toplam_oran_pct']}".replace(".", "{,}") in t
    assert "hüküm ondan verilmedi" in t or "hüküm TOPLAMDAN" in t, \
        "toplamın hüküm vermediği raporda söylenmiyor"
    # HUKUM ILE RAPOR AYNI YONE BAKIYOR MU
    if d["iddia_comert_katmanlar"]:
        assert "daraltıldı" in t or "daraltılmalı" in t, \
            "ölçüm 'cömert' diyor ama rapor cümlesini daraltmıyor"


def test_BAYAT_kapsam_kaydi_reddedilir(tmp_path, monkeypatch):
    """Kapsam SATIR NUMARASI taşır; kaynak sonradan değişirse numaralar kayar
    ve sınıflandırma YANLIŞ SATIRIN metnini okur --- sessizce.

    GERÇEK VAKA: `construct2d_bridge`e iki satır eklendi ve kayıt 207'den
    209'a "değişti". Değişen kod değil HİZALAMAYDI. Sayı yine makul
    görünüyordu, yani gözle yakalanmazdı.
    """
    import time

    cov = tmp_path / "cov.json"
    cov.write_text("{}", encoding="utf-8")
    kaynak = tmp_path / "sahte_modul.py"
    monkeypatch.setattr(A, "KOK", tmp_path)
    monkeypatch.setattr(A, "_katmanlar", lambda: {"T": ["sahte_modul.py"]})

    # KAYNAK KAPSAMDAN ESKI -> taze
    kaynak.write_text("x = 1\n", encoding="utf-8")
    import os
    os.utime(kaynak, (cov.stat().st_atime - 10, cov.stat().st_mtime - 10))
    assert A._bayat_kaynaklar(cov) == []

    # KAYNAK KAPSAMDAN YENI -> bayat
    time.sleep(0.01)
    kaynak.write_text("x = 2\n", encoding="utf-8")
    assert A._bayat_kaynaklar(cov) == ["sahte_modul.py"]


def test_KATMAN_ADI_sabit_yazilmaz():
    """`_ozetle` bir katmanı adıyla indeksliyordu ve başka bir katman kümesiyle
    çağrılınca KeyError veriyordu --- ölçüt kendi verisine pinliydi."""
    r = _ozet(BambaskaBirKatman=(50, 40))
    assert "BambaskaBirKatman" in r["_toplam_neden_hukum_vermez"]
