"""Adaptör — düzelticiyi gerçek araç çözücüsüne bağlayan tek çözücü-bilen katman.

Çözücü ÇAĞRILMAZ: testler `run_vehicle_analysis`'i sahte bir işlevle
değiştirir. Sınanan şey çeviri katmanıdır — sonucun kanıta doğru çevrilip
çevrilmediği ve düzelticinin ürettiği kurulum değişikliğinin doğru çözücü
argümanına gidip gitmediği.
"""
import sys
import types

import duzeltici as D
import duzeltici_adaptor as A


class _Sonuc:
    """VehicleAnalysisResult'ın adaptörün okuduğu alanları."""

    # Adaptör bu alanları okur; `hizmet.analiz_et` üzerinden geçen kuyruk yolu
    # ise ayrıca sınıflandırma için araç/hız/açı ister. Sahte sonuç ikisini de
    # taşımalı, yoksa test gerçek bir kusuru değil kendi eksikliğini ölçer.
    status = "ok"
    vehicle_type = "ucak"
    velocity = 30.0
    alpha_deg = 0.0
    ld = 1.0
    aref_m2 = 0.1
    drag_N = 10.0
    belirsizlik = {}
    mesh = {}
    convergence = {}
    fizik_kabul = {"verdict": "ok", "reasons": []}
    report = ""
    error = ""

    def __init__(self, cd=0.30, cl=0.1, yplus=None, p=None, uyarilar=None,
                 katman=0, case_dir=""):
        self.cd, self.cl = cd, cl
        self.case_dir = case_dir
        self.uyarilar = uyarilar or []
        self.sinir_tabaka = {"katman_sayisi": katman, "yplus": yplus or {}}
        self.mesh_duyarlilik = {"gci": {"p": p}} if p is not None else {}


def test_kanit_kur_ALANLARI_dogru_cevirir():
    r = _Sonuc(cd=0.42, cl=1.2, yplus={"ort": 0.009}, p=0.2,
               uyarilar=["çözüm sigFpe ile durdu"])
    k = A.kanit_kur(r)
    assert k["olculen"]["Cd"] == 0.42
    assert k["olculen"]["yplus"]["ort"] == 0.009
    assert k["olculen"]["gozlenen_mertebe"] == 0.2
    assert k["olculen"]["sigFpe"] is True


def test_duvar_islemi_VAKADAN_okunur_ayardan_DEGIL(tmp_path):
    """Niyet ile gerçeklik ayrışabilir: n_layers>0 duvarın çözüldüğünü kanıtlamaz."""
    (tmp_path / "0").mkdir()
    (tmp_path / "0" / "nut").write_text(
        "boundaryField { airfoil { type nutLowReWallFunction; } }", encoding="utf-8")
    assert A._duvar_islemi_oku(tmp_path) == "nutLowReWallFunction"
    assert A._duvar_islemi_oku(None) == ""
    assert A._duvar_islemi_oku(tmp_path / "yok") == ""


def _sahte_hat(monkeypatch, sonuclar):
    """`vehicle_pipeline.run_vehicle_analysis`'i sıradan sahte sonuçlarla değiştir."""
    gelen = iter(sonuclar)
    cagrilar = []

    def sahte(stl, **kw):
        cagrilar.append(kw)
        return next(gelen)

    mod = types.ModuleType("vehicle_pipeline")
    mod.run_vehicle_analysis = sahte
    monkeypatch.setitem(sys.modules, "vehicle_pipeline", mod)
    return cagrilar


def test_dusuk_Re_duzeltmesi_AG_ARGUMANLARINA_cevrilir(monkeypatch):
    """`nut_wall` doğrudan bir çözücü argümanı değil; araç hattında AĞ üzerinden
    uygulanır. Çeviri yapılmazsa düzeltme sessizce etkisiz kalırdı."""
    ilk = _Sonuc(cd=0.40, yplus={"ort": 0.009})       # duvar fonksiyonu + ince ağ
    ikinci = _Sonuc(cd=0.31, yplus={"ort": 0.8})
    cagrilar = _sahte_hat(monkeypatch, [ilk, ikinci])
    monkeypatch.setattr(A, "_duvar_islemi_oku", lambda c: "nutkWallFunction")

    r, s = A.duzelterek_analiz("x.stl", referans=0.30, n_layers=0)
    assert len(cagrilar) == 2                     # ilk koşu + düzeltilmiş koşu
    assert cagrilar[1]["n_layers"] >= 10          # katman istendi
    assert cagrilar[1]["yplus_target"] == 1.0     # düşük-Re hedefi
    assert s.mudahaleler[0].duzeltme == "duvar_islemini_aga_uydur"


def test_ON_KOSULSUZ_duzeltme_cozucuyu_HIC_cagirmaz(monkeypatch):
    """sigFpe var ama kaba çözüm yok: yeniden koşu YAPILMAMALI, gerekçe yazılmalı."""
    cagrilar = _sahte_hat(monkeypatch, [_Sonuc(uyarilar=["sigFpe"])])
    r, s = A.duzelterek_analiz("x.stl", referans=0.30)
    assert len(cagrilar) == 1                     # yalnız ilk koşu
    assert s.mudahaleler == []
    assert [ad for ad, _ in s.engellenenler] == ["rampali_baslangic"]


def test_fiziksel_olmayan_sonuc_YENIDEN_KOSMADAN_dusurulur(monkeypatch):
    """Cd<0 bir kurulum kusuru değil, ıraksama; yeniden koşmak para yakmaktır."""
    cagrilar = _sahte_hat(monkeypatch, [_Sonuc(cd=-0.019)])
    r, s = A.duzelterek_analiz("x.stl", referans=0.30)
    assert len(cagrilar) == 1
    assert s.sinif == D.OUT


def test_REFERANSSIZ_kosuda_duzeltme_BASARILI_sayilmaz(monkeypatch):
    """Referans yoksa iyileşme ölçülemez; düzeltici bunu 'işe yaradı' DEMEZ."""
    _sahte_hat(monkeypatch, [_Sonuc(cd=0.40, yplus={"ort": 0.009}),
                             _Sonuc(cd=0.31, yplus={"ort": 0.8})])
    monkeypatch.setattr(A, "_duvar_islemi_oku", lambda c: "nutkWallFunction")
    r, s = A.duzelterek_analiz("x.stl")            # referans YOK
    assert s.mudahaleler[0].ise_yaradi is None
    assert "ölçülemedi" in s.mudahaleler[0].ozet()


# ── GUI yolu ──────────────────────────────────────────────────────────────────
def test_worker_duzeltici_KAPALIYKEN_normal_yolu_kullanir(monkeypatch):
    """Varsayılan davranış DEĞİŞMEMELİ: kutu kapalıyken düzeltici hiç yüklenmez."""
    import app_analyzer as app
    cagrilar = []
    monkeypatch.setattr(app, "run_vehicle_analysis",
                        lambda **kw: (cagrilar.append(kw), _Sonuc())[1])
    w = app.AnalysisWorker({"stl_path": "x.stl", "velocity": 30.0,
                            "duzeltici": False})
    w.finished_ok = type("S", (), {"emit": staticmethod(lambda r: None)})()
    w.failed = type("S", (), {"emit": staticmethod(lambda m: None)})()
    w.progress = type("S", (), {"emit": staticmethod(lambda p, m: None)})()
    _Sonuc.status = "ok"
    w.run()
    assert len(cagrilar) == 1
    assert "duzeltici" not in cagrilar[0], "yol seçimi çözücüye SIZDI"


def test_worker_duzeltici_ANAHTARINI_cozucuye_GECIRMEZ(monkeypatch):
    """`duzeltici` bir çözücü argümanı değil; geçerse TypeError olurdu."""
    import inspect

    import vehicle_pipeline as vp
    imza = inspect.signature(vp.run_vehicle_analysis).parameters
    assert "duzeltici" not in imza, (
        "run_vehicle_analysis 'duzeltici' kabul ediyor — worker'daki pop "
        "gereksizleşti, ama sessizce iki yol ayrışmasın diye test uyarır")


# ── Rapor katmanı ─────────────────────────────────────────────────────────────
def _sonuc_ile(mudahale=(), engellenen=(), verdikt="test"):
    s = D.DuzelticiSonuc(sinif=D.TREND, verdikt=verdikt)
    s.mudahaleler = list(mudahale)
    s.engellenenler = list(engellenen)
    return s


def test_rapor_duzeltici_KAPALIYKEN_hic_bolum_yazmaz():
    """Kapalı bir özellik rapora gürültü eklememeli."""
    from vehicle_report import _duzeltici_bolumu
    assert _duzeltici_bolumu(None) == []


def test_rapor_ACIK_ama_kusursuz_kosuyu_da_SOYLER():
    """'guard baktı, bir şey bulmadı' ile 'guard hiç bakmadı' aynı şey değil."""
    from vehicle_report import _duzeltici_bolumu
    md = "\n".join(_duzeltici_bolumu(_sonuc_ile()))
    assert "tetiklenen bir kusur bulunmadı" in md


def test_rapor_ETKISIZ_duzeltmeyi_GIZLEMEZ():
    """Kusur giderildi ama sapma sürüyorsa rapor bunu açıkça yazmalı."""
    from vehicle_report import _duzeltici_bolumu
    m = D.Mudahale("duvar_islemini_aga_uydur", "…", {"nut_wall": "nutLowRe"},
                   39.6, 39.2, False, "Ağ gradasyonunu geçersiz kılar")
    md = "\n".join(_duzeltici_bolumu(_sonuc_ile([m])))
    assert "etkisiz" in md
    assert "Kusuru gidermek nedeni bulmak değildir" in md
    assert "gradasyon" in md, "yan etki raporlanmadı"


def test_rapor_ENGELLENEN_kusuru_ve_GEREKCESINI_yazar():
    from vehicle_report import _duzeltici_bolumu
    md = "\n".join(_duzeltici_bolumu(
        _sonuc_ile(engellenen=[("rampali_baslangic", "kaba çözüm BULUNMALI")])))
    assert "elle müdahale" in md.lower()
    assert "kaba çözüm BULUNMALI" in md


def test_kuyruk_yolu_da_duzelticiyi_DESTEKLER(monkeypatch, tmp_path,
                                              bellek_kapisi_acik):
    """Arayüzün iki giriş noktası AYNI yeteneğe sahip olmalı.

    Depoda bunun aynısı bir kez yaşandı: `ref_bump="oto"` kuyruk yoluna
    eklenip ana düğmeye eklenmemişti ve düzeltme beş çağıranın yalnız birine
    ulaşmıştı. `test_giris_noktasi_esdegerligi` o dersin testidir; bu test
    kuyruk worker'ının anahtarı yalnız TAŞIMAKLA kalmayıp KULLANDIĞINI de
    bağlar.
    """
    import kuyruk
    monkeypatch.setattr(kuyruk, "KUYRUK", tmp_path / "k.jsonl")
    monkeypatch.setattr(kuyruk, "KILIT", tmp_path / "k.lock")
    cagrilar = _sahte_hat(monkeypatch, [_Sonuc(cd=0.40, yplus={"ort": 0.009}),
                                        _Sonuc(cd=0.31, yplus={"ort": 0.8})])
    monkeypatch.setattr(A, "_duvar_islemi_oku", lambda c: "nutkWallFunction")
    _Sonuc.status, _Sonuc.belirsizlik, _Sonuc.report, _Sonuc.error = "ok", {}, "", ""

    kuyruk.ekle({"stl_path": "x.stl", "velocity": 30.0, "duzeltici": True})
    ozet = kuyruk.calis(once=True)
    assert ozet["bitti"] == 1
    assert len(cagrilar) == 2, "kuyruk düzelticiyi kullanmadı (tek koşu)"
