"""VLM çapası — VSPAERO'nun taşımasına ÖLÇÜLMÜŞ band verir.

VLM bu depoda hiçbir referansa karşı doğrulanmamıştı; `polar_birlestirme` Cl'i
"literatür-öncül" etiketiyle yayınlıyordu. Çapa o etiketi ölçüme çevirir.

ÖLÇÜT KAPALI-FORM (grafik/tablo değeri KULLANILMAZ):
    1/a_3B = 1/a_2B + (1+τ)/(π·AR)
1/AR'ye karşı doğru olmalı ve KESİŞİMİ 1/a_2B = 1/(2π) vermeli.

ÖLÇÜLEN (dikdörtgen kanat, AR=4/6/8/12, yakınsamış panel):
    R² = 0.99983,  kesişimden a_2B = 6.3601/rad,  2π = 6.2832  → sapma %1.22

VE BİR KUSUR BULDU: varsayılan panelde span verimi e = 1.0788 çıkıyordu —
eliptik yükleme MATEMATİKSEL ÜST SINIRDIR (e=1), yani fiziksel olarak imkânsız.
Panel taraması ayrımı yaptı: 12→1.0280, 24→1.0045, 40→0.9954. Artefakt
ayrıklaştırmadanmış. Taşıma eğimi de %6.6 kayıyordu (4.4523 → 4.1750).
"""
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KANIT = ROOT / "vlm_capa.json"


def _d():
    return json.loads(KANIT.read_text(encoding="utf-8")) if KANIT.exists() else None


def test_olcut_KAPALI_FORM_kalsin():
    """τ/δ grafik değerleri ezberden alıntılanırsa kanıt olmaz."""
    src = (ROOT / "experiments" / "vlm_capa.py").read_text(encoding="utf-8")
    assert "1/a_2B" in src or "1/a_3B" in src
    assert "A_2B_TEORI = 2.0 * math.pi" in src


def test_kesisim_2pi_yi_geri_veriyor():
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    u = d["uyum"]
    assert u["dogrusal_R2"] > 0.99, u
    assert abs(u["a_2B_olculen_per_rad"] - 2 * math.pi) / (2 * math.pi) * 100 < 5.0
    assert u["hata_pct"] < 5.0


def test_PANEL_yakinsamasi_olculmus():
    """e>1 iki farklı şey olabilir; ayrımı ölçüm yapar."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    pk = d["panel_yakinsamasi"]
    e = [k["e_max"] for k in pk["kosular"] if k["e_max"]]
    assert len(e) >= 3
    assert e[0] > e[-1], "panel arttıkça e DÜŞMELİ"
    assert e[-1] <= 1.0, "yakınsamış panelde e eliptik sınırın içine girmeli"


def test_e_asimi_SINIFLANDIRILIYOR():
    """Ne göz ardı ediliyor ne de körü körüne reddediliyor."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    a = d["span_verimi_asimi"]
    assert a["sinif"] in ("sinir icinde", "artik ayriklastirma")
    if a["asim"] and a["asim"] > 0:
        assert a["asim"] < a["panel_kaymasi"], a


def test_URETIM_yolu_yakinsamis_paneli_kullaniyor():
    """Çapa bir kusur buldu; üretim yolu düzelmezse ölçüm boşa gider."""
    src = (ROOT / "openvsp_bridge.py").read_text(encoding="utf-8")
    # Panel sayisi kumeleme duzeltmesiyle 40 -> 80'e cikti (kumeleme ile dizi
    # monotonlasti ve en ince kademe 80'de oturdu). Sabit SAYI degil, GEREKCE
    # baglanir: deger olculmus olmali ve kaynagi kodda yazili olmali.
    import re as _re
    m = _re.search(r"VLM_SPAN_PANEL = (\d+)", src)
    assert m and int(m.group(1)) >= 40, "panel sayisi varsayilana dondu"
    assert "SectTess_U" in src
    assert "e=1.0788" in src, "gerekçe sayısıyla yazılmalı"


def test_DOGRULAMA_ile_GECERLEME_karistirilmiyor():
    """VLM'i potansiyel-akış teorisiyle karşılaştırmak verification'dır;
    viskoz gerçekle farkı AYRI bir sorudur ve bu çapa onu ölçmez."""
    d = _d()
    if not d:
        pytest.skip('kanıt/girdi yok: not d')
    assert "verification" in d["_kisit"]
    assert "OLCMEZ" in d["_kisit"] or "ÖLÇMEZ" in d["_kisit"]


class TestGercekGeometriYakinsamasi:
    """Çapa TEMİZ kanatta geçti; gerçek araçta yakınsama AYNI OLMAK ZORUNDA DEĞİL.

    ÖLÇÜM 1 (düzgün aralıklı panel): MiniHawk'ta Cl(8°) = 0.1417 / 0.3866 /
    0.3815 / 0.4324 — dizi MONOTON DEĞİL, saçılma %11.78.
    ÖLÇÜM 2 (uç kümelemesi 0.25): 0.4566 / 0.4112 / 0.4030 / 0.4029 — monoton,
    son adım %0.02. Düzgün dağılım uç girdabının gradyanını yakalayamıyordu.

    BAND KANONİK KURALDAN: son-adım farkı (%0.02) band DEĞİLDİR. Panel 1B bir
    ayrıklaştırma parametresidir (h~1/N) → band_from_levels(boyut=1) → %2.18.
    """

    def test_band_KANONIK_kuraldan_heuristikten_DEGIL(self):
        """Ilk surum bandi "son kademe degisimi" veriyordu: %0.02 — iki kademenin
        yakin olmasi ayriklastirma hatasinin sifira yakin oldugunu KANITLAMAZ."""
        import json
        p = ROOT / "vlm_panel_yakinsamasi.json"
        if not p.exists():
            pytest.skip('kanıt/girdi yok: not p.exists()')
        d = json.loads(p.read_text(encoding="utf-8"))
        kb = d.get("kanonik_band")
        assert kb, "kanonik band hesaplanmamis"
        assert d["vlm_band_pct"] == kb["u_pct"]
        assert d["vlm_band_pct"] > d["yakinsama"]["son_kademe_degisimi_pct"]

    def test_UC_KUMELEMESI_her_kademeye_UYGULANIYOR(self):
        """Kümeleme kademelerin BİRİNE uygulanmazsa aile tek-parametreli olmaz
        ve Richardson'ın dayandığı varsayım kırılır."""
        import json
        p = ROOT / "vlm_panel_yakinsamasi.json"
        if not p.exists():
            pytest.skip('kanıt/girdi yok: not p.exists()')
        d = json.loads(p.read_text(encoding="utf-8"))
        assert all(k.get("uc_kumeleme") == 0.25 for k in d["kayitlar"])

    def test_VERDIKT_olculen_monotonlukla_TUTARLI(self):
        """SABİT SONUÇ BAĞLANMAZ — kamburluk açılınca dizi salınımlı oldu ve
        "monoton" diyen test kırıldı. Bağlanması gereken şey, raporun kendi
        verisiyle çelişmemesi."""
        import json
        p = ROOT / "vlm_panel_yakinsamasi.json"
        if not p.exists():
            pytest.skip('kanıt/girdi yok: not p.exists()')
        d = json.loads(p.read_text(encoding="utf-8"))
        monoton = d["yakinsama"]["monoton"]
        seri = d["yakinsama"]["seri"]
        gercek = (all(a <= b for a, b in zip(seri, seri[1:]))
                  or all(a >= b for a, b in zip(seri, seri[1:])))
        assert monoton == gercek, "monotonluk hükmü seriyle çelişiyor"
        if not monoton:
            assert "YAKINSAMAMIS" in d["verdikt"] or "YAKINSAMAMIŞ" in d["verdikt"]

    def test_URETIM_yolu_kumelemeyi_kullaniyor(self):
        src = (ROOT / "openvsp_bridge.py").read_text(encoding="utf-8")
        assert "VLM_UC_KUMELEME = 0.25" in src
        assert "OutCluster" in src
        i = src.index("VLM_UC_KUMELEME = 0.25")
        assert "%11.78" in src[max(0, i - 700):i], "gerekce olcumle yazilmali"

    def test_uyari_metni_SABIT_olcum_gommuyor(self):
        """Ilk surumde olculen seri metne gomulmustu; kumeleme eklenip seri
        monotonlasinca metin "MONOTON DEGIL" demeye DEVAM ETTI."""
        src = (ROOT / "polar_birlestirme.py").read_text(encoding="utf-8")
        i = src.index("TAŞIMA BANDI ÖLÇÜLDÜ")
        blok = src[i:i + 700]
        assert "0.4324" not in blok and "0.3815" not in blok
        assert "vlm_band_kaynagi" in blok

    def test_birlestirici_OLCULEN_bandi_tasiyor(self):
        import polar_birlestirme as pb
        if not (ROOT / "vlm_panel_yakinsamasi.json").exists():
            pytest.skip('kanıt/girdi yok: not (ROOT / "vlm_panel_yakinsamasi.json").exists()')
        d = pb._depo_verisi()
        assert d.get("vlm_band_pct") is not None
        o = pb.birlesik_polar(d["vlm_polar"], d["kesit"], re_kanat=d["re_kanat"],
                              re_kesit=d["re_kesit"],
                              kesit_cd_mesh_bagimsiz=d["kesit_cd_mesh_bagimsiz"],
                              kesit_cd_band_pct=d.get("kesit_cd_band_pct"),
                              vlm_band_pct=d["vlm_band_pct"])
        assert all("Cl_band_pct" in n for n in o["noktalar"])
        assert any("TAŞIMA BANDI ÖLÇÜLDÜ" in u for u in o["uyarilar"])
        # "Dogrulama bandi DEGIL" ayrimi metinde MUTLAKA gecmeli: panel
        # ayriklastirma bandi ile teoriye karsi dogrulama bandi ayri seylerdir.
        assert any("DOĞRULAMA bandı" in u and "DEĞİL" in u for u in o["uyarilar"])

    def test_capa_bandi_gercek_araca_TASINMIYOR(self):
        """Çapanın %1.22'si TEMİZ kanada aittir ve gerçek araca kopyalanmaz.

        Kümeleme düzeltmesinden önce iki sayı 10 kat ayrışıyordu (%11.78 vs
        %1.22); şimdi yakınlaştılar (%2.18 vs %1.22) ama AYNI DEĞİLLER ve AYRI
        KAYNAKLARDAN gelirler: biri panel ayrıklaştırması, diğeri lifting-line
        teorisine karşı doğrulama. Test büyüklük farkını değil, KARIŞTIRILMADIĞINI
        bağlar — sayılar yakınsa bile birinin diğerinin yerine geçmesi hatadır.
        """
        import json
        pk = ROOT / "vlm_panel_yakinsamasi.json"
        capa = ROOT / "vlm_capa.json"
        if not (pk.exists() and capa.exists()):
            pytest.skip('kanıt/girdi yok: not (pk.exists() and capa.exists())')
        d = json.loads(pk.read_text(encoding="utf-8"))
        band = d["vlm_band_pct"]
        capa_hata = json.loads(capa.read_text(encoding="utf-8"))["uyum"]["hata_pct"]
        assert band != capa_hata, "capa bandi oldugu gibi kopyalanmis"
        # Band, GERCEK ARACIN kendi panel serisinden turemeli.
        assert d["kanonik_band"]["u_pct"] == band
        assert d["sablon"] != "dikdortgen_capa"


class TestIraksamaKapisi:
    """VLM yolu IRAKSAMIS kosuyu hicbir kontrolden gecirmeden yayinliyordu.

    ÖLÇÜLDÜ (insidans denemesi, 2026-08-05): Y_Rel_Rotation ile insidans
    uygulanınca VSPAERO Cl=3.8814, CDi=−5.184165, Cm=−147.28 verdi ve bu
    değerler vspaero_polar.json'a "polar" olarak YAZILDI. Negatif indüklenen
    direnç fiziksel olarak imkânsızdır. Aynı kusur C-grid koşucusunda
    kapatılmıştı; VLM yolunda açık kalmıştı.
    """

    def test_negatif_CDi_REDDEDILIYOR(self):
        from validity_envelope import vlm_kabul_edilebilir
        g = vlm_kabul_edilebilir({"alpha": 0.0, "Cl": 3.8814, "Cd_i": -5.184165})
        assert g and "NEGATIF" in g

    def test_sacma_Cl_REDDEDILIYOR(self):
        from validity_envelope import vlm_kabul_edilebilir
        assert vlm_kabul_edilebilir({"Cl": 3.8814, "Cd_i": 0.01})

    def test_saglikli_nokta_GECIYOR(self):
        from validity_envelope import vlm_kabul_edilebilir
        assert vlm_kabul_edilebilir({"Cl": 0.19335, "Cd_i": 0.00268}) is None

    def test_eksik_alan_SESSIZ_GECMIYOR(self):
        from validity_envelope import vlm_kabul_edilebilir
        assert vlm_kabul_edilebilir({"Cl": 0.2})

    def test_URETIM_yolu_kapiyi_UYGULUYOR(self):
        """Tanım var ama çağrılmıyorsa kapı değil, süstür."""
        src = (ROOT / "openvsp_bridge.py").read_text(encoding="utf-8")
        assert "vlm_kabul_edilebilir" in src
        assert "kabul_edilemez" in src

    def test_YAYINLANAN_polar_kapidan_gecmis(self):
        import json
        p = ROOT / "vspaero_polar.json"
        if not p.exists():
            pytest.skip('kanıt/girdi yok: not p.exists()')
        from validity_envelope import vlm_kabul_edilebilir
        for n in json.loads(p.read_text(encoding="utf-8"))["polar"]:
            assert vlm_kabul_edilebilir(n) is None, (n, "kabul edilemez nokta YAYINDA")


class TestBeyanInsaKiyasi:
    """Dataclass'in DEDIGI ile INSA EDILEN model karsilastirilmali.

    Bu depoda ayni sinif kusur İKİ KEZ yakalandı ve ikisi de SESSİZDİ:
      `incidence`  5 şablonda tanımlı, okuyan tek satır yok
      `diameter`   `D = fus.diameter` hesaplanıyor ama hiçbir yere yazılmıyor;
                   dataclass 0.08 m derken inşa edilen gövde 2.50 m GENİŞ ve
                   3.00 m YÜKSEKTİ — 1.5 m açıklıktaki kanat İÇİNDE kalıyordu.
    İkisi de ancak sonuç garip çıkınca fark edildi. ÖLÇÜLDÜ (düzeltmeden önce/
    sonra, VLM taşıma eğimi 1/°): çıplak kanat 0.06961 sabit; kanat+gövde
    0.03544 → 0.07050; tam araç 0.04595 → 0.07579 (kuram 0.07661).
    """

    def test_KIYAS_fonksiyonu_uretim_yolunda_CAGRILIYOR(self):
        src = (ROOT / "openvsp_bridge.py").read_text(encoding="utf-8")
        assert "def geometri_kiyasla" in src
        assert "geometri_kiyasla(aircraft)" in src, "tanımlı ama çağrılmıyor"
        assert "geometri_sapmalari" in src, "sonuca yazılmıyor"

    def test_CAP_gercekten_atanıyor(self):
        """Sessiz düşüşün kaynağı: D hesaplanıp kullanılmıyordu."""
        src = (ROOT / "openvsp_bridge.py").read_text(encoding="utf-8")
        assert "Ellipse_Height" in src and "Ellipse_Width" in src

    def test_YAYINLANAN_polarda_geometri_sapmasi_KAYITLI(self):
        import json
        p = ROOT / "vspaero_polar.json"
        if not p.exists():
            pytest.skip('kanıt/girdi yok: not p.exists()')
        d = json.loads(p.read_text(encoding="utf-8"))
        n = (d.get("polar") or [{}])[0]
        if "geometri_sapmalari" not in n:
            return                      # eski kanıt dosyası; yeniden üretilince gelir
        import re
        src = (ROOT / "openvsp_bridge.py").read_text(encoding="utf-8")
        blok = src[src.index("UYGULANMAYAN_ALANLAR = {"):]
        bilinen = set(re.findall(r'"([a-z_]+\.[a-z_]+)":', blok[:1400]))
        for s2 in n["geometri_sapmalari"]:
            # Kalan sapma BİLİNEN ve gerekçesi yazılı olmalı; yenisi sessizce
            # eklenemez. Yalnızca-bilgi kayıtları (gerçeklenen zarf) hariç.
            if s2.get("yalnizca_bilgi"):
                assert s2.get("not"), "bilgi kaydi gerekcesiz"
                continue
            assert s2.get("olcut") in bilinen, f"ADI KONMAMIS sapma: {s2}"
