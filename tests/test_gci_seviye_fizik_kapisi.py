"""Mesh-bağımsızlık seviyeleri de fizik kapısından geçmeli.

Gerçek vaka (MiniHawk, 2026-07-27): 4-seviye kampanyada en kaba seviye **Cd = 0.0**
üretti — uçak o çözünürlükte hiç çözülmemiş. Fizik kapısı ana sonuca uygulanıyordu ama
seviyelere uygulanmıyordu; fizik-dışı bir değer en ince üçe düşerse Richardson fitine
girer ve GCI'ı anlamsız kılar. (O kampanyada Cd=0.0 en kaba seviyedeydi ve fit zaten
en ince üçü kullandığı için sonucu değiştirmedi — kapı gelecek vakalar için.)
"""
import inspect
import re

import vehicle_pipeline
from report_generator import compute_gci, gci_verdict
from validity_envelope import force_admissibility

SRC = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)


def test_seviyeler_fizik_kapisindan_geciyor():
    i_kapi = SRC.index('lv_rec["fizik"] = force_admissibility')
    i_fit = SRC.index("compute_gci(h(f3)")
    assert i_kapi < i_fit, "seviye kapısı Richardson fitinden ÖNCE uygulanmalı"


def test_fizik_disi_seviye_kayitta_gerekcesiyle_kalir():
    """Dışlanan seviye silinmez — mühendis neyin atıldığını görmeli."""
    assert "fizik_disi_seviyeler" in SRC and "gerekce" in SRC


def test_sifir_cd_seviyesi_kabul_edilmez():
    """MiniHawk'ın ürettiği gerçek değer."""
    assert force_admissibility(0.0)["verdict"] == "inadmissible"


def test_fizik_disi_seviye_gci_i_ALDATICI_bicimde_iyilestirir():
    """Dışlamanın asıl gerekçesi — ölçüldü, sezgiye ters:

    Cd=0.0 içeren seri GCI'ı **%0.64** veriyor (mükemmel görünür!), fiziksel olarak
    sağlam seri ise %23.7. Yani fizik-dışı bir seviye bandı kötüleştirmiyor, ALDATICI
    biçimde İYİLEŞTİRİYOR. Tek uyarı işareti monotonluğun bozulması; onu da yalnız
    `gci_verdict` yakalıyor. Bu yüzden fizik kapısı fitten ÖNCE uygulanmalı.
    """
    def h(n):
        return n ** (-1.0 / 3.0)

    kirli = [(100_000, 0.0), (300_000, 0.030), (900_000, 0.028)]
    temiz = [(50_000, 0.035), (300_000, 0.030), (900_000, 0.028)]
    g_kirli = compute_gci(h(kirli[0][0]), h(kirli[1][0]), h(kirli[2][0]),
                          kirli[0][1], kirli[1][1], kirli[2][1])
    g_temiz = compute_gci(h(temiz[0][0]), h(temiz[1][0]), h(temiz[2][0]),
                          temiz[0][1], temiz[1][1], temiz[2][1])

    assert g_kirli["gci_fine_pct"] < g_temiz["gci_fine_pct"],         "fizik-dışı seviye GCI'ı iyileştiriyor olmalı (testin varlık sebebi)"
    assert not g_kirli["monotonic"] and not g_kirli["p_in_range"],         "tek uyarı işareti monotonluk/p — kaybolursa aldatıcı GCI sessizce geçer"
    assert g_temiz["monotonic"]
    # ...ve kanonik verdikt kirli seriyi REDDETMELİ
    assert gci_verdict(g_kirli).startswith("⚠️")


def test_kapi_alpha_ile_cagriliyor():
    """Taşıma işareti kontrolü için hücum açısı geçilmeli."""
    m = re.search(r'lv_rec\["fizik"\] = force_admissibility\(([^)]*)\)', SRC)
    assert m and "alpha_deg" in m.group(1)


def test_dusen_seviye_sessizce_atilmaz():
    """MiniHawk v2'de 'orta' seviye mesh kalite kapısında reddedildi (checkMesh:
    Failed 1) ve listeden SESSİZCE düştü; kullanıcı "yalnız 2 seviye tamamlandı"
    görüp NEDENİNİ bilemiyordu. Artık sebebiyle kaydediliyor."""
    src = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)
    assert "basarisiz.append" in src, "düşen seviye kaydedilmiyor"
    assert "basarisiz_seviyeler" in src, "sonuca taşınmıyor"
    assert "DÜŞEN SEVİYE" in src, "2-seviye yorumunda sebep gösterilmiyor"
    # kayıt, seviyeyi listeye eklemeden ÖNCE olmalı (continue ile)
    i_kayit = src.index("basarisiz.append")
    i_ekle = src.index("levels.append(lv_rec)")
    assert i_kayit < i_ekle


def test_dusen_seviye_sebebi_bos_kalmaz():
    """Sebep metni boşsa 'bilinmiyor' yazılmalı — boş string hiçbir şey söylemez."""
    src = inspect.getsource(vehicle_pipeline.run_vehicle_analysis)
    i = src.index("basarisiz.append")
    assert "bilinmiyor" in src[max(0, i - 400):i + 200]
