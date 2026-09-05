"""FSI aktarım sağlığı — kanıttan okunan kart satırları.

Yol haritası V1.1/3. Ölçüm 2026-08-28'de bitti, eksik olan onu OKUYAN katmandı
ve maddenin kendi cümlesi şunu söylüyordu: *"Kart ayrışımı göstermeli, yoksa
okur yine toplamı üretime yazar."*

Neden bu ayrım kartın var oluş sebebi:

    _fsi_esnek       toplam %102,64   ESLEME %24,10
    gripen_AB_Right  toplam  %76,72   ESLEME  %0,0023

Toplama bakan bir okur gripen'i reddederdi; oysa oradaki eşlemenin hatası on
binde iki, kalanı **terk edilmiş** şemanın FEA yüzünde yeniden integre
etmesinden geliyor ve üretim yolunda hiç yok. `_fsi_esnek` ise gerçekten reddi
hak ediyor. Yani ekranda tek bir sayı göstermek, iki zıt vakayı aynı gösterir.

**Bu modül sayı ÜRETMEZ.** Payları `fsi_korunum.json`'dan okur ve hükmü
`fsi_aktarim_kapisi.aktarim_hukmu`'na sorar --- `turek_hron_kiyaslama`'daki
kuralın aynısı: yönetici YOL bilir, DEĞER bilmez. Kart burada bir yüzde
hesaplasaydı, kapının hükmüyle ekrandaki sayı sessizce ayrışabilirdi.

    python fsi_aktarim_karti.py        # konsolda tablo
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
KANIT = KOK / "fsi_korunum.json"

# Tablo Türkçe karakter ve '%' taşıyor; Windows konsolu cp1254'te
# UnicodeEncodeError atıp çıktıyı İLK SATIRDA keser --- `sessiz_yutma` ve
# `naca2412_kesit` aynı kusuru yaşamıştı ve `test_konsol_kodlamasi` bunu
# kapıya bağlamış: bu satırlar olmadan kart konsolda ölür.
for _akis in (sys.stdout, sys.stderr):
    if hasattr(_akis, "reconfigure"):
        _akis.reconfigure(encoding="utf-8", errors="replace")

# Ayrışımın kendisi bir KİMLİĞE dayanır:
#     T_düğüm - T_CFD == Σ_f dF_f ⊗ δ_f
# Kanıtta 24/24 vakada <=1e-10 tuttu. Bu eşiği aşan bir satırda ayrışım
# GÜVENİLİR DEĞİLDİR ve kart payları hüküm gibi sunmaz.
KIMLIK_ESIGI = 1e-10


def _pct(x):
    """Oranı yüzdeye çevir; YOKLUK ile SIFIR ayrı kalsın.

    `0.0` korunumlu şemada geçerli ve sık bir ölçümdür. Doğruluk sınamasıyla
    yazılsaydı sıfır sessizce 'ölçülmedi'ye dönerdi --- `fsi_surucu._yuzde`
    aynı sebeple aynı şekilde yazılı.
    """
    return None if x is None else 100.0 * float(x)


def satirlar(kanit: Path | None = None) -> list[dict]:
    """Her vaka için kartın gösterdiği alanlar, en kötü hâkim artık başta."""
    yol = Path(kanit) if kanit else KANIT
    if not yol.exists():
        return []
    veri = json.loads(yol.read_text(encoding="utf-8"))

    from fsi_aktarim_kapisi import aktarim_hukmu

    out = []
    for v in veri.get("vakalar", []):
        esleme = _pct(v.get("esleme_is_payi"))
        toplam = _pct(v.get("arayuz_isi_hatasi"))
        kimlik = v.get("kimlik_artigi")
        ayrisim_var = esleme is not None
        # Kimlik tutmuyorsa pay bir sayıdır ama DAYANAĞI yoktur; kapıya
        # götürmek onu hükme çevirir, o yüzden toplama düşülür ve sebebi
        # satıra yazılır.
        kimlik_saglam = kimlik is None or abs(float(kimlik)) <= KIMLIK_ESIGI
        hukum = aktarim_hukmu(
            _pct(v.get("kuvvet_hatasi")),
            v.get("alan_farki_pct"),
            moment_artigi_pct=_pct(v.get("moment_hatasi")),
            is_artigi_pct=toplam,
            esleme_is_payi_pct=esleme if (ayrisim_var and kimlik_saglam) else None,
        )
        out.append({
            "vaka": v.get("vaka"),
            "ayrisim_var": ayrisim_var and kimlik_saglam,
            "esleme_pay_pct": esleme if kimlik_saglam else None,
            "yuzey_pay_pct": _pct(v.get("yuzey_is_payi")) if kimlik_saglam else None,
            "toplam_pct": toplam,
            "kuvvet_pct": _pct(v.get("kuvvet_hatasi")),
            "moment_pct": _pct(v.get("moment_hatasi")),
            "alan_farki_pct": v.get("alan_farki_pct"),
            "kimlik_artigi": kimlik,
            "kimlik_saglam": kimlik_saglam,
            "normal_ters": v.get("normal_ters"),
            "hukum": hukum,
            "hakim_metrik": hukum.get("hakim_metrik"),
            "hakim_pct": hukum.get("aktarim_pct"),
            "kullanilabilir": hukum.get("kullanilabilir"),
            "kod": hukum.get("kod"),
        })
    out.sort(key=lambda r: (-1.0 if r["hakim_pct"] is None else -float(r["hakim_pct"])))
    return out


def ozet(sat: list[dict] | None = None) -> dict:
    """Kartın başlığı: kaç vakada ayrışım var, kaçı reddedildi."""
    s = satirlar() if sat is None else sat
    return {
        "vaka": len(s),
        "ayrisimi_olan": sum(1 for r in s if r["ayrisim_var"]),
        "ayrisimi_olmayan": sum(1 for r in s if not r["ayrisim_var"]),
        "reddedilen": sum(1 for r in s if r["kullanilabilir"] is False),
        "hukum_verilemeyen": sum(1 for r in s if r["kullanilabilir"] is None),
    }


def _bicim(x, basamak: int = 2) -> str:
    return "—" if x is None else f"%{float(x):.{basamak}f}"


def main() -> int:
    s = satirlar()
    if not s:
        print(f"kanıt yok: {KANIT} (python experiments/fsi_korunum.py)")
        return 1
    o = ozet(s)
    print(f"FSI aktarım sağlığı — {o['vaka']} vaka, "
          f"{o['ayrisimi_olan']}'inde ayrışım var, "
          f"{o['reddedilen']}'i reddedildi")
    print(f"{'vaka':<26}{'hâkim':<14}{'artık':>10}{'eşleme':>10}"
          f"{'yüzey':>10}{'toplam':>10}  hüküm")
    for r in s:
        h = {True: "KULLANILIR", False: "REDDEDİLDİ", None: "HÜKÜM YOK"}[r["kullanilabilir"]]
        ek = "" if r["ayrisim_var"] else "  (AYRIŞIM YOK — toplam kullanıldı)"
        print(f"{str(r['vaka'])[:25]:<26}{str(r['hakim_metrik']):<14}"
              f"{_bicim(r['hakim_pct']):>10}{_bicim(r['esleme_pay_pct']):>10}"
              f"{_bicim(r['yuzey_pay_pct']):>10}{_bicim(r['toplam_pct']):>10}"
              f"  {h}{ek}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
