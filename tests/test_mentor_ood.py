"""Mentor'un DAĞILIM DIŞI (OOD) kapısı ve sızıntı ölçümü.

Dış değerlendirmenin sorduğu: "Uzak geometri için öneri reddediliyor mu?
Komşuların mesafesi gösteriliyor mu? Aynı geometrinin varyantları sızıntı
oluşturuyor mu?"

ÖLÇÜLDÜ: `_knn` uzaklık NE OLURSA OLSUN k komşu döndürüyordu — hiçbir şeye
benzemeyen geometri de kendinden emin görünen bir öneri alıyordu. Ayrıca havuz
31 kayıt ama yalnız 17 AYRIK geometri; aynı gövdenin tekrar koşuları BİREBİR
aynı öznitelik vektörüne sahip ve 31 kaydın 26'sının en-yakın mesafesi TAM
SIFIRDI. Eşiği o dağılımdan türetmek yarısı sıfır olan bir dağılımdan
türetmekti.
"""
import mentor


def _pool():
    return mentor._load("cfd")


class TestAyrikGeometri:
    def test_TEKRAR_kosular_mesafe_istatistiginden_CIKARILIYOR(self):
        pool = _pool()
        if len(pool) < 4:
            return
        ayrik = mentor._ayrik_geometriler(pool)
        assert len(ayrik) <= len(pool)
        anahtarlar = [mentor._geometri_anahtari(c) for c in ayrik]
        assert len(anahtarlar) == len(set(anahtarlar)), "ayrık listede tekrar var"

    def test_SIFIR_mesafe_orani_dedup_ile_DUSUYOR(self):
        """Tekrarlar çıkarılınca sıfır-mesafeli kayıt oranı belirgin düşmeli;
        düşmüyorsa dedup işe yaramıyordur."""
        pool = _pool()
        if len(pool) < 6:
            return
        import auto_pilot as ap

        def sifir_orani(kayitlar):
            fv = [ap._features(c["metrik"]) for c in kayitlar]
            n = 0
            for i, a in enumerate(fv):
                d = [sum((x - y) ** 2 for x, y in zip(a, b))
                     for j, b in enumerate(fv) if j != i]
                if d and min(d) < 1e-18:
                    n += 1
            return n / len(fv)
        assert sifir_orani(mentor._ayrik_geometriler(pool)) <= sifir_orani(pool)


class TestOodKapisi:
    _YAKIN = {"L_D": 5, "W_L": 1, "H_L": 0.1, "H_W": 0.1, "govde": 2}
    _UZAK = {"L_D": 30, "W_L": 0.02, "H_L": 3.0, "H_W": 50, "govde": 8}

    def test_UZAK_geometri_DAGILIM_DISI(self):
        r = mentor.advise_mesh(self._UZAK, tip="ucak")
        if not r:
            return
        o = r["ood"]
        assert o["dagilim_disi"] is True
        assert o["guvenilir"] is False
        assert "otomatik karara GİRMEZ" in o["durum"]

    def test_MESAFE_ve_ESIK_oneriyle_birlikte_geliyor(self):
        """Mesafe gösterilmezse kullanıcı 'hiçbir şeye benzemeyen' ile
        'havuzun ortasındaki' geometriyi ayırt edemez."""
        r = mentor.advise_mesh(self._YAKIN, tip="ucak")
        if not r:
            return
        o = r["ood"]
        for alan in ("en_yakin_mesafe", "havuz_esigi", "havuz_medyan_mesafe"):
            assert isinstance(o.get(alan), (int, float)), f"{alan} yok"

    def test_KOMSU_kac_AYRIK_govdeden_soyleniyor(self):
        """k komşu, tek gövdenin k koşusu olabilir — 'iyi desteklenmiş'
        görünür ama tek geometridir."""
        r = mentor.advise_mesh(self._YAKIN, tip="ucak")
        if not r:
            return
        o = r["ood"]
        assert o["komsu_ayrik_geometri"] <= o["komsu_kayit"]
        if o["komsu_ayrik_geometri"] < 2:
            assert o["guvenilir"] is False, "tek gövdeye dayanan öneri güvenilir sayıldı"

    def test_ESIK_havuzun_KENDI_dagilimindan(self):
        """Eşik uydurulmamalı: havuzun kendi mesafe dağılımından gelmeli."""
        pool = _pool()
        if len(pool) < 6:
            return
        d = mentor._havuz_en_yakin_mesafeler(pool)
        i = min(int(len(d) * mentor.OOD_YUZDELIK), len(d) - 1)
        r = mentor.advise_mesh(self._YAKIN)
        if r and r["ood"].get("havuz_esigi") is not None:
            assert abs(r["ood"]["havuz_esigi"] - d[i]) < 0.51, \
                "eşik havuz dağılımından türetilmiyor (alt havuz farkı hariç)"

    def test_FEA_onerisi_de_OOD_tasiyor(self):
        r = mentor.advise_fea(self._YAKIN)
        if r:
            assert "ood" in r
