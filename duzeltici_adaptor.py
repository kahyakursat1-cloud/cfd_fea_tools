"""Düzeltici katmanı GERÇEK araç çözücüsüne bağlayan adaptör.

`duzeltici.py` bilerek çözücü bilmez: kanıt sözlüğü alır, kurulum değişikliği
döndürür, yeniden koşmayı çağırana bırakır. Bu dosya o boşluğu doldurur ve
KATMANIN TEK ÇÖZÜCÜ-BİLEN parçasıdır. Ayrı tutulmasının nedeni, karar
mantığının çözücüden bağımsız kalması: `duzeltici.py` çözücüsüz test edilir,
burası ise yalnız çeviri yapar.

BU ADAPTÖRÜN YAPMADIĞI ŞEY: hiçbir sonucu değiştirmez. Yalnız
`run_vehicle_analysis`'i farklı KURULUM argümanlarıyla yeniden çağırır.

Kullanım (app_analyzer / vehicle_pipeline içinden):

    from duzeltici_adaptor import duzelterek_analiz
    r, duzeltme = duzelterek_analiz(stl, vehicle_type="ucak", alpha_deg=8.0)
    print(duzeltme.verdikt)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duzeltici as D

# Düzelticinin ürettiği kurulum anahtarları → run_vehicle_analysis argümanları.
# Alt-çizgiyle başlayanlar İÇ anahtardır (çözücüye geçmez, niyeti taşır).
ARGUMAN_ESLEMESI = {
    "nut_wall": None,          # duvar işlemi doğrudan argüman değil; n_layers/yplus üzerinden
    "k_wall": None,
    "force_gentle": None,      # araç hattında karşılığı yok; kaydedilir
    "turbulence_model": "turbulence_model",
    "n_layers": "n_layers",
    "yplus_target": "yplus_target",
    "quality": "quality",
    "mesh_levels": "mesh_levels",
}


def _duvar_islemi_oku(case_dir: str | Path | None) -> str:
    """Duvar işlemini VAKADAN oku, ayarlardan ÇIKARSAMA.

    Niyet ile gerçeklik ayrışabiliyor: `n_layers>0` istenmiş olması duvarın
    çözüldüğü anlamına gelmez (katman çökmesi ölçüldü). Tek güvenilir kaynak
    `0/nut` içindeki sınır koşuludur.
    """
    if not case_dir:
        return ""
    f = Path(case_dir) / "0" / "nut"
    if not f.exists():
        return ""
    m = re.search(r"type\s+(nut\w+)", f.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else ""


def kanit_kur(r: Any, referans_ag_ailesi: str | None = None,
              kaba_cozum: str | None = None) -> dict:
    """VehicleAnalysisResult → düzelticinin okuduğu kanıt sözlüğü.

    `referans_ag_ailesi` ve `kaba_cozum` ÇAĞIRANDAN gelir çünkü ikisi de
    araç hattının kendiliğinden bilemeyeceği dış olgulardır. Verilmezlerse
    ilgili düzeltmeler "tespit edildi ama uygulanamaz" olarak raporlanır —
    sessizce atlanmaz.
    """
    ms = getattr(r, "mesh_duyarlilik", None) or {}
    gci = ms.get("gci") or {}
    st = getattr(r, "sinir_tabaka", None) or {}
    uyarilar = " ".join(str(x) for x in (getattr(r, "uyarilar", None) or []))

    return {
        "sinif": D.TREND,
        "kurulum": {
            "duvar_islemi": _duvar_islemi_oku(getattr(r, "case_dir", "")),
            "katman_sayisi": st.get("katman_sayisi"),
            "referans_ag_ailesi": referans_ag_ailesi,
            "kaba_cozum": kaba_cozum,
        },
        "olculen": {
            "yplus": st.get("yplus") or {},
            "gozlenen_mertebe": gci.get("p"),
            "Cl": getattr(r, "cl", None),
            "Cd": getattr(r, "cd", None),
            "sigFpe": "sigFpe" in uyarilar,
            "hata": uyarilar,
        },
        "_case_dir": getattr(r, "case_dir", ""),
    }


def duzelterek_analiz(stl_path, *, referans: float | None = None,
                      referans_ag_ailesi: str | None = None,
                      kaba_cozum: str | None = None,
                      maks: int = D.MAKS_DENEME, **kw):
    """Koş → guard → (gerekirse) düzelt → yeniden koş → yeniden sınıflandır.

    `referans` verilirse iyileşme ONA GÖRE ölçülür. Verilmezse düzeltici bir
    kusuru giderdiğini görebilir ama İŞE YARAYIP YARAMADIĞINI ölçemez ve bunu
    "etkisi ölçülemedi" diye yazar. Bu, referanssız koşuda düzeltmeyi
    "başarılı" saymaktan yeğdir.

    Döner: (son VehicleAnalysisResult, DuzelticiSonuc)
    """
    from vehicle_pipeline import run_vehicle_analysis

    son = {"r": run_vehicle_analysis(stl_path, **kw)}
    ayarlar = dict(kw)

    def _hata(kanit: dict) -> float | None:
        if referans in (None, 0):
            return None
        cd = (kanit.get("olculen") or {}).get("Cd")
        return None if cd is None else 100.0 * abs(cd - referans) / abs(referans)

    def _yeniden_kos(kanit: dict, degisiklik: dict) -> dict:
        # Fiziksel-olmayanı reddet: yeniden koşmak DEĞİL, koşuyu düşürmek.
        if degisiklik.get("_kosu_durumu") == "BASARISIZ":
            k = dict(kanit)
            k["sinif"] = D.OUT
            return k
        for anahtar, arg in ARGUMAN_ESLEMESI.items():
            if arg and anahtar in degisiklik:
                ayarlar[arg] = degisiklik[anahtar]
        # Duvar işlemi değişikliği araç hattında AĞ üzerinden uygulanır:
        # düşük-Re istenmişse katman iste ve y⁺ hedefini indir.
        if degisiklik.get("nut_wall", "").startswith("nutLowRe"):
            ayarlar["n_layers"] = max(int(ayarlar.get("n_layers") or 0), 10)
            ayarlar["yplus_target"] = 1.0
        son["r"] = run_vehicle_analysis(stl_path, **ayarlar)
        return kanit_kur(son["r"], referans_ag_ailesi, kaba_cozum)

    kanit = kanit_kur(son["r"], referans_ag_ailesi, kaba_cozum)
    sonuc = D.duzelt(kanit, _yeniden_kos, _hata, maks=maks)
    return son["r"], sonuc
