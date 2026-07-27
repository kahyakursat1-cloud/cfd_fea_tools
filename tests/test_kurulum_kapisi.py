"""Kurulum kapısı — yanlış KURULMUŞ analiz, sonuç kapılarının hepsini geçer.

Ölçek/eksen/referans-alan hatası fiziksel olarak makul bir sayı üretir: Cd pozitif,
mertebe doğru, mesh temiz, iterasyon yakınsamış. Hiçbir sonuç kontrolü yakalayamaz
çünkü sayı doğrudur — sadece BAŞKA bir problemin cevabıdır. Bu yüzden girdi çözücüden
önce denetlenir.
"""
import pytest

from validity_envelope import geometry_sanity


def _geo(L=1.0, on=0.05, yan=0.4, plan=0.5, ucgen=5000, keskin=0.3):
    return {"lmax_m": L, "on_alan_m2": on, "yan_alan_m2": yan,
            "planform_alan_m2": plan, "ucgen_sayisi": ucgen,
            "keskin_kenar_orani": keskin, "boyutlar_m": [L, L * 0.8, L * 0.2]}


def test_saglikli_kurulum_sessiz():
    assert geometry_sanity(_geo(), "ucak", velocity=30.0) == []


# ── Ölçek ────────────────────────────────────────────────────────────────────

def test_mm_olcegi_yakalanir():
    """1.2 m'lik İHA mm cinsinden ihraç edilirse 1200 m görünür."""
    u = geometry_sanity(_geo(L=1200.0, on=50000, yan=400000, plan=500000), "ucak", 30.0)
    assert any("ÖLÇEK ŞÜPHESİ" in s for s in u)
    assert any("1.200 m" in s for s in u), "doğru m karşılığı önerilmeli"


def test_asiri_kucuk_model_yakalanir():
    u = geometry_sanity(_geo(L=0.002, on=1e-5, yan=8e-5, plan=1e-4), "genel", 30.0)
    assert any("ÖLÇEK ŞÜPHESİ" in s and "mm" in s for s in u)


def test_dusuk_reynolds_uyarisi():
    """Küçük ölçek + düşük hızda RANS türbülans varsayımı zayıflar."""
    u = geometry_sanity(_geo(L=0.01), "genel", velocity=1.0)
    assert any("Re =" in s and "1e4" in s for s in u)


def test_normal_reynolds_sessiz():
    assert not any("Re =" in s for s in geometry_sanity(_geo(L=1.0), "genel", 30.0))


# ── Eksen ────────────────────────────────────────────────────────────────────

def test_dikey_modellenmiş_roket_yakalanir():
    """Dikey modellenmiş roket: akış ekseni gövde boyunca değil, tabanına bakar
    → frontal izdüşüm üç izdüşümün en büyüğü olur."""
    u = geometry_sanity(_geo(on=0.5, yan=0.08, plan=0.08), "roket", 30.0)
    assert any("EKSEN ŞÜPHESİ" in s for s in u)


def test_dogru_eksende_roket_sessiz():
    u = geometry_sanity(_geo(on=0.008, yan=0.3, plan=0.3), "roket", 30.0)
    assert not any("EKSEN ŞÜPHESİ" in s for s in u)


def test_kut_cisimde_eksen_uyarisi_verilmez():
    """Küpte frontal en büyük olabilir — bu normal, yanlış alarm verme."""
    u = geometry_sanity(_geo(on=0.5, yan=0.5, plan=0.5), "genel", 30.0)
    assert not any("EKSEN ŞÜPHESİ" in s for s in u)


# ── Referans alan ────────────────────────────────────────────────────────────

def test_ucak_tipi_kut_cisimde_uyarir():
    """tip='ucak' planform A_ref alır; kanat benzeri olmayan gövdede Cd alan
    oranı kadar yanlış çıkar."""
    u = geometry_sanity(_geo(on=0.4, yan=0.45, plan=0.5), "ucak", 30.0)
    assert any("REFERANS ALAN ŞÜPHESİ" in s for s in u)
    assert any("--tip genel" in s for s in u), "düzeltme yolu gösterilmeli"


def test_gercek_kanat_sessiz():
    u = geometry_sanity(_geo(on=0.03, yan=0.2, plan=0.5), "ucak", 30.0)
    assert not any("REFERANS ALAN" in s for s in u)


def test_narin_olmayan_roket_uyarir():
    u = geometry_sanity(_geo(on=0.2, yan=0.3, plan=0.3), "roket", 30.0)
    assert any("GEOMETRİ ŞÜPHESİ" in s for s in u)


# ── Pürüzsüz gövde: bu hattın bilinen sistematik sınırı ──────────────────────

def test_puruzsuz_govde_duvar_fonksiyonuyla_uyarir():
    """Küre/kapsül gibi gövdede ayrılma geçiş-güdümlüdür; tam-türbülanslı RANS
    sistematik şaşırır (projenin küreyi doğrulama vakası olarak reddetme gerekçesi)."""
    u = geometry_sanity(_geo(keskin=0.0), "genel", 30.0, n_layers=0)
    assert any("PÜRÜZSÜZ GÖVDE" in s for s in u)
    assert any("EĞİLİM" in s for s in u), "sonucun düzeyi söylenmeli"


def test_prizma_katmani_varsa_uyari_kalkar():
    assert not any("PÜRÜZSÜZ" in s
                   for s in geometry_sanity(_geo(keskin=0.0), "genel", 30.0, n_layers=5))


def test_keskin_kenarli_cisim_uyarilmaz():
    """Küp 0.67, silindir 0.33 — ayrılma geometrik olarak sabit, uyarı gereksiz."""
    for kk in (0.33, 0.67):
        assert not any("PÜRÜZSÜZ" in s
                       for s in geometry_sanity(_geo(keskin=kk), "genel", 30.0))


def test_keskin_kenar_olcusu_gercek_sekillerde_ayrisir():
    """Eşiğin ampirik dayanağı: pürüzsüz ve keskin cisimler net ayrılmalı."""
    trimesh = pytest.importorskip("trimesh")
    from vehicle_pipeline import _keskin_kenar_orani
    assert _keskin_kenar_orani(trimesh.creation.icosphere(subdivisions=3)) < 0.02
    assert _keskin_kenar_orani(trimesh.creation.box(extents=[1, 1, 1])) > 0.5
    assert _keskin_kenar_orani(trimesh.creation.cylinder(radius=0.2, height=1.0)) > 0.2


# ── Diğer ────────────────────────────────────────────────────────────────────

def test_fasetli_egri_uyarir():
    """Kaba küre (80 üçgen, ara açı dolu) gerçek bir çözünürlük sorunudur."""
    g = _geo(ucgen=80, keskin=0.0)
    g["fasetli_egrilik_orani"] = 1.0
    assert any("ÇÖZÜNÜRLÜĞÜ" in s for s in geometry_sanity(g, "genel", 30.0))


def test_cok_yuzlu_uygun_ucgen_sayisiyla_uyarilmaz():
    """YANLIŞ ALARM DÜZELTMESİ: küp TAM olarak 12 üçgendir — yaklaşım değil, kesin
    geometri. Ara açı oranı 0 (tüm komşu yüzler ya düzlemsel ya keskin) → uyarı yok."""
    g = _geo(ucgen=12, keskin=0.67)
    g["fasetli_egrilik_orani"] = 0.0
    assert not any("ÇÖZÜNÜRLÜĞÜ" in s for s in geometry_sanity(g, "genel", 30.0))


def test_egrilik_olcusu_gercek_sekillerde_ayrisir():
    trimesh = pytest.importorskip("trimesh")
    from vehicle_pipeline import _fasetli_egrilik_orani
    assert _fasetli_egrilik_orani(trimesh.creation.box(extents=[1, 1, 1])) == 0.0
    assert _fasetli_egrilik_orani(trimesh.creation.icosphere(subdivisions=1)) > 0.5


def test_eksik_alan_bilgisi_cokmez():
    assert isinstance(geometry_sanity({}, "ucak", 30.0), list)
    assert isinstance(geometry_sanity({"lmax_m": 1.0}, "genel"), list)


def test_pipeline_kapiyi_cozucuden_once_cagirir():
    """Kapı çözücüden SONRA çağrılırsa saatlik koşu boşa gider."""
    import inspect

    import vehicle_pipeline
    src = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)
    i_kapi = src.index("geometry_sanity(")
    i_cozucu = src.index("run_cfd(")
    assert i_kapi < i_cozucu, "kurulum kapısı run_cfd'den önce çağrılmalı"
    # ...ve uyarılar nihai listenin BAŞINDA olmalı
    assert "uyarilar = list(kurulum_uyarilari)" in src


@pytest.mark.parametrize("tip", ["ucak", "roket", "multikopter", "araba", "genel"])
def test_tum_tiplerde_calisir(tip):
    assert isinstance(geometry_sanity(_geo(), tip, 30.0), list)


def test_kurulum_uyarisi_raporun_en_ustunde(tmp_path, monkeypatch):
    """Yanlış ölçek/eksen aşağıdaki tüm bölümleri geçersizler; okuyucu dört bölüm
    makul sayı okuduktan SONRA öğrenmemeli."""
    from test_fizik_kapisi_uctan_uca import _Sonuc

    import vehicle_report

    r = _Sonuc()
    r.cd, r.cl = 0.032, 0.44
    r.fizik_kabul = {"verdict": "ok", "reasons": []}
    r.kurulum = ["ÖLÇEK ŞÜPHESİ: model 1200 m — mm cinsinden ihraç edilmiş olabilir"]
    r.uyarilar = list(r.kurulum) + ["y⁺ ÖLÇÜLEMEDİ — sınır tabaka doğrulanamadı"]
    for ad in ("_fig_convergence", "_fig_residuals", "_fig_geometry"):
        monkeypatch.setattr(vehicle_report, ad, lambda *a, **k: None, raising=False)
    metin = vehicle_report.build_vehicle_report(r, [], {}, tmp_path).read_text(encoding="utf-8")

    ust = metin.split("## 1. Geometri")[0]
    assert "KURULUM" in ust and "ÖLÇEK ŞÜPHESİ" in ust
    assert metin.count("ÖLÇEK ŞÜPHESİ") == 1, "kurulum uyarısı 4b'de tekrarlanmamalı"
    assert "y⁺ ÖLÇÜLEMEDİ" in metin and "y⁺ ÖLÇÜLEMEDİ" not in ust


def test_otomatik_oryantasyondan_sonra_yanlis_alarm_yok(tmp_path):
    """Kapının en önemli özelliği: MUTLU YOLDA sessiz olmak.

    Kapı, hazırlık+otomatik-oryantasyondan SONRA, çözücünün göreceği geometri
    üzerinde ölçer. Dikey modellenmiş roket otomatik düzeltilirse uyarı VERMEMELİ;
    kullanıcı açık (ve yanlış) eksen verdiyse VERMELİ.
    """
    trimesh = pytest.importorskip("trimesh")
    from vehicle_pipeline import inspect_geometry, prepare_geometry

    m = trimesh.creation.cylinder(radius=0.04, height=1.2, sections=32)   # +z'de dikey
    stl = tmp_path / "dikey_roket.stl"
    m.export(stl)

    def _eksen_uyarisi(auto):
        out = tmp_path / f"o{int(auto)}"
        out.mkdir(exist_ok=True)
        sp, _ = prepare_geometry(stl, out, None, auto_orient=auto)
        g = inspect_geometry(sp)
        return [s for s in geometry_sanity(g, "roket", 30.0) if "EKSEN" in s]

    assert not _eksen_uyarisi(True), "otomatik düzeltilen geometride yanlış alarm"
    assert _eksen_uyarisi(False), "kullanıcı yanlış eksen verdiğinde uyarı gelmeli"


def test_ince_ozellik_onerisi_katmansiz_preseti_gosterir():
    """Uyarı tam olarak İNCE özellik varken çıkar; 'hassas' 12 prizma katmanı ekler ve
    MESH_QUALITY'nin kendi notu katmanın ince firar kenarında güvenle örülemediğini
    söyler. Doğru reçete katmansız yoğun mesh: hassas_nl."""
    from vehicle_pipeline import MESH_QUALITY, resolution_warning

    w = resolution_warning(1.5, 7, 3, 0.08)          # MiniHawk standart: 3.0x
    assert w and "hassas_nl" in w
    assert MESH_QUALITY["hassas_nl"]["n_layers"] == 0
    assert MESH_QUALITY["hassas"]["n_layers"] > 0     # önerilmeyen kol


def test_onerilen_preset_uyariyi_gercekten_kaldirir():
    """Reçete işe yaramalı: önerilen ayarla hesap ≥6 katı vermeli (ölçüldü: 7.7x)."""
    from vehicle_pipeline import MESH_QUALITY, VEHICLE_PRESETS, resolution_warning

    rmax = VEHICLE_PRESETS["ucak"]["refinement"][1]
    q = MESH_QUALITY["hassas_nl"]
    assert resolution_warning(1.5, q["bg_div"], rmax + q["ref_bump"], 0.08) is None


def test_yplus_uyarisi_buyukluge_gore_derecelenir():
    """MiniHawk hassas_nl koşusunda y⁺=4113 ölçüldü — duvar-fonksiyonu bandının
    (~30-300) 13 katı. Buna 'sınırda' demek yanıltıcıdır: sürtünme bileşeni orada
    ÇÖZÜLMÜYOR. Uyarı büyüklüğe göre iki kademeli."""
    import inspect

    import vehicle_pipeline
    src = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)
    assert "_yp > 1000" in src, "y⁺ uyarısı derecelendirilmemiş"
    assert "ÇÖZÜLMÜYOR" in src and "sınırında" in src, "iki kademe de bulunmalı"
    # şiddetli kolda somut reçete verilmeli
    i = src.index("_yp > 1000")
    assert "--katman" in src[i:i + 700]


def test_katman_cokmesi_yakalanir():
    """ÖLÇÜLEN VAKA (MiniHawk 'hassas', 2026-07-27): 12 prizma katmanı istendi, y⁺
    hedefi 1.0 idi; mesh KATMANSIZ koşuyla birebir aynı çıktı (3.943.330 hücre) ve
    y⁺=4113 ölçüldü. snappy günlüğü katman tablosunda yalnız 66 yüz gösteriyor ve
    layerFaces faceSet'ine 0 yüz yazmış — katman adımı sessizce çökmüş.

    Katman İSTENİP alınamamak, hiç istememekten TEHLİKELİDİR: sonuç sahip olmadığı
    sınır-tabaka çözünürlüğünü iddia eder. Eski uyarı `n_layers == 0` koşuluna bağlıydı,
    yani bu vakada HİÇ ÇIKMIYORDU."""
    import inspect

    import vehicle_pipeline
    src = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)
    assert "KATMAN ÇÖKMESİ" in src
    i = src.index("KATMAN ÇÖKMESİ ŞÜPHESİ")
    kosul = src[max(0, i - 400):i]
    assert "n_layers > 0" in kosul, "kapı yalnız katman İSTENDİĞİNDE çalışmalı"
    assert "5 * yplus_target" in kosul, "ölçülen y⁺ HEDEFLE kıyaslanmalı"


def test_katman_cokmesi_esigi_gercek_veriyle_tetiklenir():
    """Ölçülen y⁺=4113, hedef 1.0 → 4113 kat; eşik 5× olduğundan kesin tetikler."""
    yplus_olculen, hedef = 4113.52, 1.0
    assert yplus_olculen > 5 * hedef
    # sağlıklı bir katmanlı koşu (y⁺≈1.2, hedef 1.0) tetiklememeli
    saglikli_yplus = 1.2
    assert saglikli_yplus <= 5 * hedef


def test_kalinlik_olcumu_yedege_dustugunu_soyler():
    """SESSİZ BOZULMA: rtree yoksa ray-kalınlık ölçümü ModuleNotFoundError atıyor,
    `except: pass` yutuyor ve bbox yedeği ÖLÇÜM sanılıyordu. Kaynak artık kayıtlı."""
    trimesh = pytest.importorskip("trimesh")
    from vehicle_pipeline import estimate_thin_thickness, kalinlik_olculdu_mu

    estimate_thin_thickness(trimesh.creation.box(extents=[1, 1, 0.1]))
    k = kalinlik_olculdu_mu()
    assert set(k) == {"olculdu", "neden"}
    if not k["olculdu"]:
        assert k["neden"] and k["neden"] != "henüz çağrılmadı", "sebep kaydedilmemiş"


def test_cozunurluk_uyarisi_olcum_tabanini_bildirir():
    """Ölçülmemiş bir boyuta dayanan uyarı, bunu açıkça söylemeli."""
    from vehicle_pipeline import resolution_warning

    olculen = resolution_warning(1.5, 7, 3, 0.08, olculdu=True)
    yedek = resolution_warning(1.5, 7, 3, 0.08, olculdu=False)
    assert olculen and "ÖLÇÜLMEDİ" not in olculen
    assert yedek and "ÖLÇÜLMEDİ" in yedek and "rtree" in yedek
    assert "firar kenarı" in yedek, "gerçek darboğaz adlandırılmalı"
