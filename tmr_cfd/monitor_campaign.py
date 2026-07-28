"""TMR GCI kampanyası CANLI monitör — terminal dashboard.

3 gridin (449/897/1793) iterasyon, Cd/Cl, kuvvet-drift ve plato/bitti durumunu periyodik
gösterir. Standalone V&V koşuları GUI'de görünmediğinden (analysis/ baypas) bu terminal
izleyicisi. Salt-okunur: yalnız case log/forceCoeffs okur, koşuya dokunmaz.

Kullanım:
  python tmr_cfd/monitor_campaign.py [alpha] [--once] [--poll N]
    alpha   : 0 (varsayılan) | 10 | ...   (case dizini α-ekini belirler)
    --once  : tek anlık görüntü (loop yok)
    --poll N: yenileme periyodu sn (varsayılan 15)
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from force_plateau import _read_force, forcecoeffs_dat, relative_drift  # noqa: E402

try:                                            # cp1254 (TR Windows) stdout α/° patlamasın
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# sessiz-yutma: kabul — modül-düzeyi uyumluluk kalkanı; çalışma-zamanı sonucu etkilemez
except (AttributeError, ValueError):
    pass

ALPHA = next((a for a in sys.argv[1:] if not a.startswith("-")), "0")
ONCE = "--once" in sys.argv
POLL = next((float(sys.argv[i + 1]) for i, a in enumerate(sys.argv) if a == "--poll"), 15.0)
SUF = "" if ALPHA in ("0", "0.0") else f"_a{ALPHA}"
TMR_REF = {"0": (0.0, 0.00809), "10": (1.0778, 0.01236)}
LEVELS = [("449", 57344), ("897", 229376), ("1793", 917504)]
WINDOW, TOL_CL, TOL_CD = 10, 3e-4, 1.5e-3   # lifting→Cl sıkı, α=0→Cd (force_plateau ile hizalı)


def _state(case: Path) -> dict:
    """Bir seviyenin durumu: başlamadı / kuruluyor / koşuyor / plato / ✅ BİTTİ + son Cd/Cl/drift."""
    if not (case / "system").is_dir():
        return {"durum": "başlamadı"}
    its, cds, cls = _read_force(forcecoeffs_dat(case))    # RESUME alt-dizinini de yakalar
    if not its:
        return {"durum": "kuruluyor"}           # mesh/decompose aşaması, henüz force yok
    d_cd = relative_drift(cds[-WINDOW:]) if len(cds) >= WINDOW else float("inf")
    cl_win = cls[-WINDOW:]
    lifting = bool(cl_win) and abs(sum(cl_win) / len(cl_win)) > 0.05
    d_cl = relative_drift(cl_win) if (lifting and len(cls) >= WINDOW) else 0.0
    ended = False
    log = case / "log.run"
    if log.exists():
        tail = log.read_text(errors="ignore")[-400:]
        ended = "Finalising parallel run" in tail or tail.rstrip().endswith("End")
    # Plato BİRİNCİL nicelik üzerinden (force_plateau ile aynı): lifting→Cl (sıkı TOL_CL),
    # α=0→Cd (TOL_CD). Aksi halde yavaş-creep eden ince grid sahte "plato" gösteriyordu.
    plato = (d_cl < TOL_CL) if lifting else (d_cd < TOL_CD)
    durum = "✅ BİTTİ" if ended else ("plato" if plato else "koşuyor")
    return {"durum": durum, "iter": int(its[-1]), "Cd": cds[-1], "Cl": cls[-1],
            "d_cd": d_cd, "d_cl": d_cl}


def render() -> tuple[str, bool]:
    cl_ref, cd_ref = TMR_REF.get(ALPHA, (None, None))
    L = [f"TMR GCI canlı monitör — α={ALPHA}°  (TMR ref: Cl={cl_ref} Cd={cd_ref}, "
         f"plato tol: Cl<{TOL_CL:g}/Cd<{TOL_CD:g})",
         f"{'grid':>5} {'hücre':>8} {'durum':<9} {'iter':>6} {'Cd':>10} {'Cl':>9} "
         f"{'driftCd':>8} {'driftCl':>8}"]
    all_done = True
    for lbl, cells in LEVELS:
        s = _state(HERE / f"n0012_{lbl}{SUF}")
        if s["durum"] != "✅ BİTTİ":
            all_done = False
        if "iter" in s:
            L.append(f"{lbl:>5} {cells:>8} {s['durum']:<9} {s['iter']:>6} {s['Cd']:>10.5f} "
                     f"{s['Cl']:>9.5f} {s['d_cd']:>8.1e} {s['d_cl']:>8.1e}")
        else:
            L.append(f"{lbl:>5} {cells:>8} {s['durum']:<9}")
    v = ROOT / f"tmr_gci_verdict{SUF}.json"
    if v.exists():
        r = json.loads(v.read_text(encoding="utf-8"))
        L.append("─" * 70)
        L.append("verdict: " + str(r.get("strict_gci_verdict") or r.get("sonuc", "—")))
    return "\n".join(L), all_done


def main() -> int:
    while True:
        out, done = render()
        print("\033[2J\033[H" + out + f"\n\n[{time.strftime('%H:%M:%S')}] "
              + ("tamamlandı." if done else f"yenileme {POLL:g}sn — Ctrl-C ile çık"), flush=True)
        if ONCE or done:
            return 0
        try:
            time.sleep(POLL)
        # sessiz-yutma: kabul — KeyboardInterrupt — kullanıcı izlemeyi bilerek kesti, hata değil
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
