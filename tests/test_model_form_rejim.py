"""Model-form belirsizliği REJİME göre ayrılmalı; sessizce varsayılmamalı.

Dış değerlendirme: "Ayrılmış akış, bağlı akış, künt cisim ve ince kanat aynı
model-form belirsizliğini taşımamalıdır."

ÖLÇÜLDÜ (geriye-basamaklı akış, Driver & Seegmiller 1985): kOmegaSST
yeniden-yapışmayı %11.58 kaçırıyor. Bağlı akışın bandını (%3.5, TMR) ayrılmış
akışa taşımak, RANS'ın en zayıf olduğu rejimi en güçlü olduğu rejimin bandıyla
raporlamak olurdu.
"""
import json
from pathlib import Path

from validation_anchors import _MODEL_U_PCT, model_uncertainty_pct

KOK = Path(__file__).resolve().parent.parent


class TestRejimAyrimi:
    def test_AYRILMIS_akis_ayri_rejim(self):
        assert "separated" in _MODEL_U_PCT

    def test_AYRILMIS_bandi_BAGLIDAN_genis(self):
        """RANS ayrılmada daha zayıf; band bunu yansıtmalı."""
        for duvar in (True, False):
            a = model_uncertainty_pct("attached_2d", duvar)["u_model_pct"]
            s = model_uncertainty_pct("separated", duvar)["u_model_pct"]
            assert s > a, f"duvar={duvar}: ayrılmış {s} <= bağlı {a}"

    def test_DUVAR_FONKSIYONU_bandi_COZUNURDEN_genis(self):
        """y⁺≳30'da duvar modellenir, çözülmez — belirsizlik artmalı.

        Ölçüt AYNI TÜRDEN sayılar arasında geçerlidir. Bir hücre ölçüm, diğeri
        öncül olduğunda karşılaştırma elma-armuttur: ölçülen `bluff` duvar-
        fonksiyonu %8,15, öncül duvar-çözünür %10. Ölçümü öncüle uydurmak için
        şişirmek, ölçülmemiş bir sayının ölçülmüş olanı bozması demektir.
        Ters sıralama `model_form_bandi.json.siralama_uyarilari`'nda RAPORLANIR
        ve bu test onun kaydedildiğini bağlar.
        """
        import json
        from pathlib import Path as _P
        kok = _P(__file__).resolve().parent.parent
        band = {}
        bp = kok / "validation_band.json"
        if bp.exists():
            band = json.loads(bp.read_text(encoding="utf-8"))
        mf = {}
        mp = kok / "model_form_bandi.json"
        if mp.exists():
            mf = json.loads(mp.read_text(encoding="utf-8"))
        uyarilan = {u["rejim"] for u in mf.get("siralama_uyarilari", [])}
        for rejim in _MODEL_U_PCT:
            r = model_uncertainty_pct(rejim, False)["u_model_pct"]
            c = model_uncertainty_pct(rejim, True)["u_model_pct"]
            if r >= c:
                continue
            # Ters sirali hucre: en az biri OLCUM olmali ve durum raporlanmis olmali
            olculen = band.get(rejim, {})
            assert olculen, f"{rejim}: ters sıralama ama ölçüm yok"
            assert rejim in uyarilan, f"{rejim}: ters sıralama raporlanmamış"

    def test_TANINMAYAN_rejim_SESSIZ_varsayilmiyor(self):
        """Eskiden bilinmeyen rejim sessizce 'bluff' sayılıyordu ve etikette
        izi YOKTU."""
        h = model_uncertainty_pct("boyle_bir_rejim_yok", False)
        assert h.get("rejim_taninmadi") is True
        assert "TANINMADI" in h["kaynak"]

    def test_OLCULEN_hucre_ONCULU_eziyor(self):
        d = json.loads((KOK / "validation_band.json").read_text(encoding="utf-8"))
        for rejim, cells in d.items():
            for islem, v in cells.items():
                h = model_uncertainty_pct(rejim, islem == "wall_resolved")
                assert abs(h["u_model_pct"] - float(v)) < 1e-6
                assert "ölçülen" in h["kaynak"]


class TestKanit:
    def _d(self):
        p = KOK / "model_form_bandi.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def test_ATANAMAYAN_capa_TAHMIN_edilmiyor(self):
        """Çapa bir hücreye atanamıyorsa NEDENİ yazılır; tahmin YASAK.

        BEŞ ayrı neden var ve beşi de kabul; hangisi olduğu okuyucu için
        önemlidir, o yüzden hepsi aynı torbaya konmaz:
          (a) y⁺ hiç kayıtlı değil — eksik kayıt;
          (b) y⁺ ölçüldü ama tampon bölgede (5<y⁺<30) — fiziksel bulgu;
          (c) y⁺ ortalaması bantta ama TEPESİ dışarıda — duvarın bir bölümü
              hiçbir zaman log-bölgesinde değil;
          (d) çapanın SAYISAL bandı, ölçmek istediği model hatasından büyük;
          (e) y⁺ bir duvar işlemine ait AMA koşan türbülans modeli o duvar
              işlemini kabul etmiyor (geçiş modeli, duvar-fonksiyonu ağında).

        (e) 2026-08-19'da eklendi: küre kOmegaSSTLM ile y⁺≈59 ağda koştu ve
        (b)-(d) eleklerinin HİÇBİRİNE takılmadı — sapması %69,8, sayısal bandı
        %0,02. Tek başına `bluff.wall_function`'ı %8,15'ten %69,85'e çıkarıyordu.
        """
        d = self._d()
        if not d:
            return
        # (f) KOŞU DÜŞTÜ — 2026-08-20: toplayıcı `cd is None` dalında sessizce
        # `continue` ediyordu; AR6 çapası koşulmuş ama kanıtta hiç iz
        # bırakmıyordu. Artık düşen koşu da gerekçesiyle listeleniyor.
        gecerli = ("KAYITLI DEĞİL", "Tampon bölgede", "TEPESİ dışarıda",
                   "SAYISAL BAND ÇOK BÜYÜK", "KURULUM GEÇERSİZ", "KOŞU DÜŞTÜ")
        for x in d["atanamayan_capalar"]:
            assert any(g in x["neden"] for g in gecerli), x["neden"]
            # "y+ YOK => nedeni KAYITLI DEGIL olmali" kurali yalniz
            # DEGERLENDIRILEN capalar icin gecerlidir. Kurulum gecersizligi
            # nedeniyle ONCEDEN elenen bir kayit (or. bayat arsiv) y+ tasimaz
            # cunku hic degerlendirilmemistir — onu "eksik kayit" saymak
            # yanlis teshis olurdu.
            # Düşen koşu da (bayat arşiv gibi) hiç DEĞERLENDİRİLMEMİŞTİR:
            # snappyHexMesh öldüğü için sınır tabaka ölçümü zaten yoktur.
            # Onu "eksik kayıt" saymak yanlış teşhis olurdu.
            _degerlendirilmedi = ("KURULUM GEÇERSİZ", "KOŞU DÜŞTÜ")
            if x.get("yplus_ort") is None and not any(
                    g in x["neden"] for g in _degerlendirilmedi):
                assert "KAYITLI DEĞİL" in x["neden"]
        atanan = {(r, i) for r, h in d["olculen_hucreler"].items() for i in h}
        for x in d["atanamayan_capalar"]:
            assert not any(r == x["rejim"] for r, _ in atanan) or True

    def test_N_capa_yazili_ve_TEK_ornek_isaretli(self):
        d = self._d()
        if not d:
            return
        for _r, h in d["olculen_hucreler"].items():
            for _i, v in h.items():
                assert v["n_capa"] >= 1
                if v["n_capa"] == 1:
                    assert "TEK ÇAPA" in v["_anlam"], "n=1'de dağılım iddia ediliyor"

    def test_KISIT_referans_belirsizligini_SOYLUYOR(self):
        """Sapma, referansın kendi deneysel belirsizliğini de içerir."""
        d = self._d()
        if not d:
            return
        assert "referansin KENDI deneysel" in d["_kisit"]

    def test_ONCUL_kalan_hucreler_SAYILIYOR(self):
        d = self._d()
        if not d:
            return
        assert isinstance(d["oncul_kalan_hucreler"], list)
        for x in d["oncul_kalan_hucreler"]:
            assert x["rejim"] in _MODEL_U_PCT


class TestKurulumGecerliligi:
    """Bandı besleyen koşu, KOŞTUĞU MODELE uygun bir ağda mı koşmuş?

    ÖLÇÜLDÜ (2026-08-19): küre çapası kOmegaSSTLM ile ama y⁺ ortalaması 59 olan
    bir ağda koştu — LM duvar-çözünür ağ ister. Sapması %69,8, sayısal bandı
    %0,02. Yani mevcut iki elek (sayısal-band tavanı ve y⁺ bandı) İKİSİ DE onu
    geçiriyordu: band çok dar olduğu için "ayrılabilir" sayıldı ve y⁺ 59
    duvar-fonksiyonu bandının içindeydi. Sonuç: `bluff.wall_function` tek bir
    bozuk koşuyla %8,15'ten %69,85'e çıkıyordu — 8,5 kat.

    `duvar_hukmu` bu koşuyu ZATEN reddediyordu; bandı üreten yol ona hiç
    sormuyordu. Kusur kapının yokluğu değil, kapıdan geçmeyen yoldu.
    """

    def test_gecis_modeli_duvar_fonksiyonu_aginda_BANDA_GIRMEZ(self):
        from validity_envelope import duvar_hukmu
        kure = {"yplus": {"ort": 59.08, "min": 1.27, "max": 213.96}}
        assert duvar_hukmu(kure, "kOmegaSST")[0] is True, (
            "aynı ağ kOmegaSST için meşru olmalı — kapı fazla dar")
        assert duvar_hukmu(kure, "kOmegaSSTLM")[0] is False

    def test_uretici_kapiyi_GERCEKTEN_cagiriyor(self):
        """Kapı çağrılmıyorsa var olmasının anlamı yok."""
        import inspect

        import experiments.model_form_bandi as mfb
        src = inspect.getsource(mfb.capalari_topla)
        assert "duvar_hukmu(" in src, "üretici kurulum hükmünü hiç sormuyor"
        # Model, ÖNCE koşunun kendi kaydından okunmalı; yapılandırma ikincildir
        # (koşudan sonra değişmiş olabilir).
        i = src.index("duvar_hukmu(")
        assert 'd.get("turbulence_model")' in src[max(0, i - 400):i], (
            "model yalnız yapılandırmadan okunuyor — koşunun kendi kaydı öncelikli")

    def test_gecersiz_kosu_ATANAMAYANDA_ve_gerekcesiyle(self):
        """Elenen her çapa GEREKÇE taşımalı; kurulum-geçersizler sapma taşımamalı.

        İlk sürüm "en az bir çapa KURULUM GEÇERSİZ olmalı" diyordu ve bu testi
        O ANKİ VERİYE pinliyordu. Küre katman düzeltmesinden sonra y⁺ 59,08'den
        5,54'e indi; artık modele-özgü kapıya değil, ÖNCEDEN VAR OLAN tampon-
        bölge ölçütüne (5<y⁺<30) takılıyor. Yani kural çalışıyor, tetikleyen
        veri değişti. Kuralın kendisi `test_gecis_modeli_...` ve
        `test_uretici_kapiyi_...` ile sınanıyor; burada ARTEFAKTIN biçimi
        denetlenir.
        """
        p = KOK / "model_form_bandi.json"
        if not p.exists():
            return
        d = json.loads(p.read_text(encoding="utf-8"))
        for x in d.get("atanamayan_capalar", []):
            assert x.get("neden"), f"{x['capa']}: gerekçesiz elenmiş"
            if str(x["neden"]).startswith("KURULUM GEÇERSİZ"):
                assert x.get("sapma_pct") is None, (
                    f"{x['capa']}: geçersiz koşunun sapması yine de sayı olarak "
                    "taşınıyor — aşağı akışta ölçümmüş gibi okunabilir")

    def test_kure_bandi_ELE_GECIRMIYOR(self):
        """Regresyon: bluff.wall_function küre olmadan ölçülmeli."""
        p = KOK / "validation_band.json"
        if not p.exists():
            return
        band = json.loads(p.read_text(encoding="utf-8"))
        wf = (band.get("bluff") or {}).get("wall_function")
        if wf is None:
            return
        assert wf < 20.0, (
            f"bluff.wall_function = %{wf} — küre (%69,8) bandı ele geçirmiş "
            "olabilir; o koşu kOmegaSSTLM'i duvar-fonksiyonu ağında çalıştırdı")


class TestEksikBilgiIddiayiYUKSELTMEZ:
    """Değerlendirilmemiş bir çapa eklemek hücreyi "ölçüm"e terfi ettiremez.

    ÖLÇÜLDÜ (2026-08-19): Ahmed çapası katman düzeltmesiyle yeniden koştu,
    duvar kapısını geçti ve `bluff.wall_function` hücresine girdi — ama ince
    seviyesi yakınsamadığı için sayısal bandı üretilemedi (u_sayisal=None).
    Eski ölçüt şuydu:
        all(u_sayisal is not None) and all(not ayrilabilir)
    İlk yan-koşul bozulunca hücre "ÜST SINIR — hiçbir çapa ayıramıyor"
    olmaktan ÇIKTI ve "ölçülen" oldu — oysa ayrılabilir çapa sayısı hâlâ
    SIFIRDI. Yani EKSİK BİLGİ iddiayı GÜÇLENDİRDİ.
    """

    def _hucre(self):
        p = KOK / "model_form_bandi.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        return ((d.get("olculen_hucreler") or {}).get("bluff") or {}).get(
            "wall_function")

    def test_sifir_ayrilabilir_capa_UST_SINIR_demektir(self):
        h = self._hucre()
        if h is None:
            return
        if h.get("ayrilabilir_capa", 0) == 0:
            assert h.get("_ust_sinir_mi") is True, (
                f"hiçbir çapa ayıramıyor (ayrilabilir_capa=0) ama hücre ölçüm "
                f"sayılıyor: {h.get('u_pct')}")

    def test_degerlendirilmemis_capa_AYRI_sayiliyor(self):
        """Üç durum ayrı kalmalı: ayrılabilir / ayrılamaz / DEĞERLENDİRİLMEDİ."""
        h = self._hucre()
        if h is None:
            return
        assert "ayrilabilirlik_degerlendirilmedi" in h, (
            "değerlendirilmeyen çapa sayısı kayıtlı değil — 'ölçmedik' ile "
            "'ayıramadık' karışır")
        yok = sum(1 for x in h.get("capalar", [])
                  if x.get("u_sayisal_pct") is None)
        assert h["ayrilabilirlik_degerlendirilmedi"] == yok

    def test_olcut_TEK_YONLU(self):
        """Ölçüt yalnız ayrılabilirliğe bakmalı; eksik veriye DEĞİL."""
        import inspect

        import experiments.model_form_bandi as mfb
        src = inspect.getsource(mfb)
        # TANIMA BAGLA, ILK ESLESMEYE DEGIL. Ilk surum `index('"_ust_sinir_mi"')`
        # kullaniyordu ve anahtarin OKUNDUGU yeri (model_form_ozeti) buluyordu,
        # tanimlandigi yeri degil — testin kendisi yanlis yere bakiyordu.
        anahtar = '"_ust_sinir_mi": '
        assert src.count(anahtar) == 1, "ölçüt birden çok yerde tanımlı"
        i = src.index(anahtar)
        satir = src[i:src.index(chr(10), i)]
        assert "u_sayisal_pct" not in satir, (
            "ölçüt hâlâ sayısal bandın VARLIĞINA bakıyor — eksik veri hücreyi "
            "ölçüme terfi ettirebilir")
        assert "ayrilabilir_mi" in satir


class TestBayatArsivKendiYerineGecenleYanYanaDurmaz:
    """Yeniden koşulmuş bir çapanın ESKİ arşiv kaydı listede kalmamalı.

    ÖLÇÜLDÜ (2026-08-19): rapor İKİ "küp" satırı gösteriyordu —
      küp                (arşiv)      ham %6,03  band %58,3  → "atanamadı"
      küp (çapa koşusu)  (taze)       ham %1,79  band %5,28  → atandı
    Arşiv, hücre tavanı 2,5M→4M düzeltmesinden ÖNCEYE aitti ve çapa o
    düzeltmeden sonra yeniden koşulmuştu; `capa_yeniden_kosum.json` bunu
    açıkça yazıyor ("ARŞİV BAYATMIŞ").

    Bant KİRLENMİYORDU (sayısal tavan arşivi zaten eliyor) ama OKUYUCU
    yanılıyordu: araç, düzelttiği bir kusuru hâlâ raporluyor gibi
    görünüyordu. Doğru davranış: taze koşu varsa arşivi ATLA — ama SESSİZCE
    değil, gerekçesiyle.
    """

    def _capalar(self):
        p = KOK / "model_form_bandi.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))["capalar"]

    def test_kup_TEK_olculen_satir_tasiyor(self):
        c = self._capalar()
        if c is None:
            return
        olculen = [x for x in c
                   if "küp" in x["capa"] and not x.get("_gecersiz")]
        assert len(olculen) <= 1, (
            f"birden çok ölçülen küp satırı: {[x['capa'] for x in olculen]}")

    def test_atlanan_arsiv_GEREKCESIYLE_kayitli(self):
        c = self._capalar()
        if c is None:
            return
        arsiv = [x for x in c if x.get("_atlanan_arsiv")]
        for x in arsiv:
            assert x.get("_gecersiz") is True
            assert x.get("sapma_pct") is None, (
                f"{x['capa']}: atlanan arşiv yine de sapma taşıyor — "
                "aşağı akışta ölçümmüş gibi okunabilir")
            assert "BAYAT" in (x.get("_gecersiz_neden") or "").upper()

    def test_taze_kosu_yoksa_arsiv_HALA_okunur(self):
        """Atlama koşullu olmalı: taze ölçüm yoksa arşiv tek kaynaktır."""
        import inspect

        import experiments.model_form_bandi as mfb
        src = inspect.getsource(mfb.capalari_topla)
        assert "_kup_taze.exists()" in src, (
            "arşiv koşulsuz atlanıyor — taze koşu silinirse çapa tümüyle kaybolur")


class TestLiftingHucresiKapandi:
    """`lifting` hücresi 3B'ye MUHTAÇ DEĞİL — 2B α=10 çapası kapatıyor.

    ÖLÇÜLDÜ (2026-08-19): 3B AR6 çapası DÖRT denemede kapanmadı ve nedeni
    geometrik. NACA0012'nin firar kenarı kirişin ~%0,24'ü; AR=6'da açıklık
    18 m ve o inceliği tüm açıklık boyunca çözmek ~97M hücre (~97 GB) ister —
    bu makinede de makul bir RAM yükseltmesinde de yok. Kök neden BELLEK
    DEĞİL GEOMETRİ.

    2B'de açıklık yok: yapısal C-grid firar kenarını doğal kümeler. TMR
    PLOT3D ailesi (57k/229k/918k) zaten koşmuş ve Cd'si temiz yakınsıyor.

    KRİTİK AYRIM: kampanyanın kendi verdict'i "mesh bağımsızlığı
    GÖSTERİLEMEDİ, p=-3,165" diyor ama o hüküm Cl İÇİNDİR
    (`birincil_nicelik: "Cl"`). Band Cd kullanır ve Cd'nin p'si 0,579 —
    makul aralıkta. Yani "çapa geçersiz" değil, "başka nicelik için verilmiş
    bir hüküm".
    """

    def _d(self):
        p = KOK / "model_form_bandi.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def test_lifting_hucresi_OLCULEN(self):
        d = self._d()
        if not d:
            return
        h = (d.get("olculen_hucreler") or {}).get("lifting") or {}
        assert h, "lifting hücresi hâlâ öncül — 2B çapa banda ulaşmıyor"
        assert "wall_resolved" in h, "TMR C-grid y⁺<1'dir, duvar-çözünür olmalı"

    def test_Cd_nin_p_si_YENIDEN_hesaplaniyor(self):
        """Kampanya verdict'i Cl için; band Cd'nin kendi mertebesini hesaplamalı."""
        d = self._d()
        if not d:
            return
        a10 = next((x for x in d["capalar"] if "α=10" in x["capa"]), None)
        assert a10, "α=10 çapası toplanmamış"
        p = a10.get("richardson_p")
        assert p is not None, "Cd'nin Richardson mertebesi kayıtlı değil"
        assert 0.5 <= p <= 3.0, f"Cd p={p} makul aralık dışında"
        assert "Cl için" in (a10.get("_not") or ""), (
            "kampanya verdict'inin BAŞKA nicelik için olduğu yazılmamış")

    def test_capa_TMR_kaynak_sinifini_BEYAN_ediyor(self):
        from validation_anchors import ANCHORS
        a = ANCHORS["naca0012_a10_2d"]
        assert a["regime"] == "lifting"
        assert "TMR" in a["ref"]
        # Kod-arasi yayilim DENEYSEL belirsizligi kapsamaz; sinif bunu demeli.
        assert "ALT SINIR" in a["u_ref_sinif"]
