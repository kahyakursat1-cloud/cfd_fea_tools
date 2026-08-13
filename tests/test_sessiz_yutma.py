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
#
# 2026-07-29 — TABAN 80 → 81 (güven yolu 55 → 56). Bu bir GERİLEME DEĞİL, kasıtlı
# bir SAVUNMA eklemesi: `mesh_quality_gate` sayı ayrıştırması artık `float()`
# hatasını yakalıyor. Gerekçe: eski regex `([\d.eE+]+)` eksi üssü kapsamıyordu ve
# "Max skewness = 9.8987286e-05" TÜM analizi ValueError ile düşürüyordu — yani
# kalite kapısı MESH İYİYKEN patlıyordu (güvenilirlik taramasında 12 geometrinin
# 3'ü böyle kayboldu). Yakalanan hata "sorun yok" SAYILMIYOR: None dönüyor ve kapı
# onu "okunamadı" olarak reddediyor (2eb2686'nın dersi korundu).
# Asıl izlenen sayılar DEĞİŞMEDİ: incelenmemiş 25, güven yolunda incelenmemiş 0.
#
# 2026-08-01 — TABAN 81 → 82 (güven yolu 56 → 57). Yine GERİLEME DEĞİL: `_cozucu_yasiyor`
# içindeki sorgu hatası yutuluyor ve gerekçesi kodda yazılı — sorgulanamıyorsa
# "yaşamıyor" varsayılır, en kötü hâl ESKİ davranıştır (erken okuma) ve yeni bir
# asılma riski getirmez. Bu savunma, çözücü bitmeden kuvvet tarihçesi okunmasını
# engelleyen yarış-durumu düzeltmesinin parçasıdır (8cdb221).
# Asıl izlenen sayılar yine DEĞİŞMEDİ: incelenmemiş 25, güven yolunda incelenmemiş 0.
#
# 2026-08-02 — TABAN 82 → 83. Yine GERİLEME DEĞİL: eski motora (`simulation_runner`)
# araç hattının KAPILARI takılırken `_kuvvet_tarihcesi` içinde bozuk bir forces.dat
# satırı atlanıyor ve gerekçesi kodda yazılı. Tarihçe TEŞHİS içindir (drift/salınım);
# tek bozuk satır kalan noktalarla kurulan teşhisi düşürmez, ve SON satır ayrıca
# SERT ayrıştırılıp hatası `kuvvet_cikarim_hatasi` olarak raporlanır — yani Cd/Cl
# üreten yol sessiz DEĞİL.
# Aynı commit'teki diğer iki `except` bloğu sayıya GİRMEDİ çünkü sebebi KAYDEDİYORLAR
# (`convergence_hatasi`, `yuzey_cozunurlugu_hatasi`) — tarayıcı bunu doğru ayırıyor.
# Asıl izlenen sayılar DEĞİŞMEDİ: incelenmemiş 25, güven yolunda incelenmemiş 0.
#
# 2026-08-02 (2) — TABAN 83 → 84. GERİLEME DEĞİL: XFOIL kesit yolu eklendi ve
# `_oku_polar` tablonun BAŞLIK satırlarını (alpha/CL/CD, ---- ayracı) atlıyor.
# Bunlar sayıya çevrilemez; atlanmaları beklenen davranıştır ve veri KAYBI
# oluşturmaz — istenen ile dönen açılar ayrıca karşılaştırılıp eksik açı
# `yakinsamayan_alfa` olarak RAPORLANIR (XFOIL yakınsamayan açıyı tabloya hiç
# yazmaz, yani boş satır "denenmedi" değil "YAKINSAMADI" demektir).
# İzlenen sayılar DEĞİŞMEDİ: incelenmemiş 25, güven yolunda incelenmemiş 0.
#
# 2026-08-02 (3) — TABAN 84 → 85. GERİLEME DEĞİL: VLM çapası (`vlm_capa.py`)
# VSPAERO'nun varsayılan panel yoğunluğunun YAKINSAMAMIŞ olduğunu ölçtü (span
# verimi e=1.0788 — eliptik üst sınır 1.0, yani fiziksel olarak imkânsız; 40
# panelde e=0.9954). Düzeltme `run_vspaero_polar` içinde kanat geometrilerine
# SectTess_U atıyor; her geometri bu parmı taşımayabilir ve o durumda VARSAYILAN
# panelle devam edilir. Gerekçe kodda: sonuç yine üretilir, yalnız band genişler.
# Alternatif (sert hata) mevcut çalışan akışları kırardı.
# İzlenen sayılar DEĞİŞMEDİ: incelenmemiş 25, güven yolunda incelenmemiş 0.
# 2026-08-07 — GUVEN YOLU 57 → 58. GERILEME DEGIL: silindir girdap-dokulmesi
# capasi (`experiments/silindir_vorteks.py`) forceCoeffs.dat'i okuyor ve yarim
# yazilmis SON SATIRI atliyor — kosu surerken dosya okunursa olagan bir durum.
# Hicbir satir okunamazsa cagiran "olculemedi" hukmu veriyor, yani bos sonuc
# basari sayilmiyor. Gerekce kodda yazili.
# Izlenen sayilar DEGISMEDI: incelenmemis 0, guven yolunda incelenmemis 0.
#
# 2026-08-12 — TABAN 85 → 87 (guven yolu 58 → 60). GERILEME DEGIL, iki savunma:
# (1) `basarim_matrisi._cozucu_exec_s` foamRun log'undan ExecutionTime ayristirir
#     ve bozuk satiri atlar; okunabilen SON deger doner, hic okunamazsa None ve
#     hizlanma hesabi o kosuyu DISARIDA birakir — uydurma sayi uretilmez.
# (2) `rapor_figurleri.fig_basarim_matrisi` ikinci govdenin matrisi yoksa o
#     govdeyi figurden duser. "Geometriden bagimsiz" hukmunu figur DEGIL
#     `test_iki_govde_de_olculmus` bagliyor.
# Ikisi de yeni bir olcum yolunun parcasi: hizlanma artik ASAMA DUVAR SURESINDEN
# degil ExecutionTime'dan hesaplaniyor (rapordaki 1,96x → 3,10x duzeltmesi).
# Izlenen sayilar DEGISMEDI: incelenmemis 0, guven yolunda incelenmemis 0.
TABAN_TOPLAM = 87
# 60 -> 61 (2026-08-13): experiments/naca0012_a8_rampali.py:_forces_oku.
# OpenFOAM surumleri coefficient.dat ile forceCoeffs.dat arasinda sutun
# sayisini degistiriyor; okuyucu aday dosyalari sirayla dener. Yutma
# GEREKCELI (kabul etiketi konuldu) ve hicbiri tutmazsa (None, None)
# donuyor, yani hata kaybolmuyor.
# 61 -> 62 (2026-08-13): experiments/model_form_bandi.py:_arsivden_kurtar.
# validation_anchors_runs disk temizliginde silinince kup capasinin y+'i
# okunamaz oldu; deger arsiv ciktisindan kurtariliyor. Arsiv dosyasi bozuksa
# kurtarma yapilmaz ve capa ATLANIR — yutma GEREKCELI, hata kaybolmuyor
# cunku test_model_form_tek_capa olculmemis hucreyi zaten yakaliyor.
TABAN_GUVEN_YOLU = 62
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
