"""Girdi belirsizliği yayılımı — ASME V&V 20'nin eksik adımı.

Yayımlanan Cd bandı YALNIZ ayrıklaştırmaydı. Ölçüldü (MiniHawk kanat, α=4°):
girdi kaynaklı belirsizlik ±%11.22, yayımlanan ±%1.74'ün 6.5 KATI ve BASKIN
terim. Yani "Cd = X ± %1.74" yazmak, olmayan bir kesinlik yayımlamaktı.
"""
import json
import math
from pathlib import Path

from girdi_belirsizligi import GirdiBelirsizligi, birlestir, yay

KOK = Path(__file__).resolve().parent.parent


class TestYayilim:
    def test_ANALITIK_turevle_ayni(self):
        """f = a·x²  →  ∂f/∂x = 2ax; sonlu fark bunu bulmalı."""
        def f(x):
            return 3.0 * x ** 2
        s = yay(f, [GirdiBelirsizligi("x", 2.0, 0.1, bagil=False)])
        assert abs(s.deger - 12.0) < 1e-9
        assert abs(s.u_toplam - abs(2 * 3.0 * 2.0) * 0.1) < 1e-6

    def test_BAGIMSIZ_girdiler_KARELER_toplamiyla(self):
        def f(x, y):
            return 2.0 * x + 5.0 * y
        s = yay(f, [GirdiBelirsizligi("x", 1.0, 0.1, bagil=False),
                    GirdiBelirsizligi("y", 1.0, 0.2, bagil=False)])
        beklenen = math.hypot(2.0 * 0.1, 5.0 * 0.2)
        assert abs(s.u_toplam - beklenen) < 1e-6

    def test_BASKIN_girdi_dogru_secilir(self):
        def f(x, y):
            return x + 100.0 * y
        s = yay(f, [GirdiBelirsizligi("x", 1.0, 0.1, bagil=False),
                    GirdiBelirsizligi("y", 1.0, 0.1, bagil=False)])
        assert s.baskin == "y"

    def test_DUYARSIZ_girdi_sifir_pay(self):
        def f(x, y):
            return x
        s = yay(f, [GirdiBelirsizligi("x", 1.0, 0.1, bagil=False),
                    GirdiBelirsizligi("y", 1.0, 0.1, bagil=False)])
        assert s.paylar["y"] == 0.0 or abs(s.paylar["y"]) < 1e-9

    def test_FONKSIYON_None_donerse_OLCULEMEDI(self):
        """Kapıya takılan girdi SIFIR pay sayılmamalı; toplam ALT SINIR olur."""
        def f(x, y):
            return None if abs(y - 1.0) > 1e-12 else x
        s = yay(f, [GirdiBelirsizligi("x", 1.0, 0.1, bagil=False),
                    GirdiBelirsizligi("y", 1.0, 0.1, bagil=False)])
        assert s.paylar["y"] == "ÖLÇÜLEMEDİ"
        assert "ALT SINIR" in s._kisit

    def test_NOMINAL_bozuksa_sayi_URETMIYOR(self):
        def f(x):
            return float("nan")
        s = yay(f, [GirdiBelirsizligi("x", 1.0, 0.1, bagil=False)])
        assert math.isnan(s.deger)
        assert "sayı döndürmedi" in s._kisit

    def test_BAGIL_ve_MUTLAK_belirsizlik(self):
        assert GirdiBelirsizligi("v", 20.0, 0.05, True).u_mutlak == 1.0
        assert GirdiBelirsizligi("a", 4.0, 0.5, False).u_mutlak == 0.5


class TestBirlestirme:
    def test_OLCULMEYEN_bilesen_SIFIR_sayilmiyor(self):
        b = birlestir({"girdi": 10.0, "ayriklastirma": 2.0, "model_form": None})
        assert b["alt_sinir_mi"] is True
        assert "model_form" in b["olculmeyen_bilesenler"]
        assert "ALT SINIR" in b["_anlam"]
        # birlestir 3 haneye yuvarlar; tolerans onu karsilamali
        assert abs(b["u_toplam_pct"] - math.hypot(10.0, 2.0)) < 1e-3

    def test_TUM_bilesenler_olculdugunde_alt_sinir_DEGIL(self):
        b = birlestir({"a": 3.0, "b": 4.0})
        assert b["alt_sinir_mi"] is False
        assert abs(b["u_toplam_pct"] - 5.0) < 1e-9


class TestKanit:
    """Üretilen kanıt, birleştiricinin yayımladığı sayıyla AYNI zincirden
    gelmeli; farklı zincir BAŞKA BİR BÜYÜKLÜĞÜN belirsizliğini verir."""

    def _d(self):
        p = KOK / "girdi_uq_kanat.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def test_ZINCIR_birlestiriciyle_AYNI(self):
        d = self._d()
        if not d:
            return
        import polar_birlestirme as pb
        v = pb._depo_verisi()
        o = pb.birlesik_polar(
            v["vlm_polar"], v["kesit"], re_kanat=v["re_kanat"],
            re_kesit=v["re_kesit"],
            kesit_cd_mesh_bagimsiz=v["kesit_cd_mesh_bagimsiz"],
            kesit_cd_band_pct=v.get("kesit_cd_band_pct"),
            vlm_ar=v.get("vlm_ar"), vlm_taper=v.get("vlm_taper"),
            vlm_ok_acisi=v.get("vlm_ok_acisi"),
            **{k: v[k] for k in ("kesit_simetrik", "vlm_simetrik")
               if v.get(k) is not None})
        n4 = next((x for x in o["noktalar"] if x["alpha"] == 4.0), None)
        if not n4 or "Cd_toplam" not in n4:
            return
        bagil = abs(d["Cd_nominal"] - n4["Cd_toplam"]) / n4["Cd_toplam"]
        assert bagil < 0.02, (
            f"UQ modeli {d['Cd_nominal']} veriyor, birlestirici "
            f"{n4['Cd_toplam']} — ayni zincir degil")

    def test_BASKIN_girdi_ve_KISIT_yazili(self):
        d = self._d()
        if not d:
            return
        assert d["baskin_girdi"] in {g["ad"] for g in d["girdiler"]}
        assert "RANS YOLUNDA YAYILMADI" in d["_kisit"]
        assert d["toplam_belirsizlik"]["alt_sinir_mi"] is True

    def test_BIRLESTIRICI_girdi_bandini_SOYLUYOR(self):
        """Ölçüm tüketiciye ulaşmalı: yayımlanan band girdi bileşenini
        içermiyorsa bu AÇIKÇA yazılmalı."""
        if not (KOK / "girdi_uq_kanat.json").exists():
            return
        import polar_birlestirme as pb
        v = pb._depo_verisi()
        o = pb.birlesik_polar(
            v["vlm_polar"], v["kesit"], re_kanat=v["re_kanat"],
            re_kesit=v["re_kesit"],
            kesit_cd_mesh_bagimsiz=v["kesit_cd_mesh_bagimsiz"],
            kesit_cd_band_pct=v.get("kesit_cd_band_pct"),
            vlm_band_pct=v.get("vlm_band_pct"),
            vlm_ar=v.get("vlm_ar"), vlm_taper=v.get("vlm_taper"),
            vlm_ok_acisi=v.get("vlm_ok_acisi"),
            **{k: v[k] for k in ("kesit_simetrik", "vlm_simetrik")
               if v.get(k) is not None})
        assert any("GİRDİ BELİRSİZLİĞİ" in u for u in o["uyarilar"])
        n = next((x for x in o["noktalar"] if x.get("Cd_band_pct")), None)
        if n:
            assert "girdi" in n.get("Cd_band_kapsam", "").lower()
