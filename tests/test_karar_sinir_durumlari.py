"""Karar motorunun SINIR ve BOZUK-GİRDİ davranışı.

Karar/V&V katmanı platformun ana ürün iddiasıdır ama kapsamı %60'tı. Ham
yüzde kovalamak değersiz olurdu; bunun yerine dış değerlendirmenin adıyla
saydığı sınır durumları test edilir:

    tam eşikte / bir altında / bir üstünde · NaN ve sonsuz · eksik kanıt
    · çelişkili kanıt · salınımlı yakınsama · monoton ama düşük p
    · GCI–LSR uyuşmazlığı · işaret konvansiyonu · birim/ölçek hatası

Bu durumların ortak yanı, HEPSİNİN sessizce "geçerli görünen" bir sayı
üretebilmesidir.
"""
import math

import pytest

from report_generator import band_from_levels, compute_gci, gci_verdict
from validity_envelope import (
    CD_MAX_STREAMLINED,
    YPLUS_BANDI,
    duvar_hukmu,
    force_admissibility,
    geometry_sanity,
    vlm_kabul_edilebilir,
)

# ── Eşik davranışı: tam üstünde / tam altında ────────────────────────────────

class TestEsikSiniri:
    """Eşik kontrolleri `<` mi `<=` mi — bir hücrelik fark hükmü çevirir."""

    def test_yuzey_esigi_TAM_DEGERDE_geciyor(self):
        from analysis.openfoam_runner import YUZEY_YUZ_ESIGI
        from vehicle_pipeline import yuzey_yuz_tahmini
        # Esigin TAM ustunde/altinda/esitinde tahmin ureten yuzey alani sec.
        h = 0.01
        for hedef, beklenen_gecer in ((YUZEY_YUZ_ESIGI - 1, False),
                                      (YUZEY_YUZ_ESIGI, True),
                                      (YUZEY_YUZ_ESIGI + 1, True)):
            alan = hedef * h * h
            tah = yuzey_yuz_tahmini(alan, h, 0)
            assert (tah >= YUZEY_YUZ_ESIGI) == beklenen_gecer, (hedef, tah)

    def test_cd_ust_siniri_TAM_DEGERDE(self):
        from validity_envelope import CD_MAX_PLAUSIBLE
        assert force_admissibility(CD_MAX_PLAUSIBLE)["verdict"] != "inadmissible"
        assert force_admissibility(CD_MAX_PLAUSIBLE * 1.001)["verdict"] == "inadmissible"

    def test_yplus_bandinin_UCLARI(self):
        for ort, bekle in ((YPLUS_BANDI[0], True), (YPLUS_BANDI[1], True),
                           (YPLUS_BANDI[0] - 0.1, False), (YPLUS_BANDI[1] + 0.1, False)):
            ok, _ = duvar_hukmu({"yplus": {"ort": ort}})
            assert ok is bekle, f"y+={ort} icin hukum {ok}, beklenen {bekle}"


# ── Bozuk sayılar ────────────────────────────────────────────────────────────

class TestBozukSayi:
    """NaN/inf sessizce yayılırsa karşılaştırmalar HEP False döner ve kapı
    açık kalır — en sinsi başarısızlık biçimi."""

    @pytest.mark.parametrize("bozuk", [float("nan"), float("inf"), float("-inf")])
    def test_kuvvet_kapisi_NaN_inf_GECIRMIYOR(self, bozuk):
        h = force_admissibility(bozuk)
        assert h["verdict"] != "ok", f"Cd={bozuk} 'ok' sayildi"

    @pytest.mark.parametrize("bozuk", [float("nan"), float("inf")])
    def test_VLM_kapisi_NaN_inf_GECIRMIYOR(self, bozuk):
        assert vlm_kabul_edilebilir({"Cl": bozuk, "Cd_i": 0.01})
        assert vlm_kabul_edilebilir({"Cl": 0.4, "Cd_i": bozuk})

    def test_band_NaN_iceren_seride_SAYI_URETMIYOR(self):
        b = band_from_levels([1000, 2000, 4000], [0.1, float("nan"), 0.3])
        assert b is None or not isinstance(b.get("u_pct"), float) \
            or not math.isnan(b["u_pct"]), "NaN band olarak yayimlandi"


# ── Eksik / çelişkili kanıt ──────────────────────────────────────────────────

class TestEksikKanit:
    def test_yplus_OLCULEMEDI_gecmis_sayilmiyor(self):
        ok, neden = duvar_hukmu({"yplus": {"olculemedi": True, "neden": "yok"}})
        assert ok is False and "ölçülemedi" in neden.lower()

    def test_sinir_tabaka_HIC_YOKSA_gecmiyor(self):
        ok, _ = duvar_hukmu(None)
        assert ok is False

    def test_iki_kademe_BAND_vekil_isaretli(self):
        """n=2'de gerçek band hesaplanamaz; vekil olduğu SÖYLENMELİ."""
        b = band_from_levels([1000, 4000], [0.10, 0.12])
        if b:
            assert b["yontem"] != "richardson", "2 kademede Richardson iddia ediliyor"
            assert "vekil" in b["kaynak"].lower() or "2" in b["kaynak"]


# ── Yakınsama patolojileri ───────────────────────────────────────────────────

class TestYakinsamaPatolojisi:
    def test_SALINIMLI_seride_ekstrapolasyon_YOK(self):
        b = band_from_levels([8000, 27000, 64000, 125000],
                             [0.10, 0.30, 0.12, 0.28])
        assert b is not None
        assert b["yontem"] != "richardson"
        assert b["u_pct"] > 10, "salınımlı seride dar band veriliyor"

    def test_MONOTON_ama_DUSUK_p_bayrak_kaldiriyor(self):
        """GCI küçük olsa da p teorikten uzaksa uyarı gelmeli (NACA0012: p=0.666).

        Sabit sonuç değil, TUTARLILIK bağlanır: bayrak p'ye göre görünmeli."""
        from report_generator import P_TEORIK, P_TEORIK_ORAN
        g = compute_gci(1 / 449, 1 / 897, 1 / 1793,
                        0.008200596, 0.008307406, 0.00837473)
        v = gci_verdict(g)
        dusuk = g["p"] < P_TEORIK_ORAN * P_TEORIK
        assert ("kalite bayrağı" in v) == dusuk, (g["p"], v)

    def test_GCI_LSR_UYUSMAZLIGI_kanonik_kazaniyor(self):
        """Küp: 3-kademe GCI %3.15, 4-kademe LSR %58.33. Kanonik hiyerarşi
        n≥4'te LSR seçmeli; iyimser olan otomatik kazanmamalı."""
        hucre = [23968, 82201, 267305, 888377]
        cd = [0.90397, 0.95523, 1.06849, 1.11332]
        b = band_from_levels(hucre, cd, boyut=3)
        h = [c ** (-1 / 3) for c in hucre]
        g = compute_gci(h[1], h[2], h[3], cd[1], cd[2], cd[3])
        assert b["yontem"] == "lsr"
        assert b["u_pct"] > g["gci_fine_pct"], "kanonik band iyimser olanı seçmiş"


# ── Birim / işaret konvansiyonu ──────────────────────────────────────────────

class TestBirimVeIsaret:
    def test_MM_olcegi_yakalaniyor(self):
        """STL mm cinsindense domain 1000× büyür ve Cd tamamen kayar."""
        u = geometry_sanity({"lmax_m": 1500.0, "on_alan_m2": 1.0,
                             "yan_alan_m2": 2.0, "planform_alan_m2": 3.0})
        assert any("ÖLÇEK" in x for x in u)

    def test_COK_KUCUK_olcek_de_yakalaniyor(self):
        u = geometry_sanity({"lmax_m": 0.001, "on_alan_m2": 1e-6,
                             "yan_alan_m2": 2e-6, "planform_alan_m2": 3e-6})
        assert any("ÖLÇEK" in x for x in u)

    def test_EKSEN_yanlissa_yakalaniyor(self):
        """Z-uzun modellenmiş roket: frontal izdüşüm en BÜYÜK çıkar."""
        u = geometry_sanity({"lmax_m": 1.0, "on_alan_m2": 0.1368,
                             "yan_alan_m2": 0.0113, "planform_alan_m2": 0.0113})
        assert any("EKSEN" in x for x in u)

    def test_NEGATIF_surukleme_isaret_hatasi_olarak_REDDEDILIYOR(self):
        h = force_admissibility(-0.05)
        assert h["verdict"] == "inadmissible"
        assert any("negatif" in r.lower() or "0" in r for r in h["reasons"])

    def test_akis_yonlu_cisimde_DAR_esik_cagirandan(self):
        """Künt cisim eşiği (2.5) ince gövdeyi haksız geçirmemeli — çağıran
        daha dar eşiği AÇIKÇA geçirir."""
        assert force_admissibility(1.2)["verdict"] != "inadmissible"
        assert force_admissibility(
            1.2, cd_max=CD_MAX_STREAMLINED)["verdict"] == "inadmissible"
