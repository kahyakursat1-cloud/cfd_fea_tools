"""Analiz iş-kuyruğu — '5 varyantı sıraya at, yemeğe git' iş-akışı.

Bu haftaki elle-PowerShell kampanya orkestratörlerinin genelleştirilmişi: işler
kuyruk.jsonl'e eklenir; TEK worker sırayla koşar (disk bekçisi + iş-başına log).
Worker kilidi dosya-tabanlıdır (kuyruk.lock, PID'li) — ikinci worker başlamaz;
CFD zaten makineyi doyurur, paralel worker anlamsız.

Durumlar: bekliyor → kosuyor → bitti | hata. Her güncelleme dosyayı atomik
yeniden yazar (küçük ölçek; yüzlerce iş için yeterli).

CLI: python kuyruk.py ekle model.stl [--tip roket --hiz 30 --alpha 0 --kalite hassas
                                      --duyarlilik --seviyeler 4]
     python kuyruk.py listele | calis | temizle
GUI: app_analyzer 'Kuyruğa Ekle' + KuyrukDialog.
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
import uuid
from pathlib import Path

import bellek_kapisi

HERE = Path(__file__).resolve().parent
KUYRUK = HERE / "kuyruk.jsonl"
KILIT = HERE / "kuyruk.lock"
MIN_DISK_GB = 8.0


def _yukle() -> list[dict]:
    if not KUYRUK.exists():
        return []
    out, bozuk = [], []
    for i, line in enumerate(KUYRUK.read_text(encoding="utf-8").splitlines(), 1):
        try:
            out.append(json.loads(line))
        except Exception as e:
            # BIR IS SESSIZCE KAYBOLUYORDU. Bozuk satir atlaniyor ve kullanici
            # kuyruga 5 is ekleyip 4 goruyordu; hangisinin nerede kaldigini
            # ogrenmesinin yolu yoktu. Satir yine atlanir (tek bozuk kayit tum
            # kuyrugu bloke etmemeli) ama SAYILIR ve soylenir.
            bozuk.append(f"satır {i}: {type(e).__name__}")
    # KOSULSUZ yazilir: `if bozuk` ile yazmak, dosya duzeltildikten sonra da
    # eski uyariyi sonsuza kadar gosterirdi (testte yakalandi).
    _BOZUK_SATIRLAR[:] = bozuk
    return out


# Son _yukle cagrisinda atlanan bozuk satirlar — `durum()` ve CLI bunu gosterir.
_BOZUK_SATIRLAR: list[str] = []


def bozuk_kayitlar() -> list[str]:
    """Kuyruk dosyasında okunamayan satırlar (son yükleme). Boşsa sorun yok."""
    _yukle()
    return list(_BOZUK_SATIRLAR)


def _kaydet(isler: list[dict]) -> None:
    tmp = KUYRUK.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in isler),
                   encoding="utf-8")
    tmp.replace(KUYRUK)


def ekle(params: dict) -> dict:
    """İş ekle. params = run_vehicle_analysis kwargs'ları (stl_path zorunlu)."""
    if not params.get("stl_path"):
        raise ValueError("stl_path zorunlu")
    is_ = {"id": uuid.uuid4().hex[:8], "ts": time.strftime("%Y-%m-%d %H:%M"),
           "durum": "bekliyor", "params": params}
    isler = _yukle()
    isler.append(is_)
    _kaydet(isler)
    return is_


def listele() -> list[dict]:
    return _yukle()


def temizle(hepsi: bool = False) -> int:
    """bitti/hata işleri (hepsi=True: tümünü) kuyruktan düşür; kalan sayısı döner."""
    isler = ([] if hepsi else
             [i for i in _yukle() if i["durum"] in ("bekliyor", "kosuyor", "yarim")])
    _kaydet(isler)
    return len(isler)


def _disk_gb() -> float:
    import shutil
    return shutil.disk_usage(HERE).free / 1e9


def _surec_yasiyor(pid: int) -> bool | None:
    """PID canlı mı? Bilinemiyorsa None — 'bilmiyorum' ile 'ölü' KARIŞTIRILMAZ,
    çünkü ölü sanıp kilidi almak koşan bir worker'ın üstüne ikinci worker salar.

    Tek mekanizma psutil'dir. Elle yazılmış yedekler (posix `os.kill(pid, 0)`,
    Windows ctypes `OpenProcess`) kaçınılmaz olarak geniş `except` blokları
    getiriyordu ve bu depo sessiz-yutmayı sayıyla sınırlıyor. psutil yoksa
    dürüst cevap "sorulamadı"dır; kilit o zaman güvenli tarafta bırakılır.
    (Windows'ta `os.kill(pid, 0)` zaten kullanılamaz: sinyal göndermez,
    süreci ÖLDÜRÜR.)
    """
    if pid <= 0:
        return False
    if importlib.util.find_spec("psutil") is None:
        return None
    import psutil
    return psutil.pid_exists(pid)


def kilit_durumu() -> dict:
    """Kilit kimde ve o süreç hâlâ yaşıyor mu?"""
    if not KILIT.exists():
        return {"kilitli": False}
    ham = KILIT.read_text(encoding="utf-8", errors="ignore").strip()
    pid = int(ham) if ham.isdigit() else -1
    yasiyor = _surec_yasiyor(pid)
    return {"kilitli": True, "pid": pid, "yasiyor": yasiyor,
            "bayat": yasiyor is False,
            "_not": ("kilit sahibi süreç YOK — bayat kilit (çökme/kapanma)"
                     if yasiyor is False else
                     "kilit sahibi yaşıyor" if yasiyor else
                     "süreç durumu SORULAMADI — kilit güvenli tarafta bırakıldı")}


def _kilit_al() -> bool:
    """Kilidi al. BAYAT KİLİT DEVRALINIR: worker çökerse ya da makine kapanırsa
    (bu depoda ölçüldü — oturum ortasında bilgisayar kapandı) kilit dosyası
    diskte kalıyordu ve kuyruk KALICI olarak bloke oluyordu; kimse PID'in canlı
    olup olmadığına bakmıyordu. Süreç durumu SORULAMIYORSA kilit devralınmaz."""
    try:
        fd = os.open(KILIT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        d = kilit_durumu()
        if not d.get("bayat"):
            return False
        KILIT.unlink(missing_ok=True)
        try:
            fd = os.open(KILIT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        # sessiz-yutma: kabul — kilit ZATEN varsa baska worker calisiyor demektir;
        # bu bir hata degil beklenen yaristir. False donusu cagirana "kilit
        # alinamadi" bilgisini tasiyor ve cagiran bayat-kilit devralmasini
        # ayrica deniyor (bkz. kilit_durumu).
        except FileExistsError:
            return False


def iptal(is_id: str) -> dict:
    """Bekleyen işi iptal et. KOŞAN iş iptal EDİLMEZ: çözücü ayrı bir süreçtir
    ve yarım bırakılan case dizini 'başarısız' ile 'hiç koşmadı'yı karıştırır."""
    for i in _yukle():
        if i["id"] == is_id:
            if i["durum"] != "bekliyor":
                return {"ok": False, "durum": i["durum"],
                        "mesaj": f"yalnız 'bekliyor' işler iptal edilir (bu: {i['durum']})"}
            _guncelle(is_id, durum="iptal", iptal_ts=time.strftime("%Y-%m-%d %H:%M"))
            return {"ok": True, "durum": "iptal"}
    return {"ok": False, "mesaj": f"iş bulunamadı: {is_id}"}


def yarim_isaretle() -> list[str]:
    """Kilit sahibi ölmüşken 'kosuyor' kalan işleri YARIM diye işaretle.

    Bunlar sessizce yeniden koşulmaz: koşu saatler sürmüş ve yarım bir case
    dizini bırakmış olabilir; hangisinin atılıp hangisinin sürdürüleceği
    kullanıcının kararıdır. `devam()` açıkça çağrılır."""
    d = kilit_durumu()
    if d.get("kilitli") and not d.get("bayat"):
        return []
    yarim = [i["id"] for i in _yukle() if i["durum"] == "kosuyor"]
    for is_id in yarim:
        _guncelle(is_id, durum="yarim",
                  yarim_neden="worker süreci sonlandı (çökme/kapanma) — koşu tamamlanmadı")
    return yarim


def devam(is_id: str | None = None) -> int:
    """Yarım kalan işleri yeniden kuyruğa al (hepsi ya da tek bir iş)."""
    n = 0
    for i in _yukle():
        if i["durum"] == "yarim" and (is_id is None or i["id"] == is_id):
            _guncelle(i["id"], durum="bekliyor", devam_ts=time.strftime("%Y-%m-%d %H:%M"))
            n += 1
    return n


def _guncelle(is_id: str, **alanlar) -> None:
    isler = _yukle()
    for i in isler:
        if i["id"] == is_id:
            i.update(alanlar)
    _kaydet(isler)


def calis(runner=None, once: bool = False) -> dict:
    """Worker: bekleyen işleri SIRAYLA koş. runner enjekte edilebilir (test);
    varsayılan run_vehicle_analysis. once=True → tek iş koşup çık (test/adım-adım)."""
    # BAYAT KILIT + YARIM IS: once tespit, sonra kilit. Sirasi onemli — kilidi
    # aldiktan sonra bakarsak "kilit sahibi olmus mu" sorusunu kendimize sorarız.
    _yarim = yarim_isaretle()
    if not _kilit_al():
        return {"durum": "kilitli", "mesaj": f"başka worker aktif ({KILIT})",
                "kilit": kilit_durumu()}
    ozet = {"bitti": 0, "hata": 0, "atlandi_disk": 0, "bekletildi_bellek": 0,
            "yarim_bulundu": len(_yarim)}
    try:
        if runner is None:
            from vehicle_pipeline import run_vehicle_analysis

            def runner(p):
                r = run_vehicle_analysis(**p)
                return {"status": r.status, "cd": r.cd,
                        "u_pct": (r.belirsizlik or {}).get("u_toplam_pct"),
                        "rapor": r.report, "hata": (r.error or "")[-300:]}
        while True:
            bekleyen = [i for i in _yukle() if i["durum"] == "bekliyor"]
            if not bekleyen:
                break
            is_ = bekleyen[0]
            if _disk_gb() < MIN_DISK_GB:
                _guncelle(is_["id"], durum="hata",
                          sonuc={"hata": f"disk < {MIN_DISK_GB} GB — atlandı"})
                ozet["atlandi_disk"] += 1
                continue
            # BELLEK KOTASI: disk bekcisinin esi. Bellegi dolu bir makinede
            # kuyrugu surdurmek isi bitirmez, makineyi takasa sokar ve SONRAKI
            # isleri de yavaslatir. Is BEKLIYOR kalir (hata degil) — bellek
            # bosalinca ayni kuyruk onu koşar.
            _bos = bellek_kapisi.bos_bellek_gb()
            if _bos is not None and _bos < bellek_kapisi.EN_AZ_BOS_GB:
                ozet["bekletildi_bellek"] += 1
                _guncelle(is_["id"], bellek_notu=(
                    f"boş bellek {_bos:.1f} GB < {bellek_kapisi.EN_AZ_BOS_GB} GB "
                    "— iş BEKLİYOR olarak bırakıldı, worker durdu"))
                break
            _guncelle(is_["id"], durum="kosuyor", baslama=time.strftime("%H:%M:%S"))
            t0 = time.time()
            try:
                sonuc = runner(is_["params"])
                durum = "bitti" if sonuc.get("status") == "ok" else "hata"
            except Exception as e:
                sonuc, durum = {"hata": str(e)[-300:]}, "hata"
            _guncelle(is_["id"], durum=durum, sonuc=sonuc,
                      sure_dk=round((time.time() - t0) / 60, 1))
            ozet["bitti" if durum == "bitti" else "hata"] += 1
            if once:
                break
    finally:
        KILIT.unlink(missing_ok=True)
    return ozet


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cli = argparse.ArgumentParser()
    cli.add_argument("komut", choices=["ekle", "listele", "calis", "temizle",
                                       "iptal", "devam", "kilit"])
    cli.add_argument("stl", nargs="?", help="ekle icin STL; iptal/devam icin is id")
    cli.add_argument("--tip", default="ucak")
    cli.add_argument("--hiz", type=float, default=30.0)
    cli.add_argument("--alpha", type=float, default=0.0)
    cli.add_argument("--kalite", default="standart")
    cli.add_argument("--duyarlilik", action="store_true")
    cli.add_argument("--seviyeler", type=int, default=3)
    cli.add_argument("--ref-bump", dest="ref_bump", default="0",
                     help="ek yuzey iyilestirme kademesi; tam sayi ya da 'oto'")
    args = cli.parse_args()
    if args.komut == "ekle":
        if not args.stl:
            sys.exit("ekle için STL yolu gerekli")
        # ref_bump KUYRUK CLI'SINDE YOKTU: GUI "Kuyruga Ekle" ile "oto" gonderiyor,
        # bu komut ise hic gondermiyordu — ayni kuyruk, ayni worker, isin NASIL
        # eklendigine gore FARKLI y+ davranisi. Bayrak eklendi ve varsayilani
        # vehicle_pipeline CLI'siyle AYNI ("0"): betikte acik ve tekrarlanabilir
        # olan iyidir, "oto" geometriye gore degisir. Fark artik KASITLI ve
        # belgeli (bkz. tests/test_giris_noktasi_esdegerligi.py).
        is_ = ekle({"stl_path": args.stl, "vehicle_type": args.tip, "velocity": args.hiz,
                    "alpha_deg": args.alpha, "quality": args.kalite,
                    "ref_bump": args.ref_bump,
                    "mesh_sensitivity": args.duyarlilik, "mesh_levels": args.seviyeler})
        print(json.dumps(is_, indent=2, ensure_ascii=False))
    elif args.komut == "listele":
        # Bozuk satir bir ISIN KAYBI demektir; listenin basinda soylenir ki
        # kullanici "5 ekledim 4 goruyorum" ile bas basa kalmasin.
        for _b in bozuk_kayitlar():
            print(f"⚠ KUYRUK DOSYASINDA OKUNAMAYAN KAYIT — {_b} (o iş listede YOK)")
        for i in listele():
            p = i["params"]
            print(f"[{i['durum']:>8}] {i['id']}  {Path(p['stl_path']).name}  "
                  f"tip={p.get('vehicle_type')} V={p.get('velocity')} "
                  f"kalite={p.get('quality')}  {i.get('sure_dk', '')}"
                  + (f"  Cd={i['sonuc'].get('cd')}" if i.get("sonuc") else ""))
    elif args.komut == "temizle":
        print("kalan:", temizle())
    elif args.komut == "iptal":
        if not args.stl:
            sys.exit("iptal icin is id gerekli")
        print(json.dumps(iptal(args.stl), indent=2, ensure_ascii=False))
    elif args.komut == "devam":
        yarim_isaretle()
        print(f"{devam(args.stl)} is yeniden kuyruga alindi")
    elif args.komut == "kilit":
        print(json.dumps(kilit_durumu(), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(calis(), indent=2, ensure_ascii=False))
