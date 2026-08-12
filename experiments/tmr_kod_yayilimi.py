"""NACA0012 çapasının u_D'si: TMR'nin kendi kod-arası yayılımından ÖLÇÜLDÜ.

NEDEN: `naca0012_a0` çapası u_D beyan etmiyordu ve triyaj onu KAYNAK-EKSİK
saymıştı --- çapa tanımı iki kaynak adı taşıyor (Ladson 1988 deneyi ve NASA
Turbulence Modeling Resource) ama tek sayı saklıyordu. Eksik olan ölçüm değil,
kayda geçmemiş ikinci sayıydı. Kaynağa bakıldı ve sayı ORADAYDI.

TMR, aynı doğrulama vakasını AYNI ağda (897x257) ve aynı türbülans modeliyle
(SA) yedi bağımsız kodla koşup sonuçlarını yayımlıyor. Çapanın referansı bir
deney değil, bu TMR değeridir; dolayısıyla o referansın belirsizliği, aynı
şeyi hesaplayan kodların birbirinden ne kadar ayrıldığıdır. Bu ölçülebilir:

    n=7, ortalama C_d = 0,008166,  1σ = 0,796 %,  tam aralık = 2,204 %

u_D olarak 1σ alınır --- ASME V&V 20'de u_D standart belirsizliktir (1σ), tam
aralık değil. Tam aralık yine de kayıtlıdır çünkü dağılım simetrik değil:
yedi koddan biri (TURNS, 0,00830) diğerlerinden belirgin biçimde ayrılıyor ve
o kod çıkarılırsa 1σ %0,36'ya iniyor. Aykırı değeri ATMIYORUZ; hangi kodun
"doğru" olduğuna karar verecek bir ölçütümüz yok ve atmak bandı yapay biçimde
daraltırdı.

NE KAPSAMAZ --- bu ayrım önemlidir: ölçülen şey KOD-ARASI yayılımdır, yani
aynı modeli aynı ağda çözen uygulamaların farkı. DENEYSEL belirsizliği
kapsamaz. TMR bu vaka için deneysel sürüklemeye dair açık bir uyarı taşıyor:
bu Re aralığında ölçülen sürükleme sınır tabakasının tetiklenmesinden (trip)
büyük ölçüde etkilenir ve McCroskey verisinde Re=3e6'daki tetiklenmiş
sürükleme Re=6e6'dakinden yaklaşık %10 yüksektir. Yani referans deneysel
olsaydı u_D bundan BÜYÜK olurdu. Buradaki sayı bir ALT SINIRDIR.

Kaynak: NASA Turbulence Modeling Resource, 2D NACA 0012 Airfoil Validation —
SA Model Results (M=0,15, Re=6·10^6, 897x257 ağ).
https://tmbwg.github.io/turbmodels/naca0012_val_sa.html

    python experiments/tmr_kod_yayilimi.py
Çıktı: tmr_kod_yayilimi.json
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KOK = HERE.parent
sys.path.insert(0, str(KOK))

CIKTI = KOK / "tmr_kod_yayilimi.json"

KAYNAK_URL = "https://tmbwg.github.io/turbmodels/naca0012_val_sa.html"
KOSUL = {"model": "SA", "mach": 0.15, "Re": 6.0e6, "alpha_deg": 0.0,
         "ag": "897x257"}

# TMR'nin YAYIMLADIGI degerler. Elle girildi; kaynak ve kosul yukarida.
CD_KODLAR = {
    "CFL3D": 0.00819,
    "FUN3D": 0.00812,
    "NTS": 0.00813,
    "JOE": 0.00812,
    "SUMB": 0.00813,
    "TURNS": 0.00830,
    "GGNS": 0.00817,
}


def yayilim(cd: dict[str, float]) -> dict:
    x = list(cd.values())
    ort, sigma = st.mean(x), st.stdev(x)
    en_uzak = max(cd, key=lambda k: abs(cd[k] - ort))
    kalan = [v for k, v in cd.items() if k != en_uzak]
    return {
        "n": len(x),
        "ortalama_cd": round(ort, 6),
        "sigma_cd": round(sigma, 6),
        "u_D_pct": round(100 * sigma / ort, 3),
        "aralik_pct": round(100 * (max(x) - min(x)) / ort, 3),
        "en_uzak_kod": en_uzak,
        "en_uzak_cd": cd[en_uzak],
        "en_uzak_haric_u_D_pct": round(100 * st.stdev(kalan) / st.mean(kalan), 3),
        "_aykiri_atilmadi": ("Hangi kodun dogru oldugunu belirleyecek bir "
                             "olcutumuz yok; atmak bandi YAPAY daraltirdi."),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    y = yayilim(CD_KODLAR)

    from validation_anchors import ANCHORS
    capa_cd = ANCHORS["naca0012_a0"]["Cd"]
    y["capa_cd"] = capa_cd
    y["capa_ortalamadan_sapma_pct"] = round(
        100 * abs(capa_cd - y["ortalama_cd"]) / y["ortalama_cd"], 2)

    rec = {
        "vaka": "NACA0012 α=0 — TMR kod-arası yayılımdan u_D",
        "_neden": ("Capa u_D beyan etmiyordu ve triyaj onu KAYNAK-EKSIK saydi: "
                   "iki kaynak adi tasiyor ama tek sayi sakliyordu. Kaynaga "
                   "bakildi, sayi ORADAYDI."),
        "kaynak": KAYNAK_URL,
        "kosul": KOSUL,
        "cd_kodlar": CD_KODLAR,
        "yayilim": y,
        "u_D_pct": y["u_D_pct"],
        "_ne_kapsamaz": (
            "KOD-ARASI yayilim olculdu: ayni modeli ayni agda cozen "
            "uygulamalarin farki. DENEYSEL belirsizligi KAPSAMAZ. TMR bu vaka "
            "icin acik uyari tasiyor: bu Re araliginda olculen surukleme sinir "
            "tabakasinin tetiklenmesinden buyuk olcude etkilenir (McCroskey "
            "verisinde Re=3e6'daki tetiklenmis surukleme Re=6e6'dakinden ~%10 "
            "yuksek). Referans deneysel olsaydi u_D bundan BUYUK olurdu."),
        "_sinif": "ALT SINIR",
        "_uretim": "Üretim: python experiments/tmr_kod_yayilimi.py",
    }
    rec["verdikt"] = (
        f"{y['n']} bağımsız kod, aynı ağ ({KOSUL['ag']}) ve aynı model "
        f"({KOSUL['model']}): ortalama C_d={y['ortalama_cd']}, 1σ = "
        f"%{y['u_D_pct']} (tam aralık %{y['aralik_pct']}). Çapanın taşıdığı "
        f"{capa_cd} bu ortalamadan %{y['capa_ortalamadan_sapma_pct']} sapıyor. "
        f"u_D = %{y['u_D_pct']} olarak ALT SINIR niteliğiyle beyan edildi.")

    import ortam
    ortam.damgala(rec)
    CIKTI.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")

    print(rec["vaka"] + "\n" + "=" * 74)
    for k, v in CD_KODLAR.items():
        isaret = "  <- en uzak" if k == y["en_uzak_kod"] else ""
        print(f"  {k:<8}{v:.5f}{isaret}")
    print("=" * 74)
    print(rec["verdikt"])
    print(f"-> {CIKTI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
