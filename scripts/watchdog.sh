#!/bin/bash
# 常驻守护：每 120s 检查 ComfyUI(8188) / genui(6006)，挂掉自动拉起。
# 由 restore_after_boot.sh 启动；日志 /root/autodl-tmp/watchdog.log
PY=/root/miniconda3/bin/python
CURL=/usr/bin/curl
LOG=/root/autodl-tmp/watchdog.log
while true; do
  C=$($CURL -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8188/system_stats 2>/dev/null)
  G=$($CURL -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:6006/ 2>/dev/null)
  if [ "$C" != "200" ]; then
    echo "$(date '+%F %T') comfy down (code=$C), restart" >> $LOG
    setsid bash /root/autodl-tmp/start_comfy.sh > /root/autodl-tmp/comfy.log 2>&1 < /dev/null &
  fi
  if [ "$G" != "200" ]; then
    echo "$(date '+%F %T') genui down (code=$G), restart" >> $LOG
    (cd /root/autodl-tmp/genui && setsid env GENUI_PORT=6006 "$PY" app.py >> /root/autodl-tmp/genui.log 2>&1 < /dev/null &)
  fi
  sleep 120
done
