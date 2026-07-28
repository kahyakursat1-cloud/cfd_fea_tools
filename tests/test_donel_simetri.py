"""Dönel simetri özelliği ve multikopter kuralı — NX ayrık test setiyle ölçülen davranış.

Bu özelliğin varlık sebebi ölçülmüş bir kusurdur: kuralın multikopter dalı H/L ≥ 0.30
istiyordu ve bilinen 33 multikopterin hepsinde H/L ≤ 0.28 — dal ULAŞILAMAZDI. Eşiği
gevşetmek denendi ve GERİLEDİ (ayrık sette %51.2 → %34.1), çünkü radyal doluluk
multikopterle uçağı ayırmıyor. Ayıran şey 360/k dönel simetri.

Testler üç şeyi bağlar: (1) özellik analitik şekillerde beklendiği gibi davranıyor,
(2) tek-açılı (yalnız 90°) sürüme geri dönülmüyor — tri/hexa kopter onu yeniyordu,
(3) tohum hijyeni: ayrık test ailesi öğrenme kütüphanesine sızmıyor.
"""
import json
from pathlib import Path

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("shapely")

from auto_pilot import (  # noqa: E402
    MULTIKOPTER_DOLULUK_ESIGI,
    MULTIKOPTER_SIMETRI_ESIGI,
    NX_SEED,
    _features,
    classify_vehicle,
)
from vehicle_pipeline import DONEL_KATLAR, _donel_simetri  # noqa: E402

KOK = Path(__file__).resolve().parent.parent
KANIT = KOK / "nx_siniflandirici.json"


def _spoke(n_kol: int, acik: float = 1.0, kol: float = 0.05) -> trimesh.Trimesh:
    """n kollu yıldız gövde — multikopter topolojisinin en yalın hali."""
    parcalar = [trimesh.creation.box(extents=(acik * 0.22, acik * 0.22, acik * 0.14))]
    for i in range(n_kol):
        a = 2 * np.pi * i / n_kol
        kutu = trimesh.creation.box(extents=(acik / 2, kol, kol))
        kutu.apply_transform(trimesh.transformations.translation_matrix((acik / 4, 0, 0)))
        kutu.apply_transform(trimesh.transformations.rotation_matrix(a, (0, 0, 1)))
        parcalar.append(kutu)
    return trimesh.util.concatenate(parcalar)


def test_kup_ve_kure_tam_simetrik():
    assert _donel_simetri(trimesh.creation.box(extents=(1, 1, 1))) == pytest.approx(1.0, abs=0.02)
    assert _donel_simetri(trimesh.creation.icosphere(subdivisions=3)) == pytest.approx(
        1.0, abs=0.02)


def test_uzun_ince_cisim_simetrisiz():
    """Roket üst-görünümü uzun ince dikdörtgen — hiçbir katta oturmaz."""
    assert _donel_simetri(trimesh.creation.box(extents=(2.0, 0.2, 0.2))) < 0.25


@pytest.mark.parametrize("n_kol", [3, 4, 6, 8])
def test_cok_kollu_govde_simetrik(n_kol):
    """ASIL TEST: 3 ve 6 kollu gövde 90°'de simetrik DEĞİLDİR. Yalnız 90° bakan ilk
    sürüm tri-kopteri 0.08, hexa-kopteri 0.15 ölçüyordu; ayrı NX eğitim ailesi
    yakaladı. Çok-katlı arama bu sınıfı kurtarır."""
    assert _donel_simetri(_spoke(n_kol)) >= MULTIKOPTER_SIMETRI_ESIGI


def test_iki_kat_kasitli_disarida():
    """2-kat simetri uçakta da yüksektir; dahil edilirse ayırt ediciliği yok eder."""
    assert 2 not in DONEL_KATLAR
    assert {3, 4} <= set(DONEL_KATLAR)


def test_kanat_benzeri_govde_simetrik_degil():
    """Kanat bir yöne, gövde diğerine → hiçbir katta oturmamalı."""
    kanat = trimesh.creation.box(extents=(0.25, 2.0, 0.04))
    govde = trimesh.creation.box(extents=(1.6, 0.16, 0.16))
    assert _donel_simetri(trimesh.util.concatenate([kanat, govde])) < MULTIKOPTER_SIMETRI_ESIGI


def test_okunamayan_geometride_None_doner():
    """'Bilinmiyor' 0 ya da 1 diye varsayılamaz — kural bu durumda ateşlenmemeli."""
    bos = trimesh.Trimesh(vertices=np.zeros((3, 3)), faces=np.array([[0, 1, 2]]))
    assert _donel_simetri(bos) is None


def test_kural_simetri_yoksa_ateslenmez():
    """donel_simetri None iken multikopter dalı sessiz kalmalı."""
    geo = {"boyutlar_m": [1.0, 1.0, 0.2], "on_alan_m2": 0.2, "planform_alan_m2": 1.0,
           "govde_sayisi": 1, "radyal_doluluk": 0.25, "donel_simetri": None}
    assert classify_vehicle(geo)["kural_tip"] != "multikopter"


def test_kural_simetri_ve_spoke_varken_multikopter():
    geo = {"boyutlar_m": [1.0, 1.0, 0.2], "on_alan_m2": 0.2, "planform_alan_m2": 1.0,
           "govde_sayisi": 1, "radyal_doluluk": 0.25, "donel_simetri": 0.95}
    assert classify_vehicle(geo)["kural_tip"] == "multikopter"


def test_surekli_yuzey_simetrik_olsa_da_multikopter_degil():
    """Disk/küre simetriktir ama spoke değildir — doluluk kapısı tutmalı."""
    geo = {"boyutlar_m": [1.0, 1.0, 0.2], "on_alan_m2": 0.2, "planform_alan_m2": 1.0,
           "govde_sayisi": 1, "radyal_doluluk": 1.0, "donel_simetri": 1.0}
    assert classify_vehicle(geo)["kural_tip"] != "multikopter"
    assert MULTIKOPTER_DOLULUK_ESIGI < 1.0


def test_ulasilamaz_esik_geri_gelmedi():
    """Regresyon kilidi: dal yassılığa geri bağlanırsa yine hiç ateşlenmez."""
    import inspect

    import auto_pilot
    src = inspect.getsource(auto_pilot.classify_vehicle)
    i = src.index('score["multikopter"]')
    kosul = src[max(0, i - 400):i]
    assert "donel" in kosul, "multikopter dalı dönel simetriye bağlı olmalı"
    assert "compact >= 0.3" not in kosul


def test_knn_ozellik_vektorunde_simetri_var():
    """kNN de görmezse kural doğru hüküm verse bile kütüphane onu bozar (ölçüldü)."""
    a = _features({"L_D": 2, "W_L": 1, "H_L": 0.2, "H_W": 0.2, "govde": 1,
                   "planform_frontal": 5, "ince_yassilik": 0.2, "radyal_doluluk": 0.3,
                   "donel_simetri": 1.0})
    b = {"L_D": 2, "W_L": 1, "H_L": 0.2, "H_W": 0.2, "govde": 1, "planform_frontal": 5,
         "ince_yassilik": 0.2, "radyal_doluluk": 0.3, "donel_simetri": 0.0}
    assert a != _features(b), "simetri özellik vektörüne girmiyor"
    assert len(a) == 9


def test_eski_kayitlar_simetrik_sayilmaz():
    """donel_simetri'si olmayan eski kayıt 0.0 (simetrisiz) sayılmalı; 1.0 sayılırsa
    tüm kütüphane sahte-multikopter komşusu olur."""
    yok = _features({"L_D": 2, "W_L": 1, "H_L": 0.2, "H_W": 0.2, "govde": 1,
                     "planform_frontal": 5, "ince_yassilik": 0.2, "radyal_doluluk": 0.3})
    assert yok[-1] == 0.0


@pytest.mark.skipif(not NX_SEED.exists(), reason="NX tohumu üretilmemiş")
def test_tohum_hijyeni_test_ailesi_sizmadi():
    """Ayrık test ailesi öğrenme kütüphanesine girerse ölçüm değersizleşir."""
    from experiments.nx_tohum_uret import test_ailesi_tohumlanmadi
    assert test_ailesi_tohumlanmadi()


@pytest.mark.skipif(not KANIT.exists(), reason="NX değerlendirmesi koşulmamış")
class TestAyrikOlcum:
    @staticmethod
    def _o():
        return json.loads(KANIT.read_text(encoding="utf-8"))["ozet"]

    def test_preset_dogrulugu_raporlaniyor(self):
        """İnce etiket hatası her zaman analiz hatası değildir (tilt_rotor da 'ucak'
        preset'i kullanır). Kullanıcıyı ilgilendiren metrik preset'tir."""
        o = self._o()
        assert "preset_dogruluk" in o
        assert o["preset_dogruluk"] >= o["son_ince_dogruluk"]

    def test_knn_dogru_kural_hukmunu_bozmuyor(self):
        assert self._o()["knn_bozdugu"] == []

    def test_tessellation_hukmu_degistirmiyor(self):
        """Aynı katı, farklı üçgen yoğunluğu → aynı sınıf. Aksi halde hüküm
        geometriye değil mesh ayarına bağlıdır."""
        t = self._o()["tessellation"]
        assert t["cift_sayisi"] >= 5 and t["kararsiz"] == []

    def test_korluk_beyani_kanitta_duruyor(self):
        """Son eğitim eklemesi test-seti hata analizine dayanıyor; ölçüm artık tam kör
        değil. Bu, sayının yanında DURMALI — yoksa %100 preset doğruluğu hak edilmemiş
        bir güven verir."""
        d = json.loads(KANIT.read_text(encoding="utf-8"))
        assert "TAM KOR DEGIL" in d["_korluk"]
        assert "hata analizidir" in d["_korluk"]
        assert "nx_siniflandirici_kor.json" in d["_korluk"], "kör sayıya yol gösterilmeli"

    def test_preset_dogrulugu_gerilemedi(self):
        """Regresyon kilidi: ölçülen taban %100 (41 geometri). Altına düşerse
        sınıflandırıcıya dokunan bir değişiklik analiz ayarını bozmuş demektir."""
        assert self._o()["preset_dogruluk"] >= 1.0


KOR = KOK / "nx_siniflandirici_kor.json"


@pytest.mark.skipif(not KOR.exists(), reason="kör ölçüm koşulmamış")
class TestKorOlcum:
    """Üçüncü aile — hiçbir tasarım/kalibrasyon/hata-analizi turuna girmedi."""

    @staticmethod
    def _d():
        return json.loads(KOR.read_text(encoding="utf-8"))

    def test_tam_kor_beyani(self):
        assert "TAM KOR." in self._d()["_korluk"]

    def test_preset_dogrulugu_taban(self):
        """Ölçülen kör taban %96.3 (27 geometri). Altına düşerse genelleme bozulmuştur."""
        assert self._d()["ozet"]["preset_dogruluk"] >= 0.96

    def test_multikopter_dali_kor_ailede_de_calisiyor(self):
        """ASIL KANIT: dönel simetri özelliği uydurma değil. Kör ailedeki multikopterler
        Y6 (3 kol, koaksiyel) ve UZATILMIŞ hexa — ikisi de eğitim ailesinde YOK.
        Kural bunları kendi başına bulabiliyorsa özellik gerçekten genelleşiyor."""
        mk = [k for k in self._d()["kayitlar"] if k["gercek"] == "multikopter"]
        assert len(mk) >= 4
        assert all(k["kural"] == "multikopter" for k in mk), \
            [(k["ad"], k["kural"]) for k in mk]

    def test_knn_kor_ailede_de_bozmuyor(self):
        assert self._d()["ozet"]["knn_bozdugu"] == []
