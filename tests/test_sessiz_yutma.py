"""Sessiz yutma bütçesi — "savunma kuruldu ama hükmü ulaşmıyor" sınıfı görünür kalsın.

Bu oturumda AYNI kusur üç kez ölçüldü ve üçü de sonuç üretmeye devam ederken güvenceyi
sessizce düşürüyordu:
  * salinim_analizi hesaplanıyordu, tüketicisi yoktu   → salınan çözüme "✅ yakınsadı"
  * measure_yplus `except: pass` → None                → y⁺=5399 kanıta hiç girmedi
  * geometry_sanity eksen kontrolü tipe bağlıydı       → 12× A_ref hatası görünmedi

`sessiz_yutma.py` bu imzayı AST ile sayar (grep çok satırlı blokta yanılır).
"""
import sessiz_yutma

# Ham sayı yerine İNCELENMEMİŞ sayı izlenir: "incelendi ve kabul edildi" ile "henüz
# bakılmadı" aynı görünüyordu — bu oturumda avlanan kusurun ta kendisi. Kabul, kodda
# `# sessiz-yutma: kabul — <gerekçe>` satırı ister ve gerekçe o `except`in yanında durur.
#
# KAPSAM DÜZELTMESİ: ilk sürüm yalnız KÖK dosyaları "güven yolu" sayıyordu ve
# "incelenmemiş = 0" iddiası bu yüzden YANLIŞTI — CLAUDE.md'nin KANONİK katman dediği
# `analysis/` hiç sayılmıyordu (orada 11 gerekçesiz sessizlik vardı), `experiments/`
# (V&V çapalarının üretildiği yer) ise hiç taranmıyordu. Kapsam genişletilince
# güven-yolu 31 → 55, incelenmemiş 0 → 28 çıktı; hepsi tek tek gerekçelendirildi.
#
# Ölçülen (2026-07-28, GENİŞ kapsam): 80 toplam / 55 güven yolunda / 55 kabul edilmiş.
TABAN_TOPLAM = 80
TABAN_GUVEN_YOLU = 55
TABAN_INCELENMEMIS = 25
TABAN_INCELENMEMIS_GUVEN_YOLU = 0

KABUL_SATIRI = "    # sessiz-yutma: kabul — sebebi şu"


def _yaz(p, satirlar):
    p.write_text("\n".join(satirlar) + "\n", encoding="utf-8")


def test_toplam_sessiz_yutma_artmadi():
    b = sessiz_yutma.tara()
    assert len(b) <= TABAN_TOPLAM, (
        f"{len(b)} sessiz yutma (taban {TABAN_TOPLAM}). Yeni bir `except: pass` / "
        "`except: return None` eklendi. Sebebi bir yere KAYDEDİLMELİ (gerilemeler, "
        "onarimlar, 'neden' alanı) ya da gerekçeli kabul etiketi konmalı.")


def test_guven_yolunda_sessizlik_artmadi():
    """Güven yolu = sonucu bir sayıya/hükme dönüşen modüller."""
    gy = [x for x in sessiz_yutma.tara() if x["guven_yolu"]]
    assert len(gy) <= TABAN_GUVEN_YOLU, (
        f"{len(gy)} sessiz yutma GÜVEN YOLUNDA (taban {TABAN_GUVEN_YOLU}): "
        + ", ".join(f"{x['dosya']}:{x['satir']}" for x in gy[:6]))


def test_guven_yolunda_INCELENMEMIS_yok():
    """ASIL ÖLÇÜT: sonucu bir sayıya/hükme dönüşen her sessizliğin YAZILI gerekçesi
    olmalı. Yeni bir tanesi eklenirse burası kırılır ve gerekçe yazılmasını zorlar."""
    inc = [x for x in sessiz_yutma.incelenmemis() if x["guven_yolu"]]
    assert len(inc) <= TABAN_INCELENMEMIS_GUVEN_YOLU, (
        "güven yolunda gerekçesiz sessiz yutma: "
        + ", ".join(f"{x['dosya']}:{x['satir']} ({x['fonksiyon']})" for x in inc))


def test_incelenmemis_toplam_artmadi():
    assert len(sessiz_yutma.incelenmemis()) <= TABAN_INCELENMEMIS


def test_kabul_gerekcesiyle_birlikte_okunuyor(tmp_path, monkeypatch):
    """Etiketin varlığı yetmez; gerekçe metni de çıkarılmalı."""
    _yaz(tmp_path / "a.py",
         ["def f():", "    try:", "        g()", KABUL_SATIRI,
          "    except Exception:", "        pass"])
    monkeypatch.setattr(sessiz_yutma, "ROOT", tmp_path)
    b = sessiz_yutma.tara()
    assert b and b[0]["kabul"] == "sebebi şu"
    assert sessiz_yutma.incelenmemis(b) == []


def test_kabul_etiketi_UZAK_yorumdan_alinmaz(tmp_path, monkeypatch):
    """Etiket `except`in hemen ÜSTÜNDE olmalı; araya KOD girerse sayılmaz — yoksa
    dosyanın başındaki tek bir yorum tüm bloklara mazeret olurdu."""
    _yaz(tmp_path / "b.py",
         ["def f():", KABUL_SATIRI, "    x = 1", "    try:", "        g()",
          "    except Exception:", "        pass"])
    monkeypatch.setattr(sessiz_yutma, "ROOT", tmp_path)
    assert sessiz_yutma.incelenmemis(sessiz_yutma.tara())


def test_denetim_kendini_dogruluyor(tmp_path, monkeypatch):
    """Tarayıcı gerçekten yakalıyor mu — ve sebebi KAYDEDEN bloğu affediyor mu?"""
    _yaz(tmp_path / "yutan.py",
         ["def f():", "    try:", "        g()", "    except Exception:", "        pass"])
    _yaz(tmp_path / "kaydeden.py",
         ["def f(kayit):", "    try:", "        g()", "    except Exception as e:",
          "        kayit.append(str(e))"])
    monkeypatch.setattr(sessiz_yutma, "ROOT", tmp_path)
    adlar = {x["dosya"] for x in sessiz_yutma.tara()}
    assert "yutan.py" in adlar, "sebebi yutan blok yakalanmalı"
    assert "kaydeden.py" not in adlar, "sebebi kaydeden blok yanlış alarm vermemeli"


def test_bare_except_riskli_sayiliyor(tmp_path, monkeypatch):
    _yaz(tmp_path / "cip.py",
         ["def f():", "    try:", "        g()", "    except:", "        return None"])
    monkeypatch.setattr(sessiz_yutma, "ROOT", tmp_path)
    b = sessiz_yutma.tara()
    assert b and b[0]["yakalanan"] == "BARE except"


def test_duzeltilen_vakalar_geri_gelmedi():
    """Bu oturumda kapatılan delikler yeniden açılmasın."""
    gerekcesiz = {(x["dosya"], x["fonksiyon"]) for x in sessiz_yutma.incelenmemis()}
    for vaka in (("vehicle_pipeline.py", "measure_yplus"),
                 ("vehicle_pipeline.py", "prepare_geometry"),
                 ("vehicle_fea.py", "run_structural_check"),
                 ("supersonic_report.py", "_read_solver_gci"),
                 ("auto_pilot.py", "auto_configure")):
        assert vaka not in gerekcesiz, vaka


def test_kapsam_KANONIK_katmani_iceriyor():
    """İlk sürümün kapsam hatası geri gelmesin: `analysis/` (kanonik CFD/FEA katmanı)
    ve `experiments/` (V&V çapaları) güven yolunda SAYILMALI. Sayılmazsa 'incelenmemiş
    = 0' iddiası kendiliğinden doğru çıkar ve hiçbir şey ifade etmez."""
    assert sessiz_yutma._guven_yolu("analysis/openfoam_runner.py")
    assert sessiz_yutma._guven_yolu("experiments/duz_levha_cf.py")
    assert sessiz_yutma._guven_yolu("solvers/gmsh_wrapper.py")
    assert "experiments" not in sessiz_yutma.ATLA


def test_frd_parser_atlanan_satiri_SAYIYOR():
    """Kanonik FEA ayrıştırıcısı bozuk satırı sessizce atıyordu; tepe gerilme o
    satırdaysa maksimum düşük çıkar ve SF hükmü iyimser olur."""
    from analysis.frd_parser import FRDResult
    assert "atlanan_satir" in FRDResult.__dataclass_fields__


def test_hacim_olculemezse_SIFIR_donmuyor():
    """0.0 makul görünen yanlış bir sayıdır ve aritmetiğe sızar; None 'bilinmiyor' der."""
    import inspect

    from analysis.geometry_loader import GeometryInfo
    src = inspect.getsource(GeometryInfo.volume.fget)
    assert "return None" in src and "return 0.0" not in src


def test_gerilemeler_alani_sonuca_bagli():
    """Kayıt yeri olmadan 'sebebi kaydet' kuralı uygulanamaz."""
    from vehicle_pipeline import VehicleAnalysisResult
    assert "gerilemeler" in VehicleAnalysisResult.__dataclass_fields__


def test_rapor_gerilemeleri_gosteriyor():
    import inspect

    import vehicle_report
    src = inspect.getsource(vehicle_report)
    assert 'getattr(r, "gerilemeler", None)' in src
    i = src.index('getattr(r, "gerilemeler", None)')
    assert "GÜVENCE KAYBI" in src[i - 200:i + 300]


def test_supersonik_GCI_kaldi_ile_YOK_ayriliyor():
    """Üç durum tek None'a iniyordu ve rapor hepsine "gelecek-iş kalemi" diyordu —
    oysa GCI DENENDİ ve KALDI çok daha ağır bir ifadedir."""
    import inspect

    import supersonic_report
    src = inspect.getsource(supersonic_report)
    assert "_gecersiz" in src
    i = src.index("_gecersiz")
    assert "DENENDİ ve GEÇMEDİ" in src[i:i + 3000]
