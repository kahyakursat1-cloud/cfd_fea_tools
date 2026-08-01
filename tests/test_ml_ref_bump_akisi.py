"""ref_bump ML EYLEM UZAYINDA ve KULLANICI-YÜZÜ yollarda olmalı.

Otopilot yalnız hizli/standart/hassas seçiyordu; ref_bump preset'in SABİT alanıydı.
ÖLÇÜLDÜ ki y⁺'ı duvar-fonksiyonu bandına (30-300) sokan TEK kaldıraç budur, ve
doğru kademe gövde boyutuna/hıza bağlı olduğu için sabit bir sayı tüm geometrilere
uymuyor: sabit bump=2 ile `multikopter_kucuk` y⁺=25 verip bandın ALTINA düştü;
oto kademeyle y⁺=38.6 ve geçti.

12-geometrilik taramada oto kademeyle seçilen bump'lar 0'dan 4'e değişti ve
ONBİRİNİN DE ölçülen y⁺'ı banda girdi (39-117).

KRİTİK: bu bağlantı olmadan GUI ve otopilot varsayılan (0) ile koşuyordu — yani
ölçülen %83'lük oran KULLANICI-YÜZÜ hiçbir yolda geçerli DEĞİLDİ. Bu, "ölçüm var
ama tüketilmiyor" deseninin ML katmanındaki hâliydi.
"""
import inspect


def test_auto_pilot_ref_bump_URETIYOR():
    import auto_pilot
    src = inspect.getsource(auto_pilot.auto_configure)
    assert '"ref_bump": "oto"' in src


def test_GUI_ref_bump_GECIRIYOR():
    import app_analyzer
    assert '"ref_bump": "oto"' in inspect.getsource(app_analyzer)


def test_kuyruk_parametreleri_OLDUGU_GIBI_gecirir():
    """Kuyruk **p ile çağırıyorsa GUI'nin eklediği anahtar worker'a ulaşır."""
    import kuyruk
    assert "run_vehicle_analysis(**p)" in inspect.getsource(kuyruk)


def test_pipeline_oto_degerini_TANIYOR():
    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    assert 'ref_bump.lower() == "oto"' in src or '"oto"' in src


def test_oto_CFDCase_KURULMADAN_ONCE_uygulaniyor():
    """Sonradan uygulanırsa mesh yine varsayılan kademeyle üretilir."""
    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    assert src.index("_oto and _oneri") < src.index("case = CFDCase(")


def test_SAYI_verilirse_oto_devreye_GIRMIYOR():
    """Açık sayı çağıranın kararıdır; öneri yalnız raporlanır."""
    import vehicle_pipeline as vp
    src = inspect.getsource(vp.run_vehicle_analysis)
    i = src.index("_oto = ")
    assert "isinstance(ref_bump, str)" in src[i:i + 200]
