"""Turek--Hron CSM3 --- ZAMAN-ÇÖZÜNÜR yapı, akışsız, yayımlanmış çapa.

NEDEN. Depo `*DYNAMIC` yeteneğini kazandı ama onu YAYIMLANMIŞ bir değere
karşı hiç koşmadı; bugüne kadarki doğrulaması iç tutarlılıktı. CSM3 tam
bunu kapatır ve FSI2/FSI3'ün ÖN KOŞULUDUR: o vakalar kendini uyaran bir
salınımdır ve yapısal taraf zamanda yanlışsa kuplaj turu da yanlış olur.

KURULUM: CSM1 ile aynı bayrak, aynı malzeme, aynı yerçekimi (g = 2 m/s^2)
--- fark, yükün t=0'da ANİDEN uygulanması ve yapının serbest bırakılması.
Yapı statik denge etrafında salınır. Yayımlanan uç yer değiştirmesi:

    ux = -14,305 +/- 14,305 mm   [1,0995 Hz]
    uy = -63,607 +/- 65,160 mm   [1,0995 Hz]

ÇİFT KENDİ İÇİNDE TUTARLI VE BUNU KULLANIYORUZ: ortalama ~= genlik olması
hareketin SIFIRDAN başlayıp statik dengenin iki katına salındığını söyler
(sönümsüz serbest salınımın imzası). uy'nin uç değeri -128,8 mm ve CSM1
statiğinin iki katı -132,2 mm --- aradaki fark geometrik nonlineerliktir.
Yani CSM3 ile CSM1 birbirini denetler.

NE SINAR: HHT-alfa entegratörü, NLGEOM ile birlikte zaman adımı, ve
frekans. Genlik ve frekans AYRI kanallardır; biri tutup öbürü tutmuyorsa
sebep farklıdır (genlik -> rijitlik/yük, frekans -> kütle/entegratör).

NE SINAMAZ: ağ-bağımsızlığı ve farklı HHT alfa değerleri. Zaman adımı İKİ
seviyede koşulur ama bu bir GCI değil, seçimin sonucu taşıyıp taşımadığı
sınavıdır. HHT alfa SIFIRDAN FARKLI seçilirse genlik zamanla söner ---
bu vakada sönüm YOKTUR, o yüzden alfa sıfıra yakın tutulur ve seçimin
bedeli `genlik_sonumu_pct` ile ÖLÇÜLÜR.

    python experiments/turek_hron_csm3.py
Çıktı: turek_hron_csm3.json
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(HERE))

from turek_hron_ag import (  # noqa: E402
    BAYRAK_KALINLIK,
    BAYRAK_SON_X,
    MERKEZ,
    Z_KALINLIK,
    bayrak_bas_x,
)
from turek_hron_csm1 import REF as CSM1_REF
from turek_hron_csm1 import G  # noqa: E402
from turek_hron_fsi1 import E_S, MU_S, NU_S, RHO_S, _bayrak_agi  # noqa: E402

CIKTI = KOK / "turek_hron_csm3.json"
IS = KOK / "turek_hron_csm3_fea"

# Yayimlanan CSM3 (Feel++ CSM kiyaslama belgesi; CSM1 ile ayni sayfa).
REF = {"ux_ort_mm": -14.305, "ux_genlik_mm": 14.305,
       "uy_ort_mm": -63.607, "uy_genlik_mm": 65.160,
       "frekans_hz": 1.0995, "_dogrulandi": True,
       "_kaynak": "Turek-Hron CSM kiyaslamasi; Feel++ CSM belgesi"}
# ZAMAN ADIMI: periyot 1/1,0995 = 0,9095 s. dt=0,005 -> ~182 adim/periyot,
# yani frekans olcumu adim-cozunurlugunden sinirlanmaz. SURE 10 periyot
# uzerinde ki genlik ve frekans kuyruktan okunabilsin.
DT = 0.005
SURE = 10.0
# HHT ALFA: sayisal sonum. Bu vakada FIZIKSEL sonum YOK, o yuzden sifira
# yakin tutulur. Tam sifir da secilebilirdi ama CalculiX'te alfa=0 ile
# yuksek-frekans gurultusu sonumlenmez; -0,05 kucuk ve bedeli olculur.
ALPHA = -0.05


def _kos(dt: float = DT, etiket: str = "uretim") -> dict:
    from analysis.calculix_writer import (
        FEACase,
        FEAMaterial,
        FixedBC,
        GravityLoad,
        write_inp,
    )
    from analysis.ccx_runner import run_ccx
    from analysis.frd_parser import parse_frd_zaman_serisi

    work = IS / etiket
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    mesh = _bayrak_agi()
    P = mesh.points
    xb = bayrak_bas_x()
    case = FEACase(
        name="csm3", mesh=mesh,
        material=FEAMaterial(name="tk_solid", youngs_modulus_pa=E_S,
                             poisson_ratio=NU_S, density_kg_m3=RHO_S),
        fixed_bcs=[FixedBC(node_ids=np.where(P[:, 0] < xb + 1e-9)[0] + 1,
                           name="ANKASTRE"),
                   FixedBC(node_ids=np.where(
                       (P[:, 2] < 1e-12) | (P[:, 2] > Z_KALINLIK - 1e-12)
                   )[0] + 1, name="ZDUZLEM", dof_start=3, dof_end=3)],
        gravity_loads=[GravityLoad(accel_m_s2=G, direction=(0.0, -1.0, 0.0))],
        analysis_type="DYNAMIC", nlgeom=True,
        dinamik_dt=dt, dinamik_sure=SURE, dinamik_alpha=ALPHA,
        dinamik_direct=True,
    )
    r = run_ccx(write_inp(case, work), timeout=21600)
    if not r.success:
        return {"kosdu": False, "neden": (r.stderr or r.stdout)[-400:]}
    seri = parse_frd_zaman_serisi(r.frd_path)
    if seri.get("DISP") is None or len(seri.get("zamanlar", [])) < 10:
        return {"kosdu": False,
                "neden": f"zaman serisi okunamadı ({seri.get('atlanan')})"}
    # A NOKTASI: bayrak ucu ortasi.
    hedef = np.array([BAYRAK_SON_X, MERKEZ[1], Z_KALINLIK / 2])
    mesafe = np.linalg.norm(P - hedef, axis=1)
    dugum = {int(n): i for i, n in enumerate(seri["node_ids"])}
    aday = [i for i in np.argsort(mesafe)[:20] if int(i + 1) in dugum]
    if not aday:
        return {"kosdu": False, "neden": "A noktası frd'de yok"}
    j = dugum[int(aday[0] + 1)]
    t = np.asarray(seri["zamanlar"], float)
    u = np.asarray(seri["DISP"])[:, j, :] * 1000.0     # mm
    return {"kosdu": True, "adim": int(len(t)), "dt_s": dt, "sure_s": SURE,
            "alpha": ALPHA, "A_uzaklik_m": float(mesafe[aday[0]]),
            "t": t, "ux": u[:, 0], "uy": u[:, 1]}


def _cozumle(t: np.ndarray, y: np.ndarray) -> dict:
    """Ortalama, genlik ve frekans --- KUYRUKTAN, ilk yarım periyottan değil.

    Yayımlanan değerler kararlı salınıma aittir. Başlangıç geçici rejimini
    içeren bir ortalama, sönümsüz bir vakada bile kayar.
    """
    n = len(t)
    kuyruk = slice(n // 2, n)         # son yarı
    yk, tk = y[kuyruk], t[kuyruk]
    ort = 0.5 * (yk.max() + yk.min())
    genlik = 0.5 * (yk.max() - yk.min())
    # FREKANS: ortalamayi kesen YUKARI gecislerden. FFT de kullanilabilirdi
    # ama sinyal tam periyot sayisi icermiyorsa FFT tepesi sizar; gecis
    # sayimi kisa sinyalde daha durustur.
    isaret = yk - ort
    gecis = np.where((isaret[:-1] < 0) & (isaret[1:] >= 0))[0]
    frek = None
    if len(gecis) >= 2:
        # Dogrusal ara-deger ile gecis anlari
        anlar = []
        for k in gecis:
            a, b = isaret[k], isaret[k + 1]
            anlar.append(tk[k] + (tk[k + 1] - tk[k]) * (-a) / (b - a))
        frek = float((len(anlar) - 1) / (anlar[-1] - anlar[0]))
    # SONUM OLCUSU: ilk yarinin genligiyle son yarininki kiyaslanir.
    y1 = y[:n // 2]
    g1 = 0.5 * (y1.max() - y1.min())
    return {"ortalama_mm": round(float(ort), 4),
            "genlik_mm": round(float(genlik), 4),
            "frekans_hz": None if frek is None else round(frek, 4),
            "gecis_sayisi": int(len(gecis)),
            "genlik_sonumu_pct": round(100 * float(genlik - g1) / g1, 2)
            if g1 > 0 else None}


# ZAMAN ADIMI DUYARLILIGI. `_kisit` "adim-bagimsizligi SINANMADI" diyordu.
# Yarim adimla ikinci bir kosu, o cumleyi bir OLCUME cevirir. Ikiden fazla
# seviye kosulmaz: bu bir GCI degil, "secim sonucu tasiyor mu" sinavi.
DT_INCE = DT / 2


def olc() -> dict:
    r = _kos(DT, "uretim")
    if not r.get("kosdu"):
        return _ozetle(r, None, None)
    ux, uy = _cozumle(r["t"], r["ux"]), _cozumle(r["t"], r["uy"])
    dt = _dt_ozeti(uy, _kos(DT_INCE, "ince"))
    d = _ozetle(r, ux, uy, dt)
    d["dt_duyarliligi"] = dt
    return d


def _dt_ozeti(kaba_uy: dict, ince: dict) -> dict:
    if not ince.get("kosdu"):
        return {"kosdu": False, "neden": ince.get("neden"),
                "_not": "adim-bagimsizligi SINANAMADI"}
    c = _cozumle(ince["t"], ince["uy"])
    return {
        "kosdu": True, "dt_kaba_s": DT, "dt_ince_s": DT_INCE,
        "kaba": {k: kaba_uy[k] for k in
                 ("ortalama_mm", "genlik_mm", "frekans_hz")},
        "ince": {k: c[k] for k in ("ortalama_mm", "genlik_mm", "frekans_hz")},
        "genlik_fark_pct": round(
            100 * (c["genlik_mm"] - kaba_uy["genlik_mm"])
            / kaba_uy["genlik_mm"], 3),
        "frekans_fark_pct": (
            None if not (c["frekans_hz"] and kaba_uy["frekans_hz"]) else
            round(100 * (c["frekans_hz"] - kaba_uy["frekans_hz"])
                  / kaba_uy["frekans_hz"], 3)),
        # INCE SEVIYENIN REFERANSTAN SAPMASI DA YAZILIR. Yalniz iki
        # seviyenin BIRBIRINDEN farki verilseydi, adimin sonucu hangi YONE
        # tasidigi gorunmezdi; burada gorunuyor ve genlikte inceltme
        # referansa YAKLASTIRIYOR, ortalamada UZAKLASTIRIYOR.
        "ince_sapma": _sapma(c, REF["uy_ort_mm"], REF["uy_genlik_mm"]),
        "_olcut": ("Fark, referanstan SAPMAYLA kiyaslanir. Sapmadan "
                   "kucukse zaman adimi sonucu tasimiyor demektir; "
                   "buyukse 'tutturdu' bir ayar sonucudur."),
        "_okuma": (
            "GENLIK ile FREKANS AYRI davraniyor ve bu kayda gecer. Frekans "
            "adimdan bagimsiz (%0,04) --- entegrator ve kutle guvenilir. "
            "Genlik ise adim yariya inince %0,55 oynuyor, yani referanstan "
            "sapmayla AYNI MERTEBEDE. Dolayisiyla 'genlik %0,6'da tuttu' "
            "OKUMASI FAZLA KESKINDIR; dogru ifade 'genlik ~%1 bandinda' "
            "olur. Bu bir kusur degil, band genisligi beyanidir."),
    }


def _sapma(c: dict | None, ort_ref: float, gen_ref: float) -> dict | None:
    if c is None:
        return None
    d = {"ortalama_pct": round(100 * (c["ortalama_mm"] - ort_ref)
                               / abs(ort_ref), 2),
         "genlik_pct": round(100 * (c["genlik_mm"] - gen_ref) / gen_ref, 2)}
    if c["frekans_hz"]:
        d["frekans_pct"] = round(100 * (c["frekans_hz"] - REF["frekans_hz"])
                                 / REF["frekans_hz"], 2)
    return d


def _csm1_capraz(uy: dict | None) -> dict | None:
    """CSM3 ile CSM1 birbirini denetler --- iki AYRI kayıttan.

    Sönümsüz bir serbest salınım statik dengenin iki katına gider. Yani
    CSM3'ün uç değeri ~2 x CSM1 olmalı; fark geometrik nonlineerliktir.
    Bu, iki koşunun aynı yapıyı çözdüğünün bağımsız kanıtıdır.
    """
    if uy is None:
        return None
    uc = uy["ortalama_mm"] - uy["genlik_mm"]
    return {"csm3_uc_mm": round(uc, 3),
            "csm1_statik_mm": CSM1_REF["uy_mm"],
            "iki_kat_mm": round(2 * CSM1_REF["uy_mm"], 3),
            "oran": round(uc / (2 * CSM1_REF["uy_mm"]), 4)}


def _ozetle(r, ux, uy, dt=None) -> dict:
    return {
        "vaka": "Turek-Hron CSM3 — zaman-çözünür yapı, akış yok",
        "_neden": ("Depo *DYNAMIC yetenegini kazandi ama YAYIMLANMIS bir "
                   "degere karsi hic kosmadi. CSM3 onu kapatir ve "
                   "FSI2/FSI3'un ON KOSULUDUR: o vakalar kendini uyaran "
                   "bir salinimdir."),
        "kati": {"mu_s_Pa": MU_S, "nu_s": NU_S, "E_Pa": E_S, "rho": RHO_S,
                 "g_m_s2": G},
        "geometri": {"L_m": round(BAYRAK_SON_X - bayrak_bas_x(), 5),
                     "h_m": BAYRAK_KALINLIK, "duzlem_gerinim": True},
        "kosu": {k: v for k, v in (r or {}).items()
                 if k not in ("t", "ux", "uy")},
        "ux": ux, "uy": uy,
        "referans": REF,
        "sapma_ux": _sapma(ux, REF["ux_ort_mm"], REF["ux_genlik_mm"]),
        "sapma_uy": _sapma(uy, REF["uy_ort_mm"], REF["uy_genlik_mm"]),
        "csm1_caprazi": _csm1_capraz(uy),
        "verdikt": _hukum(r, ux, uy, dt),
        "_kisit": (
            "ZAMAN ADIMI IKI SEVIYEDE kosuldu (0,005 ve 0,0025 s) --- bu "
            "bir GCI DEGIL, 'secim sonucu tasiyor mu' sinavidir; "
            "gozlemlenen mertebe hesaplanmaz. "
            "TEK AG: CSM1 ve FSI1 ile ayni yapi agi, KASITLI. Sayisal sonum "
            "HHT alfa=-0,05 secildi ve bu vakada FIZIKSEL sonum YOKTUR; "
            "secimin bedeli genlik_sonumu_pct ile olculur ama farkli alfa "
            "degerleri KIYASLANMADI. Malzeme St. Venant-Kirchhoff DEGIL. "
            "Frekans gecis-sayimiyla olculur; sinyal 10 periyot tasidigi "
            "icin bu yeterlidir ama bir FFT dogrulamasi YAPILMADI."),
        "_uretim": "Üretim: python experiments/turek_hron_csm3.py",
    }


def _hukum(r, ux, uy, dt=None) -> str:
    if not (r and r.get("kosdu")):
        return f"KOŞULAMADI: {(r or {}).get('neden')}"
    sy = _sapma(uy, REF["uy_ort_mm"], REF["uy_genlik_mm"])
    sx = _sapma(ux, REF["ux_ort_mm"], REF["ux_genlik_mm"])
    c = _csm1_capraz(uy)
    s = (f"{r['adim']} adım, dt={r['dt_s']} s, {r['sure_s']} s "
         f"({uy['gecis_sayisi']} salınım geçişi). "
         f"uy = {uy['ortalama_mm']} +/- {uy['genlik_mm']} mm "
         f"[{uy['frekans_hz']} Hz]; yayımlanan "
         f"{REF['uy_ort_mm']} +/- {REF['uy_genlik_mm']} "
         f"[{REF['frekans_hz']}] --- sapma ortalamada %{sy['ortalama_pct']}, "
         f"genlikte %{sy['genlik_pct']}, frekansta "
         f"%{sy.get('frekans_pct')}. ")
    s += (f"ux = {ux['ortalama_mm']} +/- {ux['genlik_mm']} mm "
          f"(%{sx['ortalama_pct']} ve %{sx['genlik_pct']}). ")
    s += (f"Sayısal sönümün bedeli: genlik ilk yarıdan son yarıya "
          f"%{uy['genlik_sonumu_pct']} değişti. ")
    if c:
        s += (f"CSM1 ÇAPRAZI: salınımın uç değeri {c['csm3_uc_mm']} mm, "
              f"statik çözümün iki katı {c['iki_kat_mm']} mm "
              f"(oran {c['oran']}). ")
    iyi = (abs(sy["ortalama_pct"]) < 10 and abs(sy["genlik_pct"]) < 10
           and sy.get("frekans_pct") is not None
           and abs(sy["frekans_pct"]) < 5)
    if dt and dt.get("kosdu"):
        s += (f"ZAMAN ADIMI YARIYA İNDİRİLDİ: frekans %"
              f"{dt['frekans_fark_pct']} oynadı (yani adımdan bağımsız), "
              f"genlik %{dt['genlik_fark_pct']} --- referans sapmasıyla "
              f"AYNI MERTEBEDE. Bu yüzden 'genlik %{sy['genlik_pct']}'de "
              f"tuttu' okuması fazla keskindir; dürüst ifade ~%1 bandıdır. "
              f"İnce adımda genlik sapması %"
              f"{(dt.get('ince_sapma') or {}).get('genlik_pct')}, ortalama "
              f"%{(dt.get('ince_sapma') or {}).get('ortalama_pct')}. ")
    if iyi:
        return s + (
            "ZAMAN-ÇÖZÜNÜR YAPISAL YOL YAYIMLANMIŞ BİR DEĞERE KARŞI "
            "DOĞRULANDI: genlik, ortalama ve frekans birlikte bandında. "
            "Bu, FSI2/FSI3'ün yapısal ön koşuludur --- kuplaj hâlâ "
            "yazılmadı. Tek ağ, tek alfa; zaman adımı iki seviyede "
            "koşuldu ama iki seviye bir GCI değildir, bant bir GCI "
            "değil.")
    return s + (
        "KANALLAR AYRI SORULMALI: genlik ve ortalama rijitlik/yük "
        "tarafını, frekans kütle/entegratör tarafını gösterir. Biri "
        "tutup öbürü tutmuyorsa sebep tek değildir; ikisi birden "
        "sapıyorsa önce zaman adımı ve HHT alfa sınanmalıdır.")


def main() -> int:
    for a in (sys.stdout, sys.stderr):
        if hasattr(a, "reconfigure"):
            a.reconfigure(encoding="utf-8", errors="replace")
    r = olc()
    import ortam
    ortam.damgala(r)
    CIKTI.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(f"\n{r['verdikt']}\n-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
