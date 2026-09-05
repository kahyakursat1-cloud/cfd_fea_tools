"""FSI aktarım sağlığı kartı — ayrışımı gösterir, sayıyı ÜRETMEZ.

Yol haritası V1.1/3. Ölçüm 2026-08-28'de bitmişti; eksik olan okuyan katmandı
ve maddenin kendi cümlesi riski söylüyordu: *"Kart ayrışımı göstermeli, yoksa
okur yine toplamı üretime yazar."*

Kartın var oluş sebebi tek bir tabloda görünüyor:

    gripen_AB_Right   toplam %76,72   EŞLEME %0,00   → eşleme SAĞLAM
    _fsi_esnek        toplam %102,64  EŞLEME %24,10  → eşleme GERÇEKTEN kötü

Toplama bakan bir okur ikisini de reddeder. Bu testler kartın o iki vakayı
ayırdığını, ayrışım yokken bunu SÖYLEDİĞİNİ ve payları kendisi hesaplamadığını
bağlar.
"""

import ast
import json
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import fsi_aktarim_karti as karti  # noqa: E402

KANIT = KOK / "fsi_korunum.json"


@pytest.fixture(scope="module")
def sat():
    if not KANIT.exists():
        pytest.skip("fsi_korunum.json yok (python experiments/fsi_korunum.py)")
    s = karti.satirlar()
    assert s, "kanıt var ama kart hiç satır üretmedi"
    return s


def _sade(s: str) -> str:
    """Diyakritiksiz karşılaştırma.

    `"VERİLMEDİ".lower()` Python'da `i` + U+0307 üretir ve `"verilmedi"`
    aramasını sessizce düşürür; `"verilmedi".upper()` de noktasız I verir.
    Ölçüt bu yüzden metnin kendisine değil, harflerin sadeleştirilmiş
    hâline bakar --- yeniden yazılan ama aynı şeyi söyleyen bir gerekçe
    testi kırmasın diye.
    """
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ç", "c"), ("ö", "o"), ("ü", "u")):
        s = s.replace(a, b)
    return s


def _vaka(sat, ad):
    for r in sat:
        if r["vaka"] == ad:
            return r
    pytest.skip(f"{ad} bu kanıtta yok")


def test_AYRISIM_iki_zit_vakayi_AYIRIYOR(sat):
    """Kartın tek işi bu: aynı toplamın altındaki iki farklı gerçeği ayırmak."""
    gripen = _vaka(sat, "gripen_AB_Right")
    esnek = _vaka(sat, "_fsi_esnek")

    assert gripen["toplam_pct"] > 50, "gripen'in TOPLAM artığı büyük olmalı"
    assert gripen["esleme_pay_pct"] < 1.0, (
        "gripen'in EŞLEME payı küçük olmalı — toplama bakan bir okur bu "
        "çalışan vakayı reddederdi")
    assert esnek["esleme_pay_pct"] > 20, (
        "_fsi_esnek'in eşleme payı gerçekten büyük; kart onu gripen'den "
        "ayırt edemiyorsa ayrışımı göstermenin anlamı yok")
    # ASIL İDDİA: gripen'in HÂKİM artığı onun EŞLEME payıdır, TOPLAMI değil.
    #
    # İlk sürümde burada `gripen["hakim_pct"] < esnek["hakim_pct"]` yazıyordu
    # ve kart ayrışımı hiç kullanmadığında da geçiyordu (76,72 < 102,64).
    # Yani kartın var oluş sebebi test edilmemiş kalıyordu; enjeksiyonla
    # görüldü. Ölçüt sayının KENDİSİNE bağlandı.
    assert gripen["hakim_pct"] == pytest.approx(gripen["esleme_pay_pct"], abs=1e-9), (
        f"gripen'in hâkim artığı {gripen['hakim_pct']} — eşleme payı "
        f"{gripen['esleme_pay_pct']} olmalıydı. Kart toplamı yönetici alıyor "
        "ve çalışan bir vakayı kötü gösteriyor.")
    assert gripen["hakim_pct"] < 1.0 < gripen["toplam_pct"], (
        "ayrışımın anlamı tam burada: toplam büyük, eşleme küçük")


def test_HUKUM_esleme_payina_bakiyor_toplama_DEGIL(sat):
    """Hâkim artık, ayrışımı olan satırlarda toplamı ASLA aşmaz-mış gibi
    davranmaz: eşleme payı neyse hâkim bileşen odur."""
    sayilan = 0
    for r in sat:
        if not r["ayrisim_var"] or r["hakim_metrik"] != "esleme_isi":
            continue
        sayilan += 1
        assert r["hakim_pct"] == pytest.approx(r["esleme_pay_pct"], rel=1e-9), (
            f"{r['vaka']}: hâkim metrik 'esleme_isi' ama sayı eşleme payı "
            f"değil ({r['hakim_pct']} vs {r['esleme_pay_pct']})")
    # DÖNGÜNÜN KOŞTUĞU AYRICA BAĞLANIR. Kart ayrışımı hükme hiç vermediğinde
    # hiçbir satırın hâkim metriği 'esleme_isi' olmuyor, döngü gövdesi bir kez
    # bile çalışmıyor ve test SESSİZCE geçiyordu --- bu deponun imza kusuru,
    # testin kendi içinde. Enjeksiyonla görüldü.
    assert sayilan >= 10, (
        f"yalnız {sayilan} satırda hâkim metrik 'esleme_isi'. Ölçülen 24 "
        "vakanın çoğunda eşleme payı yönetici olmalı; değilse kart ayrışımı "
        "kapıya taşımıyordur ve bu test hiçbir şey sınamamıştır.")
    # ve TOPLAMA bakan bir kart hiç kalmamalı
    toplama_bakan = [r["vaka"] for r in sat
                     if r["ayrisim_var"] and r["hakim_metrik"] == "arayuz_isi_TOPLAM"]
    assert not toplama_bakan, (
        f"ayrışımı olduğu hâlde toplama bakan satır: {toplama_bakan}")


def test_AYRISIM_YOKSA_kart_bunu_SOYLUYOR(tmp_path):
    """Sessiz geri düşüş kartın önlemek için var olduğu yanılgıyı üretir."""
    veri = {"vakalar": [{
        "vaka": "ayrisimsiz", "kuvvet_hatasi": 0.004, "moment_hatasi": 0.02,
        "arayuz_isi_hatasi": 0.7672, "alan_farki_pct": 1.0,
        # esleme_is_payi ve yuzey_is_payi YOK
    }]}
    p = tmp_path / "korunum.json"
    p.write_text(json.dumps(veri), encoding="utf-8")

    r = karti.satirlar(p)[0]
    assert r["ayrisim_var"] is False
    assert r["esleme_pay_pct"] is None, "olmayan pay uydurulmamalı"
    assert r["hakim_pct"] == pytest.approx(76.72, rel=1e-6), (
        "ayrışım yokken hüküm TOPLAM artığa bakmalı")
    neden = _sade(r["hukum"].get("neden") or "")
    assert "ayrisim" in neden and "verilmedi" in neden, (
        "geri düşüş SESSİZ olmamalı — hükmün gerekçesi ayrışımın "
        f"verilmediğini söylemeli; söylediği: {r['hukum'].get('neden')!r}")
    assert r["hakim_metrik"] == "arayuz_isi_TOPLAM", (
        "hâkim bileşenin ADI da toplamı gösterdiğini söylemeli — kart bu adı "
        "satıra yazıyor")


def test_KIMLIK_TUTMAYAN_ayrisim_HUKME_girmiyor(tmp_path):
    """Pay bir sayı ama dayanağı yoksa hükme sokmak onu kanıt sayar.

    Ayrışım `T_düğüm - T_CFD == Σ dF ⊗ δ` kimliğine dayanır; kanıtta 24/24
    vakada <=1e-10 tuttu. Tutmayan bir satırda paylar gösterilmez.
    """
    veri = {"vakalar": [{
        "vaka": "kimlik_bozuk", "kuvvet_hatasi": 0.0, "moment_hatasi": 0.01,
        "arayuz_isi_hatasi": 0.90, "esleme_is_payi": 0.02,
        "yuzey_is_payi": 0.88, "kimlik_artigi": 1e-3, "alan_farki_pct": 1.0,
    }]}
    p = tmp_path / "korunum.json"
    p.write_text(json.dumps(veri), encoding="utf-8")

    r = karti.satirlar(p)[0]
    assert r["kimlik_saglam"] is False
    assert r["ayrisim_var"] is False, (
        "kimlik tutmuyorken pay hükme girerse dayanaksız bir sayı "
        "hüküm gibi sunulmuş olur")
    assert r["hakim_pct"] == pytest.approx(90.0, rel=1e-6)


def test_SIFIR_pay_ile_OLCULMEDI_ayri(tmp_path):
    """`0.0` korunumlu şemada geçerli bir ölçüm; 'yok' demek değil."""
    veri = {"vakalar": [{
        "vaka": "sifir_pay", "kuvvet_hatasi": 0.0, "moment_hatasi": 0.0001,
        "arayuz_isi_hatasi": 0.7672, "esleme_is_payi": 0.0,
        "yuzey_is_payi": 0.7672, "kimlik_artigi": 0.0, "alan_farki_pct": 1.0,
    }]}
    p = tmp_path / "korunum.json"
    p.write_text(json.dumps(veri), encoding="utf-8")

    r = karti.satirlar(p)[0]
    assert r["ayrisim_var"] is True, (
        "sıfır eşleme payı 'ayrışım yok' değildir — doğruluk sınamasıyla "
        "yazılmış bir kart bu vakayı sessizce toplama düşürürdü")
    assert r["esleme_pay_pct"] == 0.0


def test_KART_yuzde_HESAPLAMIYOR_kanittan_OKUYOR():
    """Yönetici YOL bilir, DEĞER bilmez.

    `turek_hron_kiyaslama`'ya konan kuralın aynısı. Kart bir pay HESAPLASAYDI
    kapının hükmüyle ekrandaki sayı sessizce ayrışabilirdi; birim çevrimi
    (oran→yüzde) dışında aritmetik olmamalı.
    """
    agac = ast.parse((KOK / "fsi_aktarim_karti.py").read_text(encoding="utf-8"))
    fonk = {d.name: d for d in ast.walk(agac)
            if isinstance(d, ast.FunctionDef)}
    assert "satirlar" in fonk

    # `_pct` birim çevrimidir ve tek yerde durur; `satirlar` içinde başka
    # bölme/çıkarma yapılmamalı --- pay ORADA türetilmiş olurdu.
    yasak = [n for n in ast.walk(fonk["satirlar"])
             if isinstance(n, ast.BinOp)
             and isinstance(n.op, (ast.Div, ast.Sub, ast.Mult))]
    assert not yasak, (
        f"`satirlar` içinde {len(yasak)} aritmetik işlem var; pay kanıttan "
        "OKUNMALI, kartta türetilmemeli")

    # ve hükmü kendisi vermemeli
    govde = (KOK / "fsi_aktarim_karti.py").read_text(encoding="utf-8")
    assert "aktarim_hukmu(" in govde, "hüküm kapıdan alınmalı"
    assert "MUTLAK_RED_PCT" not in govde, (
        "kart kendi eşiğini taşımamalı; eşik kapının tek kaynağındadır")


def test_SIRALAMA_en_kotu_hakim_artik_BASTA(sat):
    degerler = [r["hakim_pct"] for r in sat if r["hakim_pct"] is not None]
    assert degerler == sorted(degerler, reverse=True), (
        "kart en kötüyü başa almazsa okur ilk satıra bakıp geçer")


def test_GUI_karti_KENDI_HESAPLAMIYOR():
    """Pencere yalnız gösterir: sayı da hüküm de modülden gelir."""
    govde = (KOK / "app_analyzer.py").read_text(encoding="utf-8", errors="replace")
    bas = govde.index("class AktarimSagligiDialog")
    son = govde.index("class KuyrukDialog")
    sinif = govde[bas:son]
    assert "fsi_aktarim_karti" in sinif, "pencere kanıdı modülden okumalı"
    assert "aktarim_hukmu(" not in sinif, (
        "pencere kapıyı DOĞRUDAN çağırmamalı; hüküm modülden gelmeli ki "
        "konsol tablosu ile ekran aynı sayıyı göstersin")
    assert "AYRIŞIM YOK" in sinif, (
        "ayrışımın yokluğu satırın üstünde durmalı — kartın var oluş sebebi "
        "olan yanılgı tam orada doğar")


# ─── Pencere gerçekten kuruluyor mu ────────────────────────────────────────
#
# Kaynak-metin denetimi kartın AÇILDIĞINI göstermez. Okunmayan bir kart,
# olmayan bir karttır; pencere offscreen Qt ile gerçekten kurulur.

def test_PENCERE_kuruluyor_ve_AYRISIMI_gosteriyor():
    pytest.importorskip("PySide6", reason="GUI yığını yok (CI)")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    if not KANIT.exists():
        pytest.skip("fsi_korunum.json yok")

    QApplication.instance() or QApplication([])
    import app_analyzer

    d = app_analyzer.AktarimSagligiDialog(None)
    assert d.tbl.rowCount() == len(karti.satirlar())

    basliklar = [d.tbl.horizontalHeaderItem(j).text()
                 for j in range(d.tbl.columnCount())]
    assert any("Eşleme" in b for b in basliklar), (
        "eşleme payı sütunu YOK — kart tam da göstermek için var olduğu "
        "sayıyı göstermiyor")
    assert any("Toplam" in b for b in basliklar), (
        "toplam da görünmeli; okur ikisinin farkını görebilmeli")

    # İlk satır en kötü hâkim artık; gripen gibi 'toplamı büyük, eşlemesi
    # sıfır' bir vakada iki hücre AYRI okunmalı.
    gripen_satir = next(i for i, r in enumerate(karti.satirlar())
                        if r["vaka"] == "gripen_AB_Right")
    j_es = basliklar.index(next(b for b in basliklar if "Eşleme" in b))
    j_top = basliklar.index(next(b for b in basliklar if "Toplam" in b))
    es = d.tbl.item(gripen_satir, j_es).text()
    top = d.tbl.item(gripen_satir, j_top).text()
    assert es != top, (
        f"gripen'in eşleme ve toplam hücreleri aynı ({es}) — ekranda ayrışım "
        "yok demektir")
    assert es.startswith("%0."), f"gripen'in eşleme payı küçük olmalı, {es} yazıyor"


def test_PENCERE_ayrisimi_olmayan_satirda_UYARIYOR(tmp_path, monkeypatch):
    """Ekranda toplam gösterilirken bunun toplam olduğu YAZILI olmalı."""
    pytest.importorskip("PySide6", reason="GUI yığını yok (CI)")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    veri = {"vakalar": [{
        "vaka": "ayrisimsiz", "kuvvet_hatasi": 0.001, "moment_hatasi": 0.002,
        "arayuz_isi_hatasi": 0.30, "alan_farki_pct": 1.0,
    }]}
    p = tmp_path / "korunum.json"
    p.write_text(json.dumps(veri), encoding="utf-8")
    monkeypatch.setattr(karti, "KANIT", p)

    QApplication.instance() or QApplication([])
    import app_analyzer

    d = app_analyzer.AktarimSagligiDialog(None)
    hucreler = [d.tbl.item(0, j).text() for j in range(d.tbl.columnCount())]
    assert any("AYRIŞIM YOK" in h for h in hucreler), (
        f"ayrışımı olmayan satır uyarısız: {hucreler}. Okur toplam artığı "
        "eşleme payı sanar --- kartın önlemek için var olduğu yanılgı.")
