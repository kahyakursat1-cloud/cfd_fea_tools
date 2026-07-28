"""Sessiz yutma bütçesi — "savunma kuruldu ama hükmü ulaşmıyor" sınıfı görünür kalsın.

Bu oturumda AYNI kusur üç kez ölçüldü ve üçü de sonuç üretmeye devam ederken güvenceyi
sessizce düşürüyordu:
  * salinim_analizi hesaplanıyordu, tüketicisi yoktu   → salınan çözüme "✅ yakınsadı"
  * measure_yplus `except: pass` → None                → y⁺=5399 kanıta hiç girmedi
  * geometry_sanity eksen kontrolü tipe bağlıydı       → 12× A_ref hatası görünmedi

`sessiz_yutma.py` bu imzayı AST ile sayar (grep çok satırlı blokta yanılır). Testler
sayıyı KİLİTLEMEZ-ama-GÖRÜNÜR yapar: yeni bir sessiz yutma eklenirse taban aşılır ve
eklemenin bilinçli olduğu commit'te gerekçesiyle yükseltilmesi gerekir.
"""
import sessiz_yutma

# Ölçülen taban (2026-07-28, düzeltmelerden sonra): 81 toplam / 33 güven yolunda.
# Öncesi 87 / 39 idi; prepare_geometry onarım kayıtları, iz-momentum çapraz-kontrolü,
# kabuk inceltme ve y⁺ ölçümü sebeplerini artık taşıyor.
TABAN_TOPLAM = 81
TABAN_GUVEN_YOLU = 33


def test_toplam_sessiz_yutma_artmadi():
    b = sessiz_yutma.tara()
    assert len(b) <= TABAN_TOPLAM, (
        f"{len(b)} sessiz yutma (taban {TABAN_TOPLAM}). Yeni bir `except: pass` / "
        "`except: return None` eklendi. Sebebi bir yere KAYDEDİLMELİ (gerilemeler, "
        "onarimlar, 'neden' alanı) ya da bu taban gerekçesiyle yükseltilmeli.")


def test_guven_yolunda_sessizlik_artmadi():
    """Güven yolu = sonucu bir sayıya/hükme dönüşen modüller. Buradaki sessizlik
    mühendisi doğrudan yanıltır; bütçesi ayrı ve daha sıkı izlenir."""
    gy = [x for x in sessiz_yutma.tara() if x["guven_yolu"]]
    assert len(gy) <= TABAN_GUVEN_YOLU, (
        f"{len(gy)} sessiz yutma GÜVEN YOLUNDA (taban {TABAN_GUVEN_YOLU}): "
        + ", ".join(f"{x['dosya']}:{x['satir']}" for x in gy[:6]))


def test_denetim_kendini_dogruluyor(tmp_path, monkeypatch):
    """Tarayıcı gerçekten yakalıyor mu — ve sebebi KAYDEDEN bloğu affediyor mu?"""
    (tmp_path / "yutan.py").write_text(
        "def f():\n    try:\n        g()\n    except Exception:\n        pass\n",
        encoding="utf-8")
    (tmp_path / "kaydeden.py").write_text(
        "def f(kayit):\n    try:\n        g()\n    except Exception as e:\n"
        "        kayit.append(str(e))\n", encoding="utf-8")
    monkeypatch.setattr(sessiz_yutma, "ROOT", tmp_path)
    b = sessiz_yutma.tara()
    adlar = {x["dosya"] for x in b}
    assert "yutan.py" in adlar, "sebebi yutan blok yakalanmalı"
    assert "kaydeden.py" not in adlar, "sebebi kaydeden blok yanlış alarm vermemeli"


def test_bare_except_riskli_sayiliyor(tmp_path, monkeypatch):
    (tmp_path / "cip.py").write_text(
        "def f():\n    try:\n        g()\n    except:\n        return None\n",
        encoding="utf-8")
    monkeypatch.setattr(sessiz_yutma, "ROOT", tmp_path)
    b = sessiz_yutma.tara()
    assert b and b[0]["yakalanan"] == "BARE except"


def test_duzeltilen_uc_vaka_geri_gelmedi():
    """Bu oturumda kapatılan üç somut delik yeniden açılmasın."""
    b = sessiz_yutma.tara()
    yer = {(x["dosya"], x["fonksiyon"]) for x in b}
    assert ("vehicle_pipeline.py", "measure_yplus") not in yer
    assert ("vehicle_pipeline.py", "prepare_geometry") not in yer
    assert ("vehicle_fea.py", "run_structural_check") not in yer


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
