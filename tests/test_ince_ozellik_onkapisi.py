"""İnce özellik hükmü KOŞUDAN ÖNCE — kanat çapasının dersinin genelleştirilmesi.

Aynı ölçüm koşudan SONRA zaten yapılıyordu (`resolution_warning`), ama o zaman
saatler harcanmış oluyor ve uyarı "belki yeterince çözülmüyor" deyip MALİYETİ
söylemiyordu.

ÖLÇÜLDÜ (NACA0012 AR6 kanat çapası, 2026-08-02):
  firar kenarı 3.6 mm, yüzey hücresi 2.8 mm → TE 1.3 HÜCRE
  hücre 20.6 KAT artarken Cl yalnız %23 arttı (0.0572 → 0.0705, beklenen 0.329)
Kutta koşulu bir hücrelik firar kenarında kurulamaz; sirkülasyon doğmazsa taşıma
da doğmaz. Yani bu bir NİCELİK hatası değil, fiziğin hiç kurulamamasıdır.
"""
import vehicle_pipeline as vp


def _kanat(**kw):
    """Kanat çapasının GERÇEK sayıları: yüzey hücresi 2.8 mm, TE 3.6 mm."""
    return vp.ince_ozellik_hukmu(0.0036, 0.0028 * 2 ** 3, 3,
                                 yuzey_alani_m2=0.279, **kw)


def test_OLCULEN_kanat_TE_hucresi_yeniden_uretiliyor():
    h = _kanat(hucre_butcesi=2_500_000)
    assert abs(h["n_hucre"] - 1.29) < 0.03        # ölçülen 1.3 hücre
    assert h["yeterli"] is False
    assert h["hedef_hucre"] == 6


def test_yeterli_cozunurlukte_uyari_YOK():
    h = vp.ince_ozellik_hukmu(0.05, 0.008, 3)     # TE 50 mm, hücre 1 mm
    assert h["yeterli"] is True and "yeterli" in h["hukum"]


def test_ULASILABILIR_kademe_soyleniyor():
    h = _kanat(hucre_butcesi=10_000_000)
    assert h["gereken_bump"] == 3 and h["ulasilabilir"] is True
    assert "ref_bump=3 ile hedefe ulaşılır" in h["hukum"]


def test_BUTCE_arka_plani_da_sayiyor():
    """Yalnız yüzeye bakmak, hacim mesh'ine yer bırakmayan kademeyi 'sığar'
    gösteriyordu — onerilen_ref_bump'ın zaten kapattığı tuzak."""
    dar = _kanat(hucre_butcesi=2_500_000, arka_plan_hucre=2_000_000)
    assert dar["ulasilabilir"] is False
    assert "SIĞMAZ" in dar["hukum"] or "ÇÖZÜLEMEZ" in dar["hukum"]
    gnis = _kanat(hucre_butcesi=2_500_000, arka_plan_hucre=0)
    assert gnis["denemeler"][2]["butceye_sigar"] is True


def test_ULASILAMAZ_durumda_TASIMA_uyarisi_acik():
    h = _kanat(hucre_butcesi=100_000)
    assert h["ulasilabilir"] is False
    assert "TAŞIMA" in h["hukum"] and "Kutta" in h["hukum"]
    assert "Sürükleme kullanılabilir" in h["hukum"]


def test_olculmemis_incelik_HUKUM_uretmiyor():
    """Ölçüm yoksa iddia da olmamalı."""
    assert vp.ince_ozellik_hukmu(None, 0.01, 3) is None
    assert vp.ince_ozellik_hukmu(0.0, 0.01, 3) is None
    assert vp.ince_ozellik_hukmu(0.003, 0.0, 3) is None


def test_boru_hatti_KOSUDAN_ONCE_cagiriyor():
    import inspect
    src = inspect.getsource(vp.run_vehicle_analysis)
    i_ince = src.index("ince_ozellik_hukmu(")
    i_case = src.index("case = CFDCase(")
    assert i_ince < i_case, "hüküm çözücüden SONRA hesaplanıyor"
    assert "kurulum_uyarilari.append" in src[i_ince:i_ince + 900]
    assert '"ince_ozellik"' in src                 # sonuca da yazılıyor


def test_gosterilen_sayi_HUKUMLE_celismiyor():
    """`:.1f` ile 5.99 "6.0" yazılıp aynı cümlede "hedef ≥6" denince okuyan haklı
    olarak "neden şikâyet ediyor" diye sorar (multikopter vakasında görüldü)."""
    h = vp.ince_ozellik_hukmu(0.00599, 0.008, 3)      # tam 5.99 hücre
    assert h["yeterli"] is False
    assert "5.99" in h["hukum"] and "6.0 hücre" not in h["hukum"]
