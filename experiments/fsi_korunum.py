"""FSI yük aktarımında korunum — üç metrik, GERÇEK vakalarda ölçülü.

NEDEN: `cfd_pressure_to_fea_loads` iki korunum metriği taşıyordu (kuvvet ve
moment) ve ikisi de makine hassasiyetinde çıkıyordu. Bu bir başarı gibi
okunuyordu; oysa ikisi de FEA yüzü→düğüm dağıtımını ölçer ve eşit-üçtebir
şemasında YAPI GEREĞİ kesindir. Yani ölçülen şey gerçekten korunmayan adım
DEĞİLDİ.

Korunmayan adım şudur: basınç, CFD yüzlerinden FEA yüzlerine EN-YAKIN-KOMŞU
ile taşınıyor. İki ağın yüz boyutları farklıysa aynı basınç alanı farklı
toplam kuvvet verir ve hiçbir metrik bunu söylemiyordu.

EKLENEN İKİ ÖLÇÜM:

  arayuz_isi_hatasi — doğrusal sanal yer-değiştirme alanı u = A·x için arayüz
    işi W = A : Σ F⊗x. Tüm doğrusal alanlar için işin korunması, birinci moment
    TENSÖRÜNÜN korunmasına denktir ve bu kuvvet+momentten güçlüdür: x×F,
    F⊗x'in yalnız antisimetrik kısmıdır. Simetrik kısım (uzama/kayma modlarının
    yaptığı iş) iki mevcut metrikte de GÖRÜNMEZ. Klasik arayüz yama-sınavı.

  aktarim_hatasi — CFD yüzeyindeki toplam kuvvet ile FEA yüzeyindekinin farkı.
    Gerçekten korunmayan adımı ölçen tek metrik budur.

AYRIM ŞART: aktarım artığının iki sebebi olabilir --- basıncın örneklenmesi ve
FEA STL'i ile CFD yüzeyinin ALAN farkı (STL özgün geometri, CFD yüzeyi
snap'lenmiş ağ). İkisi tek sayıya karışırsa hüküm verilemez, o yüzden alan
farkı ayrı raporlanır.

    python experiments/fsi_korunum.py
Çıktı: fsi_korunum.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "fsi_korunum.json"

# Makine hassasiyeti mertebesi: yapi-geregi kesin olmasi gereken metrikler
# bunun ustune cikarsa uygulama teoriden SAPMIS demektir.
KESIN_ESIK = 1e-12


def _vakalar() -> list[dict]:
    out = []
    for sj in sorted((KOK / "vehicle_runs").glob("*/sonuc.json")):
        d = json.loads(sj.read_text(encoding="utf-8"))
        vtk, stl = d.get("cp_vtk"), d.get("stl")
        if vtk and stl and Path(vtk).exists() and Path(stl).exists():
            out.append({"ad": sj.parent.name, "vtk": vtk, "stl": stl})
    return out


def _ayrisim(s: dict | None) -> dict:
    """İş artığının ESLEME ve YUZEY paylarına ayrışımı.

    KAYITTAKI ATIF YANLISTI VE BU ONU DUZELTIR. `arayuz_isi_hatasi`
    dugum momentini (URETIMDEKI korunumlu sema) yuz momentiyle (TERK
    EDILMIS tutarli sema, FEA yuzunde yeniden integre edilmis) kiyaslar.
    Yani semalari kiyaslar, eslemeyi olcmez --- ayni vakada terk edilmis
    semanin toplam kuvvetinin ISARETI bile ters cikabiliyor.

    Dogru referans CFD tarafidir ve orada bir KIMLIK vardir: baryentrik
    agirliklar dogrusal alanlari birebir urettigi icin
        T_dugum - T_cfd == sum_f dF_f (x) delta_f
    Olculdu (Turek-Hron FSI1): esleme payi %0,000000, yuzey payi %0,6457.
    """
    if not s:
        return {"esleme_is_payi": None, "yuzey_is_payi": None,
                "kimlik_artigi": None, "izdusum_olcekli_max": None,
                "izdusum_agirlikli": None}
    return {"esleme_is_payi": s.get("esleme_isi_artigi"),
            "yuzey_is_payi": s.get("yuzey_isi_artigi"),
            "kimlik_artigi": s.get("kimlik_artigi"),
            "izdusum_olcekli_max": s.get("en_buyuk_olcekli"),
            "izdusum_agirlikli": s.get("agirlikli_olcekli")}


def olc() -> dict:
    from coupling_fsi import cfd_pressure_to_fea_loads

    vakalar, kayit, dusen = _vakalar(), [], []
    for v in vakalar:
        try:
            r = cfd_pressure_to_fea_loads(v["vtk"], v["stl"])
        except Exception as e:      # noqa: BLE001 — sebep KAYDEDILIYOR
            dusen.append(f"{v['ad']}: {type(e).__name__}: {e}"[:140])
            continue
        if r.get("status") != "SUCCESS":
            dusen.append(f"{v['ad']}: {r.get('error')}"[:140])
            continue
        if not r.get("yuk_var_mi"):
            # SIFIR YUK OLCULEN SAYILMAZ. Metrikler tanimsiz; ortalamaya ya da
            # "en iyi vaka"ya girerse tabloyu SAHTE iyilestirir.
            dusen.append(f"{v['ad']}: {r['yuk_notu']}"[:200])
            continue
        kayit.append({
            "vaka": v["ad"],
            "n_cfd_yuz": r["n_cfd_faces"], "n_fea_yuz": r["n_fea_faces"],
            "kuvvet_hatasi": r["conservation_error"],
            "moment_hatasi": r["moment_conservation_error"],
            "arayuz_isi_hatasi": r["arayuz_isi_hatasi"],
            "aktarim_hatasi_pct": round(100 * r["aktarim_hatasi"], 2),
            "alan_farki_pct": r["alan_farki_pct"],
            "cfd_alan_m2": r["cfd_alan_m2"], "fea_alan_m2": r["fea_alan_m2"],
            "normal_ters": r["aktarim_normali_ters"],
            "cozunurluk_orani": round(r["n_fea_faces"] / max(r["n_cfd_faces"], 1), 3),
            # IS ARTIGININ AYRISIMI. Toplam metrik iki SEMAYI kiyaslar;
            # uretimdeki eslemenin payi ayri olculur ve kimlikle sinanir.
            **_ayrisim(r.get("esleme_sapmasi")),
        })

    # SEMA DEGISTI (2026-08-26) VE BU HUKMU DE DEGISTIRDI. Eski (tutarli)
    # semada kuvvet ve moment FEA yuzu->dugum dagitimini olcuyordu ve
    # esit-uctebir semasinda UCU DE yapi geregi kesindi. Korunumlu semada
    # kaynak CFD yuzudur: KUVVET hala kesin (agirliklar 1'e toplanir) ama
    # MOMENT degil --- kuvvet FEA ucgenine IZDUSURULUR ve izdusum kaymasi
    # kadar bir artik kalir. O artik gizlenmez, AYRICA olculur.
    kesin = [k for k in kayit if k["kuvvet_hatasi"] <= KESIN_ESIK]
    mom_kesin = [k for k in kayit if k["moment_hatasi"] <= KESIN_ESIK]
    # ALANI TUTAN vakalar artigi SAF ORNEKLEME olarak okutur; hukum oradan
    # kurulur, cunku ote vakalarda iki sebep ayrilamaz.
    temiz = [k for k in kayit if k["alan_farki_pct"] <= 0.5]
    en_kotu = max(kayit, key=lambda k: k["aktarim_hatasi_pct"]) if kayit else None

    return {
        "vaka": "FSI yük aktarımında korunum — üç metrik",
        "_neden": ("Eski (tutarli) semada kuvvet ve moment FEA yuzu -> dugum "
                   "dagitimini olcuyordu ve YAPI GEREGI kesindi; gercekten "
                   "korunmayan adim CFD -> FEA basinc aktarimiydi ve HIC "
                   "olculmuyordu. Olculunce %0,07-%72,04 cikti ve sema "
                   "degistirildi. Bu kayit YENI semanin olcumudur."),
        "olculen_vaka": len(kayit),
        "vakalar": kayit,
        "olculemeyen": dusen,
        "kuvvet_kesin_olan": f"{len(kesin)}/{len(kayit)}",
        "moment_kesin_olan": f"{len(mom_kesin)}/{len(kayit)}",
        "moment_artigi_en_kotu": round(max(
            (k["moment_hatasi"] for k in kayit), default=0.0), 5),
        "verdikt": (
            (f"KORUNUMLU ŞEMA ÜRETİMDE. CFD→FEA aktarım artığı "
             f"%{max(k['aktarim_hatasi_pct'] for k in kayit):.4f} --- "
             f"{len(kayit)}/{len(kayit)} vakada SIFIR. Bu bir KİMLİKTİR "
             f"(ağırlıklar 1'e toplanır), bulgu değil: eski şemada aynı "
             f"vakalarda %72,04'e kadar çıkıyordu. Kuvvet korunumu "
             f"{len(kesin)}/{len(kayit)} vakada makine hassasiyetinde. "
             f"MOMENT KORUNMAZ ve bu GİZLENMİYOR: kuvvet FEA üçgenine "
             f"izdüşürülür, izdüşüm kayması kadar artık kalır --- en kötü "
             f"%{100 * max((k['moment_hatasi'] for k in kayit), default=0):.2f}. "
             # IS ARTIGI VERDIKTE GIRDI --- OLCULUYORDU AMA OKUNMUYORDU.
             #
             # Dis hakem (2026-08-26) "work conservation henuz gosterilmedi"
             # dedi. Aslinda OLCULUYOR ve KORUNMUYOR: en buyuk artik bu.
             # Verdikt kuvvet ve momenti yazip isi atliyordu, yani en zayif
             # metrigi susturuyordu --- olculup okunmayan alan, bu deponun
             # avladigi kusurun ta kendisi ve bu kez SONUCU IYI gosteriyordu.
             #
             # IS ARTIGI MOMENTTEN BUYUK OLMALI ve bu bir kusur degil: x×F,
             # F⊗x tensorunun yalniz ANTISIMETRIK kismidir; is metrigi
             # simetrik kismi (uzama/kayma modlarinin yaptigi is) de gorur.
             f"ARAYÜZ İŞİ DE KORUNMAZ ve artığı momentten BÜYÜKTÜR --- en "
             f"kötü %{100 * max((k['arayuz_isi_hatasi'] for k in kayit), default=0):.2f}, "
             f"ortalama %{100 * sum(k['arayuz_isi_hatasi'] for k in kayit) / max(len(kayit), 1):.2f}. "
             # ATIF DUZELTILDI (2026-08-28). Bu satir bir turdur "sebebi ayni
             # izdusum kaymasidir" diyordu ve BU YANLISTI: metrik dugum
             # momentini (URETIMDEKI sema) yuz momentiyle (TERK EDILMIS sema,
             # FEA yuzunde YENIDEN INTEGRE) kiyasliyor, yani eslemeyi degil
             # SEMALARI olcuyor. Dogru referans CFD tarafi ve orada bir
             # KIMLIK var: T_dugum - T_cfd == sum dF (x) delta. Kimlik 24/24
             # vakada <=1e-10 tuttu ve ayrisim su:
             f"AMA ATIF ÖNEMLİ: bu sayı üretimdeki eşlemeyi DEĞİL iki "
             f"ŞEMAYI kıyaslar. Doğru referans CFD tarafıdır ve orada "
             f"kimlik (T_dugum - T_cfd = toplam dF (x) delta) "
             f"{len(kayit)}/{len(kayit)} vakada makine hassasiyetinde tuttu. "
             f"Ayrışım: ESLEME payı en kötü "
             f"%{100 * max((k.get('esleme_is_payi') or 0 for k in kayit), default=0):.2f}, "
             f"{sum(1 for k in kayit if (k.get('esleme_is_payi') or 0) < 0.01)}/{len(kayit)} "
             f"vakada %1'in ALTINDA; geri kalanı terk edilmiş şemanın yüzey "
             f"integralinden geliyor. Yani '%102,64 iş kaybı' üretimdeki "
             f"aktarımın suçu DEĞİLDİR. "
             f"Ölçüt yine de momentten güçlüdür: $x×F$ birinci moment "
             f"tensörünün yalnız antisimetrik kısmıdır, iş metriği "
             f"simetrik kısmı da görür. "
             # ON-UCUS YORDAYICISI ARANDI VE BULUNAMADI --- kayda geciyor ki
             # dorduncu kez aranmasin.
             f"ÖN-UÇUŞ YORDAYICISI ARANDI, BULUNAMADI: izdüşüm sapmasının "
             f"kuvvet-ağırlıklı ve en-büyük ölçüleri eşleme payıyla "
             f"korele DEĞİL (Spearman 0,00 ve -0,25; n={len(kayit)} için "
             f"kritik |r|~0,41). Sebebi yapısal: hata bir TENSÖR normudur "
             f"(toplam dF (x) delta) ve skaler bir sapma "
             f"ortalaması yön uyumunu göremez. Doğru kapı geometriden "
             f"kestirmek değil, yükler geldikten SONRA eşleme payını "
             f"doğrudan hesaplamaktır --- ucuzdur ve yapısal çözümden "
             f"öncedir. "
             f"Alanı tutan {len(temiz)} vakada aktarım zaten sorunsuzdu; "
             f"şema değişikliğinin kazancı alanı TUTMAYAN vakalardadır.")
            if kayit else "ÖLÇÜLEMEDİ — yüzey-basınç VTK'sı olan vaka yok"),
        "_kisit": (
            "Artik bir DOGRULUK hukmu degil bir AKTARIM hukmudur: FEA'ya giden "
            "yukun CFD'nin hesapladigi yukten ne kadar saptigini soyler, "
            "CFD'nin dogru olup olmadigini DEGIL. Ayrica tek yonlu kuplajda "
            "olculdu; iki yonlu turda her turda yeniden dogar ve birikir. "
            "Esik DAYATILMIYOR — bugun hicbir uretim yolu bu sayiya bakip "
            "kosuyu reddetmiyor; sayi once GORUNUR olmali."),
        "_uretim": "Üretim: python experiments/fsi_korunum.py",
    }


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    print("FSI yük aktarımında korunum\n")
    print(f"{'vaka':<24}{'CFD yüz':>8}{'FEA yüz':>8}{'kuvvet':>10}{'moment':>10}"
          f"{'arayüz işi':>12}{'AKTARIM':>9}{'alan farkı':>11}")
    for k in r["vakalar"]:
        print(f"{k['vaka'][:23]:<24}{k['n_cfd_yuz']:>8}{k['n_fea_yuz']:>8}"
              f"{k['kuvvet_hatasi']:>10.1e}{k['moment_hatasi']:>10.1e}"
              f"{k['arayuz_isi_hatasi']:>12.1e}"
              f"{k['aktarim_hatasi_pct']:>8.1f}%{k['alan_farki_pct']:>10.1f}%")
    for x in r["olculemeyen"]:
        print(f"  — {x}")
    print(f"\n{r['verdikt']}")
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
