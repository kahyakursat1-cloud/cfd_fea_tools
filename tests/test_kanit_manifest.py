"""Kanıt manifesti — "bu araç neyi doğrulanmış biliyor?" sorusunun tek cevabı.

Kökte 50+ JSON var, isimlendirme tutarsız (gci_cgrid_base/mid/fine/xfine/final/finding…)
ve indeks yoktu; mühendis dosya adı tahmin ederek kanıt arıyordu. Manifest dosyaları
sınıflar (kanıt / artefakt / kaynak / bozuk) ve kanıtları hükümleriyle listeler.
"""
import json

import kanit


def test_gercek_kanit_dosyalari_siniflaniyor():
    m = {k["dosya"]: k for k in kanit.manifest()}
    for ad in ("fea_validation.json", "fea_validation_hole.json", "tmr_gci_verdict.json",
               "gci_kup_arac.json"):
        assert m[ad]["sinif"] == "kanit", f"{ad} kanıt sayılmadı"
        assert m[ad]["hukum"], f"{ad} hükümsüz görünüyor"


def test_artefaktlar_kanit_sayilmaz():
    """Öğrenme kütüphanesi / tarama çıktısı doğrulama kanıtı DEĞİLDİR."""
    m = {k["dosya"]: k for k in kanit.manifest()}
    for ad in ("batch_learn_done.json", "aoa_polar.json", "regresyon_sonuc.json"):
        if ad in m:
            assert m[ad]["sinif"] != "kanit", f"{ad} yanlışlıkla kanıt sayıldı"


def test_materials_kaynak_olarak_isaretli():
    m = {k["dosya"]: k for k in kanit.manifest()}
    assert m["materials.json"]["sinif"] == "kaynak"


def test_hukum_sembolu_normallesiyor():
    assert kanit._hukum({"sonuc": "GECTI — analitik ile uyumlu"})[0] == "✅"
    assert kanit._hukum({"verdikt": "⚠️ Mesh bağımsızlığı GÖSTERİLEMEDİ: p dışı"})[0] == "⚠️"
    assert kanit._hukum({"sonuc": "KALDI — band dışı"})[0] == "❌"
    assert kanit._hukum({})[0] == "—"


def test_hukum_onceligi():
    """Kesin (strict) verdikt varsa düzyazı `sonuc`'a değil ona bakılır."""
    d = {"strict_gci_verdict": "⚠️ GÖSTERİLEMEDİ", "sonuc": "GECTI — güzel uyum"}
    assert kanit._hukum(d)[0] == "⚠️"


def test_bom_lu_dosya_okunabilir(tmp_path, monkeypatch):
    """PowerShell çıktısı BOM taşır; düz utf-8 okuma JSONDecodeError verirdi."""
    p = tmp_path / "bomlu.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"vaka": "x", "sonuc": "GECTI"}).encode())
    assert kanit._oku(p) == {"vaka": "x", "sonuc": "GECTI"}
    monkeypatch.setattr(kanit, "ROOT", tmp_path)
    k = kanit.sinifla(p)
    assert k["sinif"] == "kanit" and k["sembol"] == "✅"


def test_bozuk_dosya_sebebiyle_raporlanir(tmp_path):
    p = tmp_path / "bozuk.json"
    p.write_text("{ bu json degil", encoding="utf-8")
    k = kanit.sinifla(p)
    assert k["sinif"] == "bozuk" and "JSONDecodeError" in k["not"]


def test_eskimis_dosya_isaretlenir(tmp_path):
    p = tmp_path / "eski.json"
    p.write_text(json.dumps({"vaka": "x", "sonuc": "GECTI", "_SUPERSEDED": "yeni: y.json"}),
                 encoding="utf-8")
    k = kanit.sinifla(p)
    assert k["eskimis"] and "ESKİMİŞ" in k["not"]


def test_tablo_bozuk_dosyalari_ayri_listeler():
    t = kanit.tablo(kanit.manifest(), yalniz_kanit=True)
    assert "| Dosya | Vaka | Hüküm |" in t and "**Özet:**" in t


def test_zarf_bom_dayanikli():
    """Zarf da kanıt okur; BOM'lu bir kanıt dosyası tabloyu düşürmemeli."""
    import inspect

    import zarf
    assert "utf-8-sig" in inspect.getsource(zarf._json)


def test_uretim_komutu_cikarilir():
    """Yeniden-üretilebilirlik yayın/hakem için kritik: kanıtı hangi komut üretti?"""
    assert kanit._uretim_komutu({"_not": "Uretim: python experiments/fea_validation.py"}) \
        == "python experiments/fea_validation.py"
    # nokta komutun PARÇASI (vehicle_pipeline.py) — cümle sonuyla karıştırılmamalı
    uzun = {"_u": "Üretim: python vehicle_pipeline.py x.stl --tip genel. Not: 4 seviye"}
    assert kanit._uretim_komutu(uzun) == "python vehicle_pipeline.py x.stl --tip genel"
    assert kanit._uretim_komutu({"vaka": "komut yok"}) == ""


def test_uretim_komutu_olmayan_kanit_eksik_sayilir(tmp_path):
    import json as _j
    p = tmp_path / "kanitsiz.json"
    p.write_text(_j.dumps({"vaka": "x", "sonuc": "GECTI"}), encoding="utf-8")
    assert kanit.sinifla(p)["uretim"] == ""


def test_tablo_yeniden_uretim_sutunu_tasir():
    t = kanit.tablo(kanit.manifest())
    assert "Yeniden üretim" in t and "Yeniden üretilebilir:" in t


def test_bilinen_kanitlar_komut_kaydediyor():
    """FEA doğrulama ailesi bu geleneği kurdu — regresyon çapası."""
    m = {k["dosya"]: k for k in kanit.manifest()}
    for ad in ("fea_validation.json", "fea_validation_hole.json", "gci_kup_arac.json"):
        assert m[ad]["uretim"].startswith("python"), f"{ad} üretim komutunu kaybetti"


def test_ic_ice_hukum_alanlari_bulunur():
    """Kanıt dosyaları tek şemaya uymuyor: kimi `sonuc`, kimi `degerlendirme`,
    kimi `ozet.yorum` altında hüküm veriyor. Yalnız üst düzeye bakmak, hükmü OLAN
    dosyaları 'hükümsüz' göstererek manifesti yanıltıyordu."""
    assert kanit._hukum({"ozet": {"yorum": "C3D4 sehimi %58 düşük tahmin"}})[1].startswith("C3D4")
    assert kanit._hukum({"degerlendirme": "shockFluid mimarisi çalışıyor"})[1].startswith("shock")
    assert kanit._hukum({"ozet": {"baska": 1}})[0] == "—"


def test_hukum_turetilen_dosya_eksik_sayilmaz(tmp_path):
    """Üçüncü durum: hüküm bu dosyada saklanmaz ama zarf.py hesaplar. 'YOK' demek
    yanıltıcı olurdu — kanıt eksik değil, hüküm türetilir."""
    import json as _j
    p = tmp_path / "ham.json"
    p.write_text(_j.dumps({"vaka": "x", "levels": [1, 2, 3],
                           "_hukum_kaynagi": "zarf.py hesaplar"}), encoding="utf-8")
    k = kanit.sinifla(p)
    assert k["hukum_turetilir"] is True and k["sembol"] == "↗"
    assert "türetilir" in k["hukum"]


def test_gercek_kanitlarin_hepsi_hukum_tasiyor():
    """Regresyon çapası: kökteki hiçbir kanıt dosyası hükümsüz kalmamalı."""
    hukumsuz = [k["dosya"] for k in kanit.manifest()
                if k["sinif"] == "kanit" and not k["hukum"]]
    assert hukumsuz == [], f"hükümsüz kanıt: {hukumsuz}"


def test_uretim_scripti_cikarilir():
    assert kanit._uretim_scripti("python experiments/fea_validation.py") \
        == "experiments/fea_validation.py"
    assert kanit._uretim_scripti("python vehicle_pipeline.py x.stl --tip genel") \
        == "vehicle_pipeline.py"
    assert kanit._uretim_scripti("kabuk komutu") == ""


def test_bagimli_kod_import_zincirini_izler():
    """`analysis/` KLASÖRÜNÜN tamamıyla kıyaslamak yanlış: FEA kanıtı calculix/frd
    yoluna bağlıdır, openfoam_runner'a değil. Her CFD değişikliği tüm FEA kanıtlarını
    'bayat' ilan ederse sinyal gürültüye gömülür."""
    zincir = kanit._bagimli_kod("check_vehicle_validation.py")
    assert "check_vehicle_validation.py" in zincir
    assert "vehicle_pipeline.py" in zincir, "doğrudan import izlenmedi"

    fea = kanit._bagimli_kod("experiments/fea_validation.py")
    assert not any("openfoam_runner" in y for y in fea), \
        "FEA zinciri CFD çözücüsüne bağlanmamalı"


def test_bayatlik_kesin_ve_tahmin_ayrimi():
    """Üretim komutu kayıtlı olan KESİN, olmayan TAHMİN olarak işaretlenir."""
    b = kanit.bayatlik(kanit.manifest())
    assert all("kesin" in x and "kiyas" in x and "bayat_gun" in x for x in b)
    for x in b:
        if x["kesin"]:
            assert x["kiyas"].endswith(".py")


def test_bayat_isareti_hukum_degil():
    """`--bayat` 'yanlış' demez, 'doğrula' der: altı FEA çapası bu işareti taşırken
    yeniden koşulduğunda BİREBİR aynı çıktı (2026-07-27). Metin bunu yansıtmalı."""
    import inspect
    src = inspect.getsource(kanit.main)
    assert "olabilir" in src, "kesin hüküm gibi sunulmamalı"


def test_komsu_alan_uretim_komutunu_bozmaz():
    """REGRESYON: değerler birleştirilerek taranınca komşu alan komutun peşine yapışıp
    uzunluk sınırını aştırıyor ve eşleşme TAMAMEN kayboluyordu (_son_dogrulama
    eklenince fea_validation.json'da yaşandı). Her alan ayrı taranmalı."""
    d = {"_not": "…dogrulandi. Uretim: python experiments/fea_validation.py",
         "_son_dogrulama": "2026-07-27 — yeniden koşuldu; sonuç " + "x" * 200}
    assert kanit._uretim_komutu(d) == "python experiments/fea_validation.py"


def test_hicbir_belge_erisilemez_kalmaz():
    """INDEX.md belge haritasıdır; listede olmayan sayfa pratikte kayıptır.
    (Kendi bakım listesindeki 'orphaned pages' maddesinin makine kontrolü.)"""
    from pathlib import Path
    kok = Path(kanit.__file__).resolve().parent
    idx = (kok / "INDEX.md").read_text(encoding="utf-8")
    eksik = [p.name for p in kok.glob("*.md")
             if p.name != "INDEX.md" and p.name not in idx]
    assert eksik == [], f"INDEX.md'de olmayan belge: {eksik}"


def test_uretim_regexi_python_disi_komutlari_taniyor():
    """NX journal kanıtları `run_journal.exe …` ile üretilir ve regex YALNIZ `python`
    kabul ediyordu → kanıtta komut YAZILI olduğu halde manifest "kayıtlı değil" diyordu.
    Ortam değişkenli koşular (NX_AILE=kor python …) da aynı delikten düşüyordu."""
    ok = [
        'Üretim: python experiments/duz_levha_cf.py',
        'Üretim: NX_OLC=kor python experiments/nx_siniflandirici_testi.py',
        ('Üretim: "C:/Program Files/Siemens/NX2412/NXBIN/run_journal.exe" '
         'experiments/nx_geometri_uret.py'),
        'Üretim: run_journal.exe experiments/nx_geometri_uret.py && python x.py',
    ]
    for m in ok:
        assert kanit._uretim_komutu({"_uretim": m}), m


def test_uretim_regexi_duz_metni_komut_saymiyor():
    """Gevşetme, prozayı komut sanacak kadar ileri gitmemeli."""
    for m in ("Üretim: elle hesaplandı", "Üretim: ölçüm laboratuvarda yapıldı"):
        assert not kanit._uretim_komutu({"_uretim": m}), m


def test_uretici_kod_yoklugu_ayri_isaretleniyor():
    """'Komut kayıtlı değil' iki ayrı durumu gizliyordu: (a) script duruyor, not
    düşülmemiş — bir satırlık iş; (b) üretici kod depoda HİÇ YOK — kanıt gerçekten
    yeniden üretilemez. İkincisi çok daha ağır ve ayrı görünmeli."""
    assert kanit.uretici_kod_var("duz_levha_cf.json") is True
    assert kanit.uretici_kod_var("bu_dosya_hicbir_yerde_yazilmiyor_xyz.json") is False


def test_manifest_uretilemez_kaniti_acikca_soyluyor():
    """İki durum manifest metninde AYRI ifade edilmeli — ve "üretici var" hâlinde
    YOLU da yazılmalı: ölçüldü ki bool cevap, komutu yazmak için yetmiyor
    (10 "yeniden üretilemez" kanıdın 8'inin üreticisi duruyordu)."""
    import inspect
    src = inspect.getsource(kanit)
    assert "ÜRETİCİ KOD DEPODA YOK" in src
    assert "komut kayıtlı değil — üretici:" in src
    assert "x['uretici']" in src


def test_dogrulama_damgasi_bayatligi_temizliyor(tmp_path, monkeypatch):
    """ASIL KUSUR: kanıt yeniden koşulup sonuç BİREBİR AYNI çıkarsa git yeni commit
    görmez ve dosya sonsuza dek "bayat" kalır — "hiç koşulmadı" ile "koşuldu ve
    doğrulandı" ayırt edilemiyordu. `_son_dogrulama` alanı ZATEN yazılıyordu (4
    dosyada) ama `bayatlik()` onu HİÇ OKUMUYORDU: bu oturumda avlanan desenin
    kendisi, üstelik bu projenin kendi kanıt aracında."""
    kayit = {"dosya": "x.json", "sinif": "kanit", "uretim": "", "dogrulama_ts": 0}
    monkeypatch.setattr(kanit, "_git_tarih",
                        lambda y: 1000 if y == "x.json" else 2000)
    assert kanit.bayatlik([kayit]), "damgasız kanıt bayat sayılmalı"
    assert not kanit.bayatlik([{**kayit, "dogrulama_ts": 2500}]), (
        "üreten koddan YENİ damga bayatlığı temizlemeli")
    assert kanit.bayatlik([{**kayit, "dogrulama_ts": 1500}]), (
        "üreten koddan ESKİ damga bayatlığı temizlememeli")


def test_damgala_alani_yaziyor(tmp_path, monkeypatch):
    import json as _json
    p = tmp_path / "k.json"
    p.write_text(_json.dumps({"vaka": "t"}), encoding="utf-8")
    monkeypatch.setattr(kanit, "ROOT", tmp_path)
    assert kanit.damgala(["k.json"]) == 1
    d = _json.loads(p.read_text(encoding="utf-8"))
    assert d["_son_dogrulama_ts"] > 0 and "yeniden" in d["_son_dogrulama"]


def test_komutsuz_kanit_MUTLAKA_beyan_tasir():
    """KURAL: üretim komutu olmayan her kanıt, NEDEN olmadığını beyan etmeli.

    Beyanlı eksik ile sessiz eksik AYRI şeylerdir ve manifest ikisini aynı
    gösteriyordu. Bu 2026-08-20'de somut zarar verdi: `gci_cgridP_*` dosyaları
    "üreticisi yok, ölü" sanılıp SİLİNMESİ önerildi — oysa üreticileri
    (`exp_cgrid_run_parallel.py`; dosya adını f-string kurduğu için düz metin
    araması bulamıyor) de tam beyanları da vardı.

    Test dosya ADI pinlemez: komutsuz olan HANGİSİ olursa olsun beyan aranır.
    """
    komutsuz = [k for k in kanit.manifest()
                if k["sinif"] == "kanit" and not k.get("uretim")]
    sessiz = [k["dosya"] for k in komutsuz if not k.get("uretim_beyanli")]
    assert sessiz == [], (
        "Bu kanıtların üretim komutu YOK ve neden olmadığı da yazılmıyor; "
        f"'yeniden üretilemez' hükmü verilemez: {sessiz}")
    for k in komutsuz:
        assert k.get("uretim_beyani"), f"{k['dosya']}: beyan boş"
        # Beyan GEREKÇE tasimali, tek kelime degil
        assert len(k["uretim_beyani"]) > 40, k["dosya"]
