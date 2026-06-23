"""CFD mesh-density × AoA knob-taraması — silent-failure assay'in CFD tarafı (Path A).
NACA0012 O-grid (truth = NASA Ladson Cl/Cd) üzerinde naive-kullanıcı knob'larını tara:
  mesh-density {kaba, orta, ince} × AoA {0,4} (bağlı akış — temiz truth).
Her config → simpleFoam → Cl/Cd → Ladson hatası. Kaba mesh sessiz-hata kaynağı mı?
validation_suite.NACA0012Validation'ı attribute-set ile yeniden kullanır (surgery yok).
Çıktı: cfd_mesh_sweep.jsonl (assay korpusu CFD hücreleri).
Kullanım (arka plan): python experiments/cfd_mesh_sweep.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validation_suite import NACA0012Validation  # noqa: E402

# (etiket, n_prof profil-nokta, n_norm duvar-normal hücre)
DENSITIES = [("coarse", 120, 40), ("mid", 200, 80), ("fine", 320, 110)]
ALPHAS = [0, 4]


def main():
    work = HERE.parent / "cfd_mesh_sweep_cases"
    work.mkdir(exist_ok=True)
    out = HERE.parent / "cfd_mesh_sweep.jsonl"
    out.write_text("", encoding="utf-8")
    rows = []
    for alpha in ALPHAS:
        for label, nprof, nnorm in DENSITIES:
            tag = f"a{alpha}_{label}"
            print(f"=== {tag} (n_prof={nprof}, n_norm={nnorm}) ===", flush=True)
            v = NACA0012Validation(str(work / tag))
            v.n_prof, v.n_norm = nprof, nnorm
            try:
                r = v.run(alpha)
            except Exception as e:
                r = {"error": str(e)[-200:]}
            cell = {"case": "naca0012-Ladson", "alpha": alpha, "density": label,
                    "n_prof": nprof, "n_norm": nnorm,
                    "Cl_sim": r.get("Cl_sim"), "Cd_sim": r.get("Cd_sim"),
                    "Cl_ref": r.get("Cl_ref"), "Cd_ref": r.get("Cd_ref"),
                    "Cl_err_pct": r.get("Cl_err_pct"), "Cd_err_pct": r.get("Cd_err_pct"),
                    "error": r.get("error")}
            rows.append(cell)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(cell, ensure_ascii=False) + "\n")
            if cell.get("error"):
                print(f"  [{tag}] HATA: {cell['error']}", flush=True)
            else:
                print(f"  [{tag}] Cl={cell['Cl_sim']} (ref {cell['Cl_ref']}, %{cell['Cl_err_pct']}) "
                      f"Cd={cell['Cd_sim']} (ref {cell['Cd_ref']}, %{cell['Cd_err_pct']})", flush=True)
    print(f"\nYAZILDI {out.name} ({len(rows)} config)", flush=True)
    print("Yorum: kaba mesh → Ladson'dan sapma bekleniyor; 3-density asimptotik-guard'ın "
          "kaba seviyeyi yakalayıp yakalamadığını ölçer. Assay korpusuna CFD hücreleri olarak girer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
