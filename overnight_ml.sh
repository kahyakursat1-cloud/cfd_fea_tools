#!/usr/bin/env bash
# Gece ML orkestratörü: TMR α=8 koşusu bitince (laptop boşalınca) izole yüksek-kalite
# (hassas, duvar-çözünür) batch_learn koşar → sonra hq DB'yi LOOCV ile değerlendirir.
# Mevcut hizli-kalite DB'ye DOKUNMAZ (BATCH_TAG=hq → ayrı bellek/dizin).
set -u
cd /d/bilsem_beyin/cfd_fea_tools || exit 1
export PYTHONUTF8=1
LOG=overnight_ml.log
say(){ echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

say "=== gece ML orkestratörü başladı ==="

# 1) TMR koşusunun bitmesini bekle: verdict yazıldı VEYA foamRun 3 ardışık kontrolde yok
absent=0
for i in $(seq 1 480); do            # 480×60s = 8 saat tavan
  if [ -f tmr_gci_verdict_a8.json ]; then say "TMR verdict yazıldı → laptop boş"; break; fi
  if wsl -e bash -lc 'pgrep foamRun >/dev/null' 2>/dev/null; then absent=0; else absent=$((absent+1)); fi
  if [ "$absent" -ge 3 ]; then say "foamRun 3 kontrolde yok → laptop boş (verdict beklemeden devam)"; break; fi
  sleep 60
done

# 2) Süre bütçesi: bugün 07:30'a kadar, en çok 300dk (laptop'ı gündüze taşımadan)
now=$(date +%s); stop=$(date -d "07:30" +%s 2>/dev/null || date +%s)
[ "$stop" -le "$now" ] && stop=$((now+1800))    # 07:30 geçtiyse en az 30dk
budget=$(( (stop-now)/60 )); [ "$budget" -gt 300 ] && budget=300
say "hassas batch başlıyor: budget=${budget}dk (BATCH_TAG=hq, cap=3)"

# 3) İzole yüksek-kalite veri üretimi (duvar-çözünür hassas etiketler)
BATCH_TAG=hq BATCH_MAX_MIN=$budget python experiments/batch_learn.py 3 3 hassas >>"$LOG" 2>&1
say "hassas batch bitti (exit $?)"

# 4) hq DB'yi (seed + hq anchors) LOOCV ile değerlendir → surrogate_cv_hq.json
if [ -f auto_pilot_memory_hq.jsonl ]; then
  n=$(wc -l < auto_pilot_memory_hq.jsonl)
  say "hq bellek: $n kayıt → LOOCV değerlendirmesi"
  CV_MEMORY=auto_pilot_memory_hq.jsonl CV_TAG=hq python experiments/surrogate_cv.py >>"$LOG" 2>&1
  say "hq CV bitti (surrogate_cv_hq.json)"
else
  say "hq bellek dosyası yok — batch hiç anchor üretmemiş olabilir (log'a bak)"
fi
say "=== gece ML orkestratörü tamamlandı ==="
