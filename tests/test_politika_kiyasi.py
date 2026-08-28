"""Kayıtlı hüküm ile BUGÜNKÜ hüküm arayüzde yan yana --- tüketicisi olan ölçüm.

`hukum_tazeligi` deponun 23 koşusunun 15'inde kalem-düzeyi hükmün bayat
olduğunu ve on beşinin de AYNI yönde --- gevşek --- olduğunu ölçüyordu:
kayıt "C_L VALIDATED, tasarım-güvenli EVET" derken bugünkü kod "TREND,
HAYIR" diyor. Yani kayıt, aracın bugün vermeyeceği bir güvence vaat ediyor.

AMA O ÖLÇÜMÜ KİMSE OKUMUYORDU. Modülün tek çağıranı kendi testiydi; koşu
geçmişine bakan bir kullanıcı bayat hükmü olduğu gibi görüyordu. Bu deponun
baskın kusuru tam bu sınıf: kapı VAR, üretim yolu onu ÇAĞIRMIYOR.

Testler üç şeyi bağlar:
  1. `tek()` tek koşuyu ölçüyor ve `tara()` ONU çağırıyor (ikinci ölçüt
     kaynağı kurulmuyor --- modülün kendi kısıtı bunu yasaklıyor),
  2. arayüz düğmesi gerçekten `hukum_tazeligi`'ne bağlı,
  3. kart GEVŞEK bayatlıkta uyarı basıyor, SIKI bayatlıkta basmıyor
     (ölçütün iki tarafı) ve kaydı DEĞİŞTİRMİYOR.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))


# ----------------------------------------------------------------- tek()

def test_TEK_ve_TARA_AYNI_YOLU_KULLANIYOR():
    """`tara` kendi kıyas mantığını TEKRAR YAZMAMALI. İki yol, iki ölçüt
    demektir ve modülün kendi `_kisit` metni bunu açıkça yasaklıyor."""
    agac = ast.parse((KOK / "hukum_tazeligi.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(agac)
              if isinstance(n, ast.FunctionDef) and n.name == "tara")
    cagrilar = {getattr(c.func, "id", getattr(c.func, "attr", ""))
                for c in ast.walk(fn) if isinstance(c, ast.Call)}
    assert "tek" in cagrilar, "tara() tek()'i çağırmıyor — ikinci ölçüt yolu"
    assert "_yeniden_hukum" not in cagrilar, (
        "tara() kıyası kendi başına kuruyor; tek() üzerinden geçmeli")


def test_TEK_bozuk_kaydi_ADIYLA_bildiriyor(tmp_path):
    import hukum_tazeligi
    d = tmp_path / "kirik"
    d.mkdir()
    (d / "sonuc.json").write_text("{bozuk", encoding="utf-8")
    r = hukum_tazeligi.tek(d)
    assert r["durum"] == "olculemedi" and r["kosu"] == "kirik"
    assert "okunamadı" in r["neden"]


def test_TEK_kapsam_disini_OLCULEMEDIDEN_ayiriyor(tmp_path):
    """Başarısız bir koşuda bayatlık SORUSU yoktur. İkisini aynı kovaya
    atmak kapıyı gereksiz kırmızı gösterirdi."""
    import hukum_tazeligi
    d = tmp_path / "basarisiz"
    d.mkdir()
    (d / "sonuc.json").write_text(json.dumps({"status": "failed"}),
                                  encoding="utf-8")
    assert hukum_tazeligi.tek(d)["durum"] == "kapsam-disi"

    d2 = tmp_path / "hukumsuz"
    d2.mkdir()
    (d2 / "sonuc.json").write_text(json.dumps({"status": "ok"}),
                                   encoding="utf-8")
    assert hukum_tazeligi.tek(d2)["durum"] == "kapsam-disi"


# --------------------------------------------------------------- kart metni

def _md(**r):
    from app_analyzer import KosularDialog
    return KosularDialog._politika_md(r)


def _fark(yon="gevşek", kayitli="VALIDATED", bugun="TREND",
          k_guv=True, b_guv=False):
    return {"nicelik": "C_L (taşıma)", "kayitli": kayitli, "bugun": bugun,
            "yon": yon, "kayitli_tasarim_guvenli": k_guv,
            "bugun_tasarim_guvenli": b_guv}


def test_KART_GEVSEK_bayatlikta_UYARI_basiyor():
    m = _md(kosu="a320", durum="bayat", gevseyen=1, farklar=[_fark()])
    assert "POLİTİKASI DEĞİŞTİ" in m and "YENİDEN DEĞERLENDİRME" in m
    assert "VALIDATED" in m and "TREND" in m


def test_KART_SIKI_bayatlikta_UYARI_BASMIYOR():
    """Ölçütün yanlış-pozitif tarafı. Sıkılaşma yönündeki fark yalnız
    muhafazakârdır; onu da tehlike gibi göstermek uyarıyı değersizleştirir."""
    m = _md(kosu="x", durum="bayat", gevseyen=0,
            farklar=[_fark(yon="sıkı", kayitli="TREND", bugun="VALIDATED",
                           k_guv=False, b_guv=True)])
    assert "POLİTİKASI DEĞİŞTİ" not in m
    assert "sıkılaşma" in m


def test_KART_TAZE_kosuda_fark_iddia_etmiyor():
    m = _md(kosu="x", durum="taze", gevseyen=0, farklar=[])
    assert "AYNI" in m and "POLİTİKASI DEĞİŞTİ" not in m


def test_KART_OLCULEMEYENI_TAZE_saymiyor():
    m = _md(kosu="x", durum="olculemedi", neden="ValueError: yok")
    assert "Ölçülemedi" in m and "TAZE sayılmaz" in m


def test_KART_KAYDIN_DEGISMEDIGINI_SOYLUYOR():
    """Kullanıcı bu pencereyi görünce 'kayıt düzeltildi mi' diye sorar;
    cevap kartın üstünde yazılı olmalı."""
    m = _md(kosu="a320", durum="bayat", gevseyen=1, farklar=[_fark()])
    assert "değiştirilmedi" in m


# ------------------------------------------------------------- arayuz bagi

def test_ARAYUZ_DUGMESI_OLCUME_BAGLI():
    """Ölçüt metne değil AĞACA bağlanır: `_politika_kiyasla` gövdesinde
    `hukum_tazeligi` içe aktarılıp `tek` çağrılmalı."""
    agac = ast.parse((KOK / "app_analyzer.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(agac) if isinstance(n, ast.FunctionDef)
              and n.name == "_politika_kiyasla")
    ithal = {a.name for n in ast.walk(fn) if isinstance(n, ast.Import)
             for a in n.names}
    assert "hukum_tazeligi" in ithal, "düğme ölçüm modülünü çağırmıyor"
    assert any(getattr(c.func, "attr", "") == "tek"
               for c in ast.walk(fn) if isinstance(c, ast.Call)), (
        "tek() çağrılmıyor")


def test_ARAYUZ_KAYDA_GERI_YAZMIYOR():
    """Tarihsel kanıt korunur. Politika yolunda sonuc.json'a yazan bir
    çağrı olmamalı --- 'yeniden değerlendir' bir GÖSTERİM'dir, düzeltme
    değil."""
    agac = ast.parse((KOK / "app_analyzer.py").read_text(encoding="utf-8"))
    for ad in ("_politika_kiyasla", "_politika_md"):
        fn = next(n for n in ast.walk(agac)
                  if isinstance(n, (ast.FunctionDef,)) and n.name == ad)
        yazan = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                 and getattr(c.func, "attr", "") in ("write_text", "dump",
                                                     "write")]
        assert not yazan, f"{ad}: kayda geri yazıyor"


def test_OLCUM_MODULU_KOSU_KAYDINA_YAZMIYOR():
    """OLCUT BIR KEZ FAZLA GENIS KURULDU: once "hic write_text olmasin"
    dendi ve modulun KENDI kanit dosyasini yazan satiri sucladi. Yasak
    olan sey KOSU KAYDINA yazmaktir; kendi ciktisini yazmak degil.

    Olcut dolayisiyla YOLA baglanir: yazilan hedef `vehicle_runs` ya da
    `sonuc.json` icermemeli.
    """
    agac = ast.parse((KOK / "hukum_tazeligi.py").read_text(encoding="utf-8"))
    for c in ast.walk(agac):
        if not (isinstance(c, ast.Call)
                and getattr(c.func, "attr", "") == "write_text"):
            continue
        hedef = ast.unparse(c.func.value)
        assert "sonuc" not in hedef and "vehicle_runs" not in hedef, (
            f"kosu kaydina geri yaziyor: {hedef}")
