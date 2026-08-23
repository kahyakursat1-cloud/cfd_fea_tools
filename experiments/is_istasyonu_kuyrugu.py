"""İş istasyonu geldiğinde ne koşulacak — bütçeler KANITTAN okunur.

NEDEN BU DOSYA: bu oturumda kapanamayan her madde için bir fizibilite bütçesi
ÖLÇÜLDÜ ve ayrı kanıt dosyalarına yazıldı. Bir liste elle derlenirse, koşular
yenilendiğinde sessizce eskir --- bu deponun her yerde avladığı kusur. Liste
kanıt dosyalarından ÜRETİLİR.

NE YAPMAZ: öncelik SIRASI vermez. Sıra mühendislik kararıdır (hangi hücre
hangi projeye lazım); bu dosya yalnız MALİYETİ ve NEYİN AÇILACAĞINI verir.

    python experiments/is_istasyonu_kuyrugu.py
Çıktı: is_istasyonu_kuyrugu.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "is_istasyonu_kuyrugu.json"

# Hedef donanim — bellekte kayitli aday (1001-donanim-secenekleri).
HEDEF_GB = 192.0
# Bu makine, olculen bos bellek (makine-bellek-kisiti).
MEVCUT_GB = 4.62


def _j(ad: str) -> dict | None:
    p = KOK / ad
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    # sessiz-yutma: kabul — bozuk kanit dosyasi ADIYLA listeleniyor, atlanmiyor
    except json.JSONDecodeError:
        return None


def _kalem(hakem, ad, kanit, gb, hucre=None, sure=None, not_=None, acar=None):
    return {"hakem_maddesi": hakem, "is": ad, "kanit": kanit,
            "bellek_GB": gb, "hucre": hucre, "tahmini_sure": sure,
            "bu_makinede": (gb is not None and gb <= MEVCUT_GB),
            "is_istasyonunda": (gb is not None and gb <= HEDEF_GB),
            "neyi_acar": acar, "_not": not_}


def topla() -> list[dict]:
    out, eksik = [], []

    b = _j("bluff_duvar_cozunur_fizibilite.json")
    if b and b.get("ahmed_butcesi"):
        a = b["ahmed_butcesi"]
        out.append(_kalem(
            "—", "Ahmed gövdesi duvar-çözünür (y⁺≈1)",
            "bluff_duvar_cozunur_fizibilite.json",
            a.get("bellek_gb"), a.get("hucre_kestirimi"), a.get("sure_saat"),
            acar="model-form tablosunda bluff.wall_resolved hücresi "
                 "(bugün literatür öncülü, ölçüm yok)",
            not_="Bellek katsayısı ÖLÇÜLEN (3 koşu, bellek_katsayisi.json)."))
    else:
        eksik.append("bluff_duvar_cozunur_fizibilite.json")

    les = _j("silindir_les_fizibilite.json")
    if les and les.get("butce"):
        lb = les["butce"]
        out.append(_kalem(
            "#5", "Silindir duvar-çözümlü LES (türbülanslı zaman-çözünür çapa)",
            "silindir_les_fizibilite.json",
            lb.get("bellek_GB"), lb.get("hucre"), None,
            acar="türbülanslı zaman-çözünür ÇAPA; bugün elde olan doğrulanmış "
                 "çapa LAMİNER rejimde ve türbülanslı vakayı doğrulamıyor",
            not_="Subkritik Re'de tam-türbülanslı kapanış Cd'yi %39'a kadar "
                 "düşük veriyor (ölçüldü). Ucuz ara adım: geçiş modeli "
                 "kOmegaSSTLM ile aynı vakayı koşmak — LES'ten ÇOK ucuz."))
    else:
        eksik.append("silindir_les_fizibilite.json")

    f = _j("fsi_tahrik_fizibilite.json")
    if f and f.get("en_ucuz_ulasilabilir"):
        u, k = f["en_ucuz_ulasilabilir"], f.get("en_ucuzun_kotumser_ucu") or {}
        out.append(_kalem(
            "#12", f"Fizikle sürülen 2-yönlü FSI ({u['malzeme']}, "
                   f"{u['hiz_m_s']:.0f} m/s)",
            "fsi_tahrik_fizibilite.json",
            u.get("bellek_GB"), int(u["hucre_M"] * 1e6), None,
            acar="iki-yönlü FSI'nin FİZİKSEL olarak sürüldüğü ilk vaka",
            not_=(f"BÜTÇE BİR BAND: {u['bellek_GB']:.0f} GB (yüzey-yakın "
                  f"ölçekleme) – {k.get('bellek_GB', 0):,.0f} GB (hacim "
                  f"ölçekleme). Hangi ucun geçerli olduğu ÖLÇÜLMEDİ; iyimser "
                  f"uç tutmazsa iş istasyonunda da SIĞMAZ."
                  ).replace(",", ".")))
    else:
        eksik.append("fsi_tahrik_fizibilite.json")

    m = _j("model_form_kosullama.json")
    if m and (m.get("butce") or {}).get("fark_basina"):
        for x in m["butce"]["fark_basina"]:
            if x["ayirt_edilecek_fark_puan"] != 10.0:
                continue
            eksik_capa = x["toplam_MEVCUT_TABLO"] - m["mevcut_capa"]
            out.append(_kalem(
                "#13", f"Model-form tablosunu ölçülebilir kılmak "
                       f"({eksik_capa} yeni çapa)",
                "model_form_kosullama.json", None,
                None, f"~{eksik_capa} çapa koşusu",
                acar="10 puanlık hücre farkını AYIRT EDEBİLME; bugün 6 "
                     "hücrenin 5'inde tek çapa var ve tablonun veri-güdümlü "
                     "kısmı 3/6",
                not_="Bellek değil ÇAPA SAYISI kısıtı; iş istasyonu tek "
                     "başına açmaz, koşu zamanı açar."))
    else:
        eksik.append("model_form_kosullama.json")

    t = _j("girdi_uq_teshis.json")
    if t:
        out.append(_kalem(
            "#9", "Sıkı-yakınsama girdi-UQ taraması",
            "girdi_uq_teshis.json", None, None,
            "~30 koşu (iterasyon tavanı yükseltilmiş)",
            acar="u_girdi'nin GERÇEK değeri; bugünkü %0,89 bir ÜST SINIR "
                 "ve içindeki payın ne kadarının girdi olduğu ayrılamıyor",
            not_="İÇ DENETİM HAZIR: sıkı taramada NULL değişkenlerin "
                 "(küre için α, sabit-ν ile ρ) korelasyonu SIFIRA inmeli. "
                 "Geçmeden band yayımlanmaz."))

    return out, eksik


def olc() -> dict:
    kalemler, eksik = topla()
    is_ist = [k for k in kalemler if k["is_istasyonunda"]]
    bellek_gerektiren = [k for k in kalemler if k["bellek_GB"]]
    return {
        "vaka": "İş istasyonu kuyruğu — kapanamayan maddelerin ÖLÇÜLEN bütçeleri",
        "_neden": ("Bu oturumda kapanamayan her madde icin fizibilite butcesi "
                   "OLCULDU ve ayri kanit dosyalarina yazildi. Liste elle "
                   "derlenirse kosular yenilendiginde sessizce eskir."),
        "hedef_donanim_GB": HEDEF_GB,
        "bu_makine_bos_GB": MEVCUT_GB,
        "kalemler": kalemler,
        "kanit_eksik": eksik,
        "verdikt": (
            f"{len(kalemler)} açık kalem. Bellek gerektiren "
            f"{len(bellek_gerektiren)} kalemin {len(is_ist)}'i {HEDEF_GB:.0f} GB "
            f"iş istasyonunda sığıyor; bu makinede "
            f"{sum(1 for k in kalemler if k['bu_makinede'])}'i sığıyor. "
            f"Kalan kalemler bellek değil KOŞU ZAMANI ya da ÇAPA SAYISI "
            f"kısıtlı — donanım tek başına açmaz."),
        "_kisit": (
            "SIRA VERILMEZ: oncelik muhendislik kararidir (hangi hucre hangi "
            "projeye lazim). Bu dosya yalniz MALIYETI ve NEYIN ACILACAGINI "
            "verir. Ayrica butceler kestirimdir ve kendi kisitlarini kendi "
            "kanit dosyalarinda tasir — ozellikle FSI butcesi bir BAND ve "
            "iyimser ucu tutmazsa is istasyonunda da sigmaz."),
        "_uretim": "Üretim: python experiments/is_istasyonu_kuyrugu.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    print("İş istasyonu kuyruğu — ölçülen bütçeler\n")
    print(f"{'hakem':<7}{'iş':<52}{'bellek':>10}{'hücre':>12}  açar")
    for k in r["kalemler"]:
        gb = f"{k['bellek_GB']:.0f} GB" if k["bellek_GB"] else (k["tahmini_sure"] or "—")
        hu = f"{k['hucre']/1e6:.1f} M" if k["hucre"] else "—"
        im = "✓" if k["is_istasyonunda"] else (" " if k["bellek_GB"] else "·")
        print(f"{k['hakem_maddesi']:<7}{k['is'][:51]:<52}{gb:>10}{hu:>12} {im}")
    for k in r["kalemler"]:
        if k.get("_not"):
            print(f"\n  {k['is'][:60]}\n    {k['_not']}")
    if r["kanit_eksik"]:
        print(f"\nKANIT EKSİK (kalem listelenemedi): {r['kanit_eksik']}")
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
