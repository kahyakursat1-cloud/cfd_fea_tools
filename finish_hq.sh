#!/usr/bin/env bash
# hq tamamlayıcı v2: SADECE eksik (<6 anchor) tipleri hedefler (BATCH_TIPLER) — dolu tipi
# tekrarlamaz. Entegre janitor (disk). 8 tip de ≥6 olana dek round'lar, sonra final CV.
set -u
cd /d/bilsem_beyin/cfd_fea_tools || exit 1
export PYTHONUTF8=1
LOG=overnight_ml.log
SENT="HQ_FINISH2_DONE"
say(){ echo "[$(date '+%m-%d %H:%M:%S')] FINISH2: $*" | tee -a "$LOG"; }

# entegre janitor: tamamlanan case dizinlerini sil, en yeni 2'yi koru (SENT'e kadar)
( while ! grep -q "$SENT" "$LOG" 2>/dev/null; do
    keep=$(ls -dt vehicle_runs/_batch_geo_hq/*_prep/ 2>/dev/null | head -2 | xargs -n1 basename 2>/dev/null | tr '\n' '|')
    for d in vehicle_runs/_batch_geo_hq/*_prep; do
      b=$(basename "$d"); echo "$keep" | grep -q "${b}|" || rm -rf "$d" 2>/dev/null
    done
    sleep 600
  done ) &
say "janitor başladı (PID $!)"

underfilled(){
  python - <<'PY'
import json,collections
T=("roket","kanatli_roket","ucak","multikopter","genel","tilt_rotor","kanatli_vtol","kaldirici_govde")
c=collections.Counter()
try:
    for ln in open("auto_pilot_memory_hq.jsonl",encoding="utf-8"):
        d=json.loads(ln)
        if d.get("cd_toplam") is not None: c[d["onayli_tip"]]+=1
except FileNotFoundError: pass
print(",".join(t for t in T if c.get(t,0)<6))
PY
}

# hassas_nl: katmansız (ince kanat firar-kenarına katman örülemiyor → Cd=None). En çok 3 round.
for r in 1 2 3; do
  miss=$(underfilled)
  if [ -z "$miss" ]; then say "tüm tipler ≥6 → tamamlandı"; break; fi
  say "round $r: eksik tipler = [$miss] (hassas_nl, katmansız)"
  BATCH_TAG=hq BATCH_TIPLER="$miss" BATCH_MAX_MIN=480 python experiments/batch_learn.py 8 5 hassas_nl >>"$LOG" 2>&1
  say "round $r bitti (exit $?)"
done
say "round'lar bitti — kalan eksik (varsa): [$(underfilled)]"

n=$(wc -l < auto_pilot_memory_hq.jsonl 2>/dev/null || echo 0)
say "final CV ($n kayıt)"
CV_MEMORY=auto_pilot_memory_hq.jsonl CV_TAG=hq python experiments/surrogate_cv.py >>"$LOG" 2>&1
say "=== $SENT ==="
