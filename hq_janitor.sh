#!/usr/bin/env bash
# hq batch süresince disk-dolması önleyici: tamamlanan _prep case dizinlerini siler,
# en yeni 2'yi (aktif + geçiş emniyeti) korur. anchorlar belleğe yazıldığı için case scratch.
cd /d/bilsem_beyin/cfd_fea_tools || exit 1
while ! grep -q "hq devam tamamlandı" overnight_ml.log 2>/dev/null; do
  keep=$(ls -dt vehicle_runs/_batch_geo_hq/*_prep/ 2>/dev/null | head -2 | xargs -n1 basename 2>/dev/null | tr '\n' '|')
  for d in vehicle_runs/_batch_geo_hq/*_prep; do
    b=$(basename "$d")
    echo "$keep" | grep -q "${b}|" || rm -rf "$d" 2>/dev/null
  done
  sleep 900
done
echo "[$(date '+%H:%M:%S')] janitor durdu (batch bitti)" >> overnight_ml.log
