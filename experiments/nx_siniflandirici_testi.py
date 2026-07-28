"""auto_pilot araç sınıflandırıcısını NX test setinde ölçer (AYRILMIŞ set).

auto_pilot hafızasındaki 241 kaydın 234'ü projenin kendi parametrik şekillerinden ya da
uzman etiketinden geliyor — yani sınıflandırıcı bugüne dek KENDİ dağılımında ölçüldü.
Bu script, NX'te üretilmiş ve etiketi inşa anında bilinen bağımsız aileyi kullanır;
öğrenme yapmaz, yalnız ölçer. Genelleme açığını görmenin tek dürüst yolu bu.

    python experiments/nx_siniflandirici_testi.py

Çıktı: nx_siniflandirici.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import trimesh  # noqa: E402

from auto_pilot import PRESET_MAP, classify_vehicle  # noqa: E402
from vehicle_pipeline import inspect_geometry  # noqa: E402

# Hangi aile ölçülecek: "test" (kalibrasyona hiç girmedi ama son turda hata analizine
# konu oldu) | "kor" (üçüncü aile, hiçbir turda bakılmadı — kirlenmemiş sayı).
AILE = os.environ.get("NX_OLC", "test")
_DIZIN = {"test": "nx_geo", "kor": "nx_geo_kor"}
GEO = HERE / _DIZIN.get(AILE, "nx_geo")
CIKTI_JSON = {"test": "nx_siniflandirici.json", "kor": "nx_siniflandirici_kor.json"}[AILE]
# Kural motoru yalnız 4 sınıf üretebilir; ince etiketler (kanatlı roket, tilt-rotor…)
# ancak öğrenilmiş kNN oyundan gelebilir. İki seviyeyi AYRI raporlamak şart:
# kural motorunu ulaşamayacağı bir etikette suçlamak ölçümü bozar.
KABA = {"roket": "roket", "kanatli_roket": "roket", "ucak": "ucak",
        "tilt_rotor": "ucak", "kanatli_vtol": "ucak", "kaldirici_govde": "ucak",
        "multikopter": "multikopter", "genel": "genel"}


def _metre_kopyasi(stl: Path, hedef: Path) -> dict:
    """NX mm cinsinden yazar; proje metre çalışır. Ölçek dönüşümü AÇIK yapılır."""
    m = trimesh.load(stl, force="mesh")
    m.apply_scale(1e-3)
    m.export(hedef)
    return {"ucgen": int(len(m.faces)), "watertight": bool(m.is_watertight),
            "hacim_m3": round(float(m.volume), 8),
            "boyut_m": [round(float(x), 4) for x in m.extents]}


_KORLUK = {
    "test": (
        "TAM KOR DEGIL. Ilk olcum (kural %51.2 / kNN-kaba %80.5 / ince %53.7) tam ayrik "
        "sette yapildi; donel_simetri turu da kor kaldi (esikler yalniz egitim ailesinde "
        "kalibre edildi). Ancak SON tur, bu sette kalan iki preset hatasina bakilarak "
        "yapilmis bir hata analizidir — bu yuzden buradaki sayilar bir miktar iyimserdir. "
        "Kirlenmemis sayi icin nx_siniflandirici_kor.json'a bakin."),
    "kor": (
        "TAM KOR. Ucuncu aile; ne ozellik tasarimi ne esik kalibrasyonu ne de hata "
        "analizi bu aileye bakilarak yapildi. Uretim hatalari (temas etmeyen parcalar) "
        "duzeltildi ama bunlar SINIFLANDIRICI sonucuna bakilmadan giderildi. Buradaki "
        "sayilar sistemin gercek genelleme performansidir."),
}


def calistir() -> dict:
    etiketler = json.loads((GEO / "etiketler.json").read_text(encoding="utf-8"))
    kayitlar = []
    tmp = Path(tempfile.mkdtemp(prefix="nx_test_"))
    try:
        for g in etiketler["geometriler"]:
            stl = GEO / g["stl"]
            if not stl.exists():
                continue
            hedef = tmp / g["stl"]
            mesh_bilgi = _metre_kopyasi(stl, hedef)
            geo = inspect_geometry(str(hedef))
            sonuc = classify_vehicle(geo)
            gercek = g["etiket"]
            kayitlar.append({
                "ad": g["ad"], "gercek": gercek, "gercek_kaba": KABA[gercek],
                "kural": sonuc["kural_tip"], "son": sonuc["tip"],
                "guven": sonuc["guven"], "ogrenilen": sonuc.get("ogrenilen"),
                "metrik": sonuc["metrik"], "kordal_tol": g["kordal_tol"],
                **mesh_bilgi})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"etiket_kaynagi": etiketler["kaynak"], "kayitlar": kayitlar}


def ozetle(kayitlar: list[dict]) -> dict:
    n = len(kayitlar)
    kaba_dogru = sum(1 for k in kayitlar if k["kural"] == k["gercek_kaba"])
    ince_dogru = sum(1 for k in kayitlar if k["son"] == k["gercek"])
    son_kaba_dogru = sum(1 for k in kayitlar if KABA.get(k["son"], k["son"]) == k["gercek_kaba"])
    # ASIL ÖNEMLİ METRİK: ince etiket yanlış olsa bile SEÇİLEN AYAR doğru olabilir
    # (tilt_rotor ve kanatli_vtol zaten 'ucak' preset'ini kullanır). Analiz sonucunu
    # etkileyen şey preset'tir; ince etiket yalnız rapor diliidir.
    preset_dogru = sum(1 for k in kayitlar
                       if PRESET_MAP.get(k["son"]) == PRESET_MAP.get(k["gercek"]))
    preset_hatalari = [{"ad": k["ad"], "gercek": k["gercek"], "tahmin": k["son"],
                        "preset_gercek": PRESET_MAP.get(k["gercek"]),
                        "preset_tahmin": PRESET_MAP.get(k["son"])}
                       for k in kayitlar if PRESET_MAP.get(k["son"]) != PRESET_MAP.get(k["gercek"])]
    knn_bozdu = [k["ad"] for k in kayitlar
                 if k["kural"] == k["gercek_kaba"] and KABA.get(k["son"], k["son"]) != k["gercek_kaba"]]
    knn_duzeltti = [k["ad"] for k in kayitlar
                    if k["kural"] != k["gercek_kaba"] and KABA.get(k["son"], k["son"]) == k["gercek_kaba"]]
    hatalar = Counter((k["gercek_kaba"], k["kural"]) for k in kayitlar
                      if k["kural"] != k["gercek_kaba"])
    # Aynı katının ince/kaba üçgenlemesi farklı sınıf veriyorsa sınıflandırıcı
    # geometriye değil mesh yoğunluğuna bakıyor demektir.
    ciftler = {}
    for k in kayitlar:
        ad = k["ad"][:-5] if k["ad"].endswith("_kaba") else k["ad"]
        ciftler.setdefault(ad, {})[k["ad"].endswith("_kaba")] = k
    tess = [{"ad": a, "ince": v[False]["son"], "kaba": v[True]["son"],
             "ucgen_ince": v[False]["ucgen"], "ucgen_kaba": v[True]["ucgen"]}
            for a, v in ciftler.items() if len(v) == 2]
    tess_kararsiz = [t["ad"] for t in tess if t["ince"] != t["kaba"]]
    return {
        "adet": n,
        "kural_kaba_dogruluk": round(kaba_dogru / n, 3),
        "son_kaba_dogruluk": round(son_kaba_dogru / n, 3),
        "son_ince_dogruluk": round(ince_dogru / n, 3),
        "preset_dogruluk": round(preset_dogru / n, 3),
        "preset_hatalari": preset_hatalari,
        "knn_bozdugu": knn_bozdu, "knn_duzelttigi": knn_duzeltti,
        "kural_hatalari": [{"gercek": g, "tahmin": t, "adet": c}
                           for (g, t), c in hatalar.most_common()],
        "tessellation": {"cift_sayisi": len(tess), "kararsiz": tess_kararsiz,
                         "ayrinti": tess},
    }


def main() -> int:
    if not (GEO / "etiketler.json").exists():
        print("nx_geo/etiketler.json yok — önce NX üreticisini koşun:\n"
              '  "C:\\Program Files\\Siemens\\NX2412\\NXBIN\\run_journal.exe" '
              "experiments/nx_geometri_uret.py")
        return 1
    d = calistir()
    o = ozetle(d["kayitlar"])
    out = {
        "vaka": f"auto_pilot arac siniflandirici — NX ayrik set ({AILE})",
        "kaynak": d["etiket_kaynagi"],
        "_neden": ("Siniflandiricinin hafizasi kendi parametrik sekillerinden olusuyor; "
                   "bu set bagimsiz ve etiketi insa aninda bilinen AYRILMIS settir. "
                   "Ogrenme yapilmaz, yalniz olculur."),
        "_korluk": _KORLUK[AILE],
        "ozet": o, "kayitlar": d["kayitlar"],
        "verdikt": _verdikt(o),
        "_uretim": ("Üretim: run_journal.exe experiments/nx_geometri_uret.py"
                    " && python experiments/nx_siniflandirici_testi.py"),
    }
    (HERE.parent / CIKTI_JSON).write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{'geometri':24} {'gercek':16} {'kural':12} {'son':16} guven")
    for k in d["kayitlar"]:
        im = "✓" if k["son"] == k["gercek"] else ("~" if KABA.get(k["son"]) == k["gercek_kaba"]
                                                  else "✗")
        print(f"{k['ad']:24} {k['gercek']:16} {k['kural']:12} {k['son']:16} "
              f"{k['guven']:.2f} {im}")
    print(f"\nkural kaba dogruluk : {o['kural_kaba_dogruluk']:.1%}")
    print(f"son   kaba dogruluk : {o['son_kaba_dogruluk']:.1%}")
    print(f"son   ince dogruluk : {o['son_ince_dogruluk']:.1%}")
    print(f"PRESET dogrulugu    : {o['preset_dogruluk']:.1%}  "
          f"(analiz ayarini gercekten etkileyen metrik)")
    for h in o["preset_hatalari"]:
        print(f"   ! {h['ad']}: {h['preset_gercek']} yerine {h['preset_tahmin']}")
    print(f"kNN bozdugu: {o['knn_bozdugu']}")
    print(f"kNN duzelttigi: {o['knn_duzelttigi']}")
    print(f"tessellation kararsiz: {o['tessellation']['kararsiz']}")
    print("\n" + out["verdikt"])
    print("-> " + CIKTI_JSON)
    return 0


def _verdikt(o: dict) -> str:
    p = []
    if o["kural_kaba_dogruluk"] >= 0.9:
        p.append(f"Kural motoru bagimsiz sette %{o['kural_kaba_dogruluk'] * 100:.0f} "
                 "kaba-sinif dogrulugu tutturuyor")
    else:
        p.append(f"⚠️ Kural motoru bagimsiz sette yalniz %{o['kural_kaba_dogruluk'] * 100:.0f} "
                 "kaba-sinif dogrulugunda — kendi dagiliminda olculen guven yaniltici")
    if o["knn_bozdugu"]:
        p.append(f"⚠️ ogrenilen kNN {len(o['knn_bozdugu'])} vakada DOGRU kural hukmunu "
                 f"bozdu ({', '.join(o['knn_bozdugu'][:4])})")
    elif o["knn_duzelttigi"]:
        p.append(f"kNN {len(o['knn_duzelttigi'])} vakayi duzeltti, hic bozmadi")
    if o["tessellation"]["kararsiz"]:
        p.append(f"⚠️ {len(o['tessellation']['kararsiz'])} katida ince/kaba ucgenleme FARKLI "
                 "sinif verdi — hukum geometriye degil mesh yogunluguna duyarli")
    else:
        p.append("ucgenleme yogunlugu hukmu degistirmiyor")
    p.append(f"ince (8-sinif) dogruluk %{o['son_ince_dogruluk'] * 100:.0f}, ANALIZ AYARINI "
             f"belirleyen preset dogrulugu %{o['preset_dogruluk'] * 100:.0f}")
    return ". ".join(p) + "."


if __name__ == "__main__":
    sys.exit(main())
