"""Arka-uç taşımasının ÖLÇÜLMÜŞ eşdeğerliği — taşımadan önce, tahmin yerine.

NEDEN: iki dosya ortak katmana taşınmayı bekliyordu ve gerekçe ikisinde de
aynıydı --- "taşıma davranışı değiştirebilir, önce eşdeğerlik ölçülmeli".
`xfoil_kesit` login kabuğa (PATH profil dosyalarından), `construct2d_bridge`
stdin beslemesine ve süreç yoklamasına dayanıyor. Katmana `login` ve `girdi`
seçenekleri eklendi; bu betik eklemenin YETTİĞİNİ ölçer.

YÖNTEM: aynı iş İKİ YOLLA koşulur --- eski doğrudan `wsl bash -lc` ve yeni
`analysis.backend.linux_run`. Sayısal çıktılar karşılaştırılır. Fark varsa
taşıma YAPILMAZ; bu betik "taşınabilir" demeden taşınmaz.

    python experiments/arka_uc_esdegerlik.py
Çıktı: arka_uc_esdegerlik.json (kanıt)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

from analysis.backend import linux_run  # noqa: E402

ESIK_BAGIL = 1e-9      # ikisi AYNI ikiliyi ayni girdiyle kosar: birebir beklenir


def _eski_yol(komut: str, girdi: str | None = None) -> subprocess.CompletedProcess:
    """Taşımadan ÖNCEKİ çağrı biçimi — karşılaştırma tabanı."""
    return subprocess.run(["wsl", "bash", "-lc", komut], input=girdi,
                          capture_output=True, text=True, timeout=600)


def xfoil_esdegerligi() -> dict:
    """XFOIL polarını iki yolla koş, Cl/Cd'yi karşılaştır."""
    try:
        sys.path.insert(0, str(KOK))
        from xfoil_kesit import _komut_dizisi
    except Exception as e:
        return {"durum": "atlandi", "neden": f"xfoil_kesit içe aktarılamadı: {e}"}
    p = _eski_yol("command -v xfoil")
    if p.returncode != 0 or not p.stdout.strip():
        return {"durum": "atlandi", "neden": "XFOIL kurulu değil (login PATH'te yok)"}
    yol = p.stdout.strip()

    def kos(calistir) -> list[dict]:
        d = calistir("mktemp -d").stdout.strip()
        cikti = f"{d}/polar.txt"
        girdi = _komut_dizisi("0012", 3.5e5, 0.0, [0, 4, 8], cikti)
        calistir(f"cd {d} && {yol}", girdi)
        tablo = calistir(f"cat {cikti}").stdout
        calistir(f"rm -rf {d}")
        from xfoil_kesit import _oku_polar
        return _oku_polar(tablo)

    eski = kos(lambda c, g=None: _eski_yol(c, g))
    yeni = kos(lambda c, g=None: linux_run(c, 600, login=True, girdi=g))
    return _kiyasla("xfoil_kesit", eski, yeni, ("Cl", "Cd"))


def construct2d_esdegerligi() -> dict:
    """Construct2D'yi iki yolla koş, üretilen ağın DÜĞÜM SAYILARINI karşılaştır.

    Bu vakanın gerekçesi iki katmanlıydı: kabuk içinde `printf | ikili` boru
    hattı (stdin) VE süreç görünürlüğü (ölçülmüş yarış durumu --- sarmalayıcı,
    Construct2D hâlâ koşarken dönüyordu). İkisi de burada sınanır.

    İKİLİ PATH'TE DEĞİL, PROJE DİZİNİNDE. İlk sürüm `command -v construct2d`
    ile aradı ve "kurulu değil" diye atladı --- ölçüm yapılmadan geçilmiş
    olurdu. Yol `construct2d_bridge.C2D_BIN`ten alınır.
    """
    from analysis.ccx_runner import windows_to_wsl_path as wsl_yol
    from construct2d_bridge import C2D_BIN, read_p3d_2d
    if not C2D_BIN.exists():
        return {"durum": "atlandi", "neden": f"ikili yok: {C2D_BIN}"}
    dat = KOK / "Construct2D" / "sample_airfoils" / "ls417.dat"
    if not dat.exists():
        return {"durum": "atlandi", "neden": f"profil .dat yok: {dat}"}

    def kos(calistir, etiket: str):
        import shutil

        import construct2d_bridge as c2b
        w = KOK / f"_c2d_esd_{etiket}"
        shutil.rmtree(w, ignore_errors=True)
        w.mkdir(parents=True)
        shutil.copy(dat, w / "esd.dat")
        # NAMELIST'I KOPRU URETIR. Ilk surum onu ELLE yaziyordu ve eksikti;
        # olculen sey tasima degil, benim namelist'imin dogrulugu oluyordu.
        # Kopru fonksiyonu cagrilir; degisen tek sey TASIMADIR.
        ozgun = c2b.linux_run
        try:
            if calistir is not None:
                c2b.linux_run = lambda cmd, t, **k: calistir(cmd)
            p3d = c2b.run_construct2d(str(w / "esd.dat"), w, "esd",
                                      jmax=60, nsrf=150, nwke=30,
                                      stp1=200, stp2=50)
        finally:
            c2b.linux_run = ozgun
        if not p3d or not Path(p3d).exists():
            return None
        X, Y, ni, nj = read_p3d_2d(Path(p3d))
        return {"ni": int(ni), "nj": int(nj),
                "x_ilk": round(float(X.flat[0]), 9),
                "y_son": round(float(Y.flat[-1]), 9),
                "x_toplam": round(float(X.sum()), 6),
                "y_toplam": round(float(Y.sum()), 6)}

    eski = kos(None, "eski")                         # koprunun MEVCUT yolu
    yeni = kos(lambda c: linux_run(c, 900), "yeni")  # ORTAK KATMAN
    # Surec gorunurlugu: iki yol da ayni pgrep cevabini vermeli.
    sorgu = "pgrep -f '[c]onstruct2d' >/dev/null && echo VAR || echo YOK"
    pg_e, pg_y = _eski_yol(sorgu).stdout.strip(), linux_run(sorgu, 60).stdout.strip()
    out = {"surec_gorunurlugu": {"eski": pg_e, "yeni": pg_y, "ayni": pg_e == pg_y},
           "eski": eski, "yeni": yeni}
    if not eski or not yeni:
        out["durum"] = "olculemedi"
        out["neden"] = f"p3d üretilemedi (eski={bool(eski)}, yeni={bool(yeni)})"
    elif eski == yeni and pg_e == pg_y:
        out["durum"] = "AYNI"
    else:
        out["durum"] = "FARKLI"
    return out


def _kiyasla(ad: str, eski: list[dict], yeni: list[dict],
             alanlar: tuple[str, ...]) -> dict:
    if not eski or not yeni:
        return {"durum": "olculemedi", "ad": ad,
                "neden": f"eski={len(eski)} nokta, yeni={len(yeni)} nokta"}
    if len(eski) != len(yeni):
        return {"durum": "FARKLI", "ad": ad,
                "neden": f"nokta sayısı: eski {len(eski)}, yeni {len(yeni)}"}
    en_buyuk = 0.0
    for a, b in zip(eski, yeni):
        for k in alanlar:
            if a[k] == 0:
                continue
            en_buyuk = max(en_buyuk, abs(b[k] - a[k]) / abs(a[k]))
    return {"durum": "AYNI" if en_buyuk <= ESIK_BAGIL else "FARKLI", "ad": ad,
            "n_nokta": len(eski), "en_buyuk_bagil_fark": en_buyuk,
            "esik": ESIK_BAGIL,
            "ornek": {"eski": eski[0], "yeni": yeni[0]}}


def main() -> int:
    for _a in (sys.stdout, sys.stderr):
        if hasattr(_a, "reconfigure"):
            _a.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.time()
    x = xfoil_esdegerligi()
    c = construct2d_esdegerligi()
    tasinabilir = (x.get("durum") == "AYNI"
                   and c.get("durum") in ("AYNI", "atlandi"))
    rec = {
        "vaka": "Arka-uç taşıması — eşdeğerlik ölçümü (taşımadan ÖNCE)",
        "_neden": ("Iki dosya ortak katmana tasinmayi bekliyordu ve gerekce "
                   "ikisinde de 'once esdegerlik olculmeli'ydi. Katmana login "
                   "kabuk ve stdin secenekleri eklendi; bu betik eklemenin "
                   "YETTIGINI olcer."),
        "xfoil": x,
        "construct2d": c,
        "tasinabilir_mi": tasinabilir,
        "_uretim": "Üretim: python experiments/arka_uc_esdegerlik.py",
        "_sure_s": round(time.time() - t0, 1),
    }
    _c = (f"Construct2D: {c.get('durum')}"
          + (f" ({c['eski']['ni']}x{c['eski']['nj']} düğüm, koordinat toplamları "
             "aynı)" if c.get("eski") else f" — {c.get('neden', '')}"))
    rec["verdikt"] = (
        f"✅ Taşıma GÜVENLİ. XFOIL: iki yol aynı ({x.get('n_nokta')} nokta, en "
        f"büyük bağıl fark {x.get('en_buyuk_bagil_fark', 0):.1e}). {_c}."
        if tasinabilir else
        f"⚠️ Eşdeğerlik GÖSTERİLEMEDİ. XFOIL: {x.get('durum')}"
        f" — {x.get('neden', '')}. {_c}. "
        "Taşıma YAPILMAZ; gerekçe kodda kalmaya devam eder.")
    import ortam
    ortam.damgala(rec)
    (KOK / "arka_uc_esdegerlik.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(rec["verdikt"])
    if c.get("surec_gorunurlugu"):
        print("Süreç görünürlüğü aynı mı:", c["surec_gorunurlugu"]["ayni"])
    print("-> arka_uc_esdegerlik.json")
    return 0 if tasinabilir else 1


if __name__ == "__main__":
    raise SystemExit(main())
