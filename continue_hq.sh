#!/usr/bin/env bash
# hq (hassas, duvar-çözünür) batch'i sürdür → bitince hq LOOCV. TMR bitti, beklemeye gerek yok.
# Mevcut 7 anchora EKLER (BATCH_TAG=hq → bellek/done kalıcı, kümülatif).
set -u
cd /d/bilsem_beyin/cfd_fea_tools || exit 1
export PYTHONUTF8=1
LOG=overnight_ml.log
say(){ echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

say "=== hq batch DEVAM (cap=6, budget=600dk) ==="
BATCH_TAG=hq BATCH_MAX_MIN=600 python experiments/batch_learn.py 6 4 hassas >>"$LOG" 2>&1
say "hq batch bitti (exit $?)"

if [ -f auto_pilot_memory_hq.jsonl ]; then
  n=$(wc -l < auto_pilot_memory_hq.jsonl)
  say "hq bellek: $n kayıt → LOOCV (surrogate_cv_hq.json)"
  CV_MEMORY=auto_pilot_memory_hq.jsonl CV_TAG=hq python experiments/surrogate_cv.py >>"$LOG" 2>&1
  say "hq CV bitti"
fi
say "=== hq devam tamamlandı ==="
