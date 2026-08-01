"""GCI seviye YAKINSAMA kapısı — mesh-bağımsızlık sayısının ön koşulu.

ÖLÇÜLDÜ (gci_minihawk_arac.json): koşu `rezidual_ok: false`, `iterasyon: 103`
diyordu; aynı seviyeler Richardson fitine girdi ve GCI %379 çıktı. Seviye Cd'leri
0.00057 → 0.03765 → 0.01388, yani 66 KAT saçılma — bu bir yakınsama dizisi değil,
üç ayrı geçici çözüm. Yakınsamamış noktalardan hesaplanan GCI, hatayı
AYRIKLAŞTIRMAYA yanlış atfeder; asıl sebep iterasyon/duvar çözünürlüğüdür.

Fizik kapısı ("Cd fiziksel mi") zaten vardı; bu kapı "Cd OTURDU MU" sorar.
"""
import pytest

from vehicle_pipeline import seviye_yakinsadi_mi, yakinsama_teshisi


def _conv(**k):
    d = {"iterasyon": 500, "rezidual_ok": True, "drift_ok": True,
         "cd_drift_son20pct": 0.1, "son_rezidualler": {"Ux": "1e-05", "p": "2e-05"},
         "salinim": {"osilasyon": False}}
    d.update(k)
    return d


def test_saglikli_seviye_gecer():
    ok, neden = seviye_yakinsadi_mi(_conv())
    assert ok and neden == ""


def test_MINIHAWK_VAKASI_reddedilir():
    """Gerçek ölçülen değerler: 103 iterasyon, rezidual_ok false."""
    ok, neden = seviye_yakinsadi_mi(_conv(
        iterasyon=103, rezidual_ok=False,
        son_rezidualler={"Ux": "5.15e-04", "p": "2.05e-03"}))
    assert ok is False
    assert "rezidueller" in neden


def test_az_iterasyon_tek_basina_reddeder():
    ok, neden = seviye_yakinsadi_mi(_conv(iterasyon=20))
    assert ok is False and "20 iterasyon" in neden


def test_drift_reddeder():
    ok, neden = seviye_yakinsadi_mi(_conv(drift_ok=False, cd_drift_son20pct=12.3))
    assert ok is False and "drift" in neden


def test_SALINIM_reddeder():
    """Limit çevrimindeki çözümün Cd'si salınımın nerede durduğuna bağlıdır."""
    ok, neden = seviye_yakinsadi_mi(_conv(salinim={"osilasyon": True}))
    assert ok is False and "salinim" in neden


def test_gerekce_HER_basarisizlik_icin_yazilir():
    ok, neden = seviye_yakinsadi_mi(_conv(
        iterasyon=10, rezidual_ok=False, drift_ok=False,
        salinim={"osilasyon": True}))
    assert ok is False
    for anahtar in ("rezidueller", "drift", "salinim", "iterasyon"):
        assert anahtar in neden, f"{anahtar} gerekcede yok"


def test_ANA_KOSU_ve_SEVIYE_ayni_kaynagi_kullanir(tmp_path):
    """İki yol ayrı yazılsaydı kaçınılmaz olarak ayrışırdı — nitekim ayrışmıştı."""
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp)
    assert src.count("yakinsama_teshisi(") >= 3      # tanim + ana kosu + seviye
    # ana kosu artik kendi kopyasini kurmuyor
    assert '"cd_drift_son20pct": round(drift_pct, 3)' not in src.split(
        "def yakinsama_teshisi")[2] if src.count("def yakinsama_teshisi") > 1 else True


def test_teshis_log_yoksa_COKMEZ(tmp_path):
    c = yakinsama_teshisi(tmp_path, [])
    assert c["iterasyon"] == 0
    assert c["rezidual_ok"] is False        # kanit yoksa "yakinsadi" DEMEZ


class TestSeviyeQoIDuraganlik:
    """Seviye kapısı, ölçmeye çalıştığı şeyi İMKÂNSIZLAŞTIRIYORDU.

    ÖLÇÜLDÜ (küp, 3 seviyeli GCI): ince Cd=1.04166, orta Cd=1.04584 — %0.4 fark,
    yani büyüklükler oturmuş. Ama orta seviyenin rezidüelleri 1.5-2.6e-4'te platoya
    oturmuştu ve KATI rezidüel ölçütü İKİ kaba seviyeyi de eledi. Geriye tek seviye
    kaldı, GCI HİÇ hesaplanamadı ve sayısal belirsizlik "—" olarak raporlandı.

    Richardson her seviyenin KENDİ ayrıklaştırmasının yakınsamış çözümünü ister —
    bu da QoI'nin oturmasıdır; rezidüel onun VEKİLİDİR. Aynı ayrım ana koşuda
    zaten kurulmuştu (87751f9, 8dfb6d8); seviyelere uygulanmamıştı.
    """
    @staticmethod
    def _kup_orta(**k):
        d = {"rezidual_ok": False, "drift_ok": True, "cd_drift_son20pct": 0.3,
             "iterasyon": 800, "salinim": {"osilasyon": False},
             "son_rezidualler": {"Uy": "2.62e-04", "p": "1.53e-04"}}
        d.update(k)
        return d

    def test_KUP_ORTA_SEVIYESI_artik_GCIya_giriyor(self):
        ok, neden = seviye_yakinsadi_mi(self._kup_orta())
        assert ok is True and neden == ""

    def test_genis_drift_HALA_eleniyor(self):
        ok, _ = seviye_yakinsadi_mi(self._kup_orta(cd_drift_son20pct=1.5))
        assert ok is False

    def test_SALINIMLI_seviye_HALA_eleniyor(self):
        """Limit çevrimindeki bir seviye Richardson fitine giremez."""
        ok, neden = seviye_yakinsadi_mi(
            self._kup_orta(salinim={"osilasyon": True, "genlik_pct": 2.0}))
        assert ok is False and "salinim" in neden

    def test_drift_OLCULEMEZSE_eleniyor(self):
        ok, _ = seviye_yakinsadi_mi(self._kup_orta(cd_drift_son20pct=None))
        assert ok is False

    def test_az_iterasyon_HALA_eleniyor(self):
        ok, _ = seviye_yakinsadi_mi(self._kup_orta(iterasyon=20))
        assert ok is False

    def test_esik_TEK_KAYNAKTAN(self):
        """Ana koşu ile seviye kapısı aynı eşiği kullanmalı; ayrışırlarsa
        'seviye geçti ama koşu geçmedi' gibi tutarsız hükümler çıkar."""
        import inspect

        import vehicle_pipeline as vp
        src = inspect.getsource(vp.seviye_yakinsadi_mi)
        assert "QOI_DURAGAN_DRIFT_PCT" in src
        assert "validity_envelope" in src


def test_QoI_muafiyeti_KISA_tarihcede_verilmiyor():
    """MiniHawk vakası: 103 iterasyon, drift %0.007 — "durağan" GÖRÜNÜYOR ama
    o kampanyanın seviye Cd'leri 0.00057 / 0.03765 / 0.01388 idi (66 KAT saçılma).
    Rezidüel ölçütünden vazgeçince tek dayanak QoI tarihçesidir; kısa tarihçede
    "drift küçük" durağanlık KANITI DEĞİLDİR."""
    from vehicle_pipeline import QOI_MUAFIYET_MIN_ITER
    kisa = {"rezidual_ok": False, "drift_ok": True, "cd_drift_son20pct": 0.007,
            "iterasyon": 103, "salinim": {"osilasyon": False},
            "son_rezidualler": {"Ux": "5.15e-04", "p": "2.05e-03"}}
    ok, neden = seviye_yakinsadi_mi(kisa)
    assert ok is False and "rezidueller" in neden
    # ayni kosu UZUN tarihceyle: muafiyet verilir
    uzun = {**kisa, "iterasyon": QOI_MUAFIYET_MIN_ITER}
    assert seviye_yakinsadi_mi(uzun)[0] is True


def test_GCI_seviyelerine_AYNI_iterasyon_butcesi():
    """Kaba seviyelere `hizli` preset'inin end_time'i (200) veriliyordu, inceye 800
    — yani kaba seviyeler TASARIM GEREĞİ az-yakınsamış oluyordu. Seviye yakınsama
    kapısı eklenince bu, GCI'yı doğrudan İMKÂNSIZLAŞTIRDI.

    ÖLÇÜLDÜ (küp): kaba 415.064 hücre Cd=1.04808 (200 iter, rezidüel p=2e-2, ELENDİ)
    orta 726.544 Cd=1.04584 (800 iter, geçti) | ince 905.896 Cd=1.04166.
    Üç değer MONOTON, toplam saçılma %0.6 — küp zaten mesh-yakınsak.

    Kısmak yanlış ekonomi: kaba mesh iterasyon başına DAHA UCUZ ama
    az-yakınsamışlığı bütün çalışmayı götürüyor."""
    import inspect

    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    i = src.index("kademeler = [")
    blok = src[i:i + 400]
    assert 'MESH_QUALITY["hizli"]["end_time"]' not in blok, (
        "kaba seviye hala kisitli iterasyonla kosuyor")
    assert blok.count('q["end_time"]') >= 2


class TestIyilestirmeOrani:
    """Celik 2008: GCI için r ≥ 1.3 ŞART. Altında Richardson mertebesi patlar.

    ÖLÇÜLDÜ (küp, 3 seviye hepsi yakınsamış):
        kaba 415.064  h=0.013406  Cd=1.04934
        orta 726.544  h=0.011124  Cd=1.04583
        ince 905.896  h=0.010335  Cd=1.04166
        r21=1.076  r32=1.205   ->  p=-2.338, GCI=-%3.167, asimptotik 2.25
    NEGATİF mertebe ve NEGATİF belirsizlik fiziksel değildir; o sayıyı yayınlamak
    hiç yayınlamamaktan KÖTÜDÜR.

    KÖK SEBEP kendi düzeltmemle etkileşim: kaba seviyeler NİYET arka planından
    (`lmax/bg_div`) türetiliyordu, ince seviye ise bütçe için KABALAŞTIRILIYORDU —
    aradaki oran sıkışıyordu. Artık kaba seviyeler ince seviyenin GERÇEK arka
    planından türetiliyor.
    """
    def test_esik_Celik_2008(self):
        from vehicle_pipeline import GCI_MIN_ORAN
        assert GCI_MIN_ORAN == 1.3

    def test_OLCULEN_oranlar_esigin_ALTINDA(self):
        N = [415064, 726544, 905896]
        h = [n ** (-1 / 3) for n in N]
        r21, r32 = h[1] / h[2], h[0] / h[1]
        from vehicle_pipeline import GCI_MIN_ORAN
        assert r21 < GCI_MIN_ORAN and r32 < GCI_MIN_ORAN

    def test_kapi_GCIyi_ENGELLIYOR(self):
        import inspect

        import vehicle_pipeline as vp
        src = inspect.getsource(vp.run_vehicle_analysis)
        i = src.index("_oran_ok = ")
        blok = src[i:i + 300]
        assert "if _oran_ok else None" in blok, "oran yetersizken GCI hala hesaplaniyor"

    def test_verdikt_SEBEBI_ve_COZUMU_soyluyor(self):
        import inspect

        import vehicle_pipeline as vp
        src = inspect.getsource(vp.run_vehicle_analysis)
        assert "iyileştirme oranı yetersiz" in src
        assert "Celik 2008" in src
        assert "hücre oranını artırın" in src        # ne yapilacagi da yazili

    def test_kaba_seviyeler_GERCEK_arka_plandan_turetiliyor(self):
        """Niyet kullanılırsa seviyeler bütçe düzeltmesi yüzünden sıkışır."""
        import inspect

        import vehicle_pipeline as vp
        src = inspect.getsource(vp.run_vehicle_analysis)
        i = src.index("bg_ince = ")
        assert "bg_bilgi" in src[i:i + 200]
