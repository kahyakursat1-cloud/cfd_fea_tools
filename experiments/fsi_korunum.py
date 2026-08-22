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
        })

    kesin = [k for k in kayit
             if max(k["kuvvet_hatasi"], k["moment_hatasi"],
                    k["arayuz_isi_hatasi"]) <= KESIN_ESIK]
    # ALANI TUTAN vakalar artigi SAF ORNEKLEME olarak okutur; hukum oradan
    # kurulur, cunku ote vakalarda iki sebep ayrilamaz.
    temiz = [k for k in kayit if k["alan_farki_pct"] <= 0.5]
    en_kotu = max(kayit, key=lambda k: k["aktarim_hatasi_pct"]) if kayit else None

    return {
        "vaka": "FSI yük aktarımında korunum — üç metrik",
        "_neden": ("Mevcut iki metrik (kuvvet, moment) FEA yuzu -> dugum "
                   "dagitimini olcer ve esit-uctebir semasinda YAPI GEREGI "
                   "kesindir. Gercekten korunmayan adim CFD -> FEA basinc "
                   "aktarimidir ve HIC olculmuyordu."),
        "olculen_vaka": len(kayit),
        "vakalar": kayit,
        "olculemeyen": dusen,
        "yapi_geregi_kesin_olan": f"{len(kesin)}/{len(kayit)}",
        "verdikt": (
            (f"YAPI GEREĞİ KESİN OLANLAR DOĞRULANDI ({len(kesin)}/{len(kayit)} "
             f"vakada kuvvet, moment ve arayüz işi ≤ {KESIN_ESIK:g}). AMA "
             f"KORUNMAYAN ADIM ÖLÇÜLDÜ: CFD→FEA basınç aktarımı "
             f"%{min(k['aktarim_hatasi_pct'] for k in kayit):.1f}–"
             f"%{en_kotu['aktarim_hatasi_pct']:.1f} arasında artık bırakıyor "
             f"(en kötü: {en_kotu['vaka']}). Alanı tutan "
             f"{len(temiz)} vakada artık SAF ÖRNEKLEME hatasıdır.")
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
