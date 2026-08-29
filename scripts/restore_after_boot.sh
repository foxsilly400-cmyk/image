#!/bin/bash
# 实例重启/切换后恢复：拉起 ComfyUI(8188) + genui(6006) + watchdog 守护。
# 幂等，可重复执行。换实例后 SSH 跑一次即可。
# 用法: bash /root/autodl-tmp/restore_after_boot.sh
set -u
PY=/root/miniconda3/bin/python
if [ ! -x "$PY" ]; then
  echo "[FATAL] $PY 不存在"
  echo "系统盘环境丢失（新建实例且未用保存镜像时会出现）。"
  echo "需先恢复 miniconda 环境再重跑本脚本。"
  exit 2
fi
export PATH=/root/miniconda3/bin:$PATH

echo "[1/5] 清理残留进程"
pkill -f 'main.py --listen 0.0.0.0 --port 8188' 2>/dev/null
pkill -f 'python app.py' 2>/dev/null
pkill -f 'watchdog.sh' 2>/dev/null
sleep 2

echo "[2/5] 启动 ComfyUI"
setsid bash /root/autodl-tmp/start_comfy.sh > /root/autodl-tmp/comfy.log 2>&1 < /dev/null &

echo "[3/5] 启动 genui (6006)"
cd /root/autodl-tmp/genui
setsid env GENUI_PORT=6006 "$PY" app.py >> /root/autodl-tmp/genui.log 2>&1 < /dev/null &

echo "[4/5] 启动 watchdog 守护（每 120s 检查，挂了自动拉起）"
setsid bash /root/autodl-tmp/watchdog.sh > /dev/null 2>&1 < /dev/null &

echo "[5/5] 等待就绪 (最长 120s)"
for i in $(seq 1 24); do
  sleep 5
  C=$(/usr/bin/curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8188/system_stats)
  G=$(/usr/bin/curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:6006/)
  echo "  [$i] comfy=$C genui=$G"
  # 非 000（连不上）即视为就绪；genui 的 401 是登录拦截，属正常存活
  if [ "$C" != "000" ] && [ "$G" != "000" ]; then
    echo "[OK] ComfyUI + genui + watchdog 均就绪"
    exit 0
  fi
done
echo "[WARN] 120s 未就绪: comfy=$C genui=$G，看 comfy.log / genui.log"
exit 1
