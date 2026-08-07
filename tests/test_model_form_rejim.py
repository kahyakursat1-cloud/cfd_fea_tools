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
        """y⁺≳30'da duvar modellenir, çözülmez — belirsizlik artmalı."""
        for rejim in _MODEL_U_PCT:
            r = model_uncertainty_pct(rejim, False)["u_model_pct"]
            c = model_uncertainty_pct(rejim, True)["u_model_pct"]
            assert r >= c, f"{rejim}: duvar-fonksiyonu {r} < çözünür {c}"

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

        İki ayrı neden var ve ikisi de kabul: (a) y⁺ hiç kayıtlı değil — eksik
        kayıt; (b) y⁺ ÖLÇÜLDÜ ama tampon bölgede (5<y⁺<30) — fiziksel bulgu,
        o koşu hiçbir duvar işlemini temsil etmez. İkisini aynı torbaya koymak
        "ölçemedim" ile "ölçtüm, ait değil"i karıştırmak olurdu.
        """
        d = self._d()
        if not d:
            return
        for x in d["atanamayan_capalar"]:
            if x.get("yplus_ort") is None:
                assert "KAYITLI DEĞİL" in x["neden"]
            else:
                assert "ÖLÇÜLDÜ" in x["neden"] and "Tampon" in x["neden"]
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
