"""Aralıklılık sondasını bekle, GEÇERSE tam koşuyu başlat — kararı ölçüm versin.

NEDEN BİR ZİNCİR: #5'in sınavında üç açıklama arka arkaya düştü (serbest-akış
şiddeti, `nut` duvar işlemi, ağ). Dördüncü denemeye girerken tam koşu ~16 saat
(ölçülen 13,0 s/adım × 4400 adım). Sondanın işi o 16 saati HARCAMADAN tek
soruyu yanıtlamak: geçiş modeli devreye giriyor mu?

KARAR KODDA, YORUMDA DEĞİL. Sonda bittiğinde kimse başında olmayabilir; hüküm
o anda bir insanın "galiba yeterli" demesine değil, `gammaInt`in ölçülen
minimumuna bağlı olmalı. Sonda geçmezse tam koşu BAŞLAMAZ ve sebebi kayda
geçer.

YENİDEN ÇALIŞTIRILABİLİR: her adımda diskteki duruma bakar. Zincir kesilirse
(oturum kapanır, makine uyur) aynı komut kaldığı yerden devam eder --- yarım
kalmış bir koşuyu baştan başlatmaz, bitmiş bir koşuyu tekrarlamaz.

    python experiments/gecis_zinciri.py
Çıktı: gecis_zinciri_karar.json
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
sys.path.insert(0, str(HERE))

SONDA_KANIT = KOK / "silindir_gecis_3b_dr_des_sonda3.json"
SONDA_VAKA = KOK / "_silindir_gecis_3b_dr_des_sonda3"
TAM_KANIT = KOK / "silindir_gecis_3b_dr_des.json"
TAM_VAKA = KOK / "_silindir_gecis_3b_dr_des"
KARAR = KOK / "gecis_zinciri_karar.json"

BEKLEME_S = 300          # sonda ~1,5 saat; 5 dk'da bir bakmak yeterli
AZAMI_BEKLEME_S = 6 * 3600
# BELLEK KAPISI: 2,43 M hucrelik vaka 4 cekirdekte RAM'i %92'ye cikariyor
# (olculdu). Sonda henuz belleği birakmadiysa tam kosuyu baslatmak ikisini
# de riske atar. Bu makinede toplam 13,7 GB var.
BELLEK_TAVANI_PCT = 75.0


def _bellek_pct() -> float:
    import psutil
    return psutil.virtual_memory().percent


def sonda_hukmu() -> dict | None:
    """Sonda bitti mi ve geçti mi? — kanıt dosyasından, yorumdan değil."""
    if not SONDA_KANIT.exists():
        return None
    d = json.loads(SONDA_KANIT.read_text(encoding="utf-8"))
    a = d.get("aralik_denetimi") or {}
    return {"gecti": bool(a.get("devreye_girdi")),
            "min": a.get("min"),
            "laminer_pct": a.get("laminer_hucre_orani_pct"),
            "verdikt": d.get("verdikt", "")[:400]}


_HUKUM = {
    "sonda_zaman_asimi": "SONDA BİTMEDİ (zaman aşımı) — tam koşu BAŞLATILMADI. "
                         "Karar verilemedi; yokluk 'geçti' sayılmaz.",
    "sonda_gecmedi_tam_kosu_YOK": "SONDA GEÇMEDİ — duvar-çözünür ağ da tek "
                                  "başına yetmedi. 16,9 saatlik koşuya girmek "
                                  "için sebep YOK ve girilmedi.",
    "bellek_dolu": "SONDA GEÇTİ ama BELLEK BOŞALMADI — tam koşu BAŞLATILMADI. "
                   "Koşuyu belleği yetmeyen bir makinede başlatmak, ikisini de "
                   "riske atmaktır.",
    "tam_kosu_basladi": "SONDA GEÇTİ ve TAM KOŞU BAŞLADI (~16,9 saat, 22 "
                        "periyot). Kararı ölçüm verdi: aralıklılık eşiği aşıldı.",
    "tam_kosu_bitti": "TAM KOŞU BİTTİ — hüküm koşunun kendi kanıt dosyasında "
                      "(silindir_gecis_3b_dr_des.json).",
    "tam_kosu_dustu": "TAM KOŞU DÜŞTÜ — sebep kayıtta; sonuç ÜRETİLMEDİ ve "
                      "yarım koşudan sayı okunmaz.",
}


def _karar_yaz(durum: str, s: dict | None, ek: dict | None = None) -> None:
    kayit = {
        "vaka": "Geçiş sınavı zinciri — sonda sonrası karar",
        "durum": durum,
        # HER KANIT DOSYASI KENDI HUKMUNU TASIR. Ilk surum yalniz `durum`
        # kodunu yaziyordu ve kanit-manifest kapisi bunu yakaladi: bir durum
        # KODU, dosyayi okuyan icin hüküm degildir.
        "verdikt": _HUKUM.get(durum, f"durum: {durum}"),
        "sonda": s,
        "_neden": ("Tam kosu ~16 saat (olculen 13,0 s/adim x 4400 adim). "
                   "Sonda o sureyi HARCAMADAN tek soruyu yanitlar: gecis "
                   "modeli devreye giriyor mu? Karar gammaInt'in olculen "
                   "minimumuna baglidir, yorum degil."),
        "zaman": time.strftime("%Y-%m-%d %H:%M"),
        "_uretim": "Üretim: python experiments/gecis_zinciri.py",
        **(ek or {}),
    }
    import ortam
    ortam.damgala(kayit)
    KARAR.write_text(json.dumps(kayit, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")


def main() -> int:
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")

    if TAM_KANIT.exists():
        print("tam koşu ZATEN bitmiş — zincir yapacak bir şey bulmadı")
        return 0

    t0 = time.time()
    s = sonda_hukmu()
    while s is None:
        if time.time() - t0 > AZAMI_BEKLEME_S:
            print("SONDA ZAMAN AŞIMI — tam koşu BAŞLATILMADI")
            _karar_yaz("sonda_zaman_asimi", None)
            return 1
        print(f"  sonda sürüyor ({(time.time()-t0)/60:.0f} dk)...", flush=True)
        time.sleep(BEKLEME_S)
        s = sonda_hukmu()

    print(f"SONDA BİTTİ: geçti={s['gecti']} gammaInt min={s['min']} "
          f"laminer=%{s['laminer_pct']}", flush=True)
    print(s["verdikt"], flush=True)

    if not s["gecti"]:
        # DORDUNCU ACIKLAMA DA DUSTU — ve 16 saate degil ~2 saate mal oldu.
        print("\nTAM KOŞU BAŞLATILMIYOR: duvar-çözünür ağ da tek başına "
              "yetmedi. 16 saatlik koşuya girmek için sebep YOK.")
        _karar_yaz("sonda_gecmedi_tam_kosu_YOK", s)
        return 0

    # BELLEK: sonda surecinin bellegi birakmasini bekle.
    while _bellek_pct() > BELLEK_TAVANI_PCT:
        if time.time() - t0 > AZAMI_BEKLEME_S:
            print("BELLEK BOŞALMADI — tam koşu BAŞLATILMADI")
            _karar_yaz("bellek_dolu", s, {"bellek_pct": _bellek_pct()})
            return 1
        print(f"  bellek %{_bellek_pct():.0f} > %{BELLEK_TAVANI_PCT:.0f}, "
              f"bekleniyor...", flush=True)
        time.sleep(BEKLEME_S)

    print("\nTAM KOŞU BAŞLATILIYOR (~16 saat, 22 periyot)", flush=True)
    _karar_yaz("tam_kosu_basladi", s, {"bellek_pct": _bellek_pct()})
    r = subprocess.run(
        [sys.executable, str(HERE / "silindir_gecis_3b.py"), "--ag", "des"],
        cwd=str(KOK), capture_output=True, text=True, errors="replace")
    kuyruk = (r.stdout or "")[-1500:]
    print(kuyruk)
    _karar_yaz("tam_kosu_bitti" if r.returncode == 0 else "tam_kosu_dustu", s,
               {"cikis_kodu": r.returncode, "son_ciktilar": kuyruk[-800:]})
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
