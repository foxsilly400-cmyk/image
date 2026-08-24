"""验证：生成任务 → 重启 genui → 任务是否保留"""
import json
import subprocess
import time
import urllib.request

BASE = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"

payload = {
    "checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "loras": [], "vae": "内置 (checkpoint)",
    "prompt": "1girl, score_9, best quality",
    "negative": "lowres, worst quality",
    "steps": 10, "cfg": 7, "sampler": "euler", "scheduler": "normal",
    "width": 832, "height": 1216, "seed": 777, "batch": 1, "clip_skip": 1,
}
req = urllib.request.Request(BASE + "/api/generate", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    resp = json.loads(r.read())
print("generate:", resp)
tid = resp["task_id"]

# 等完成
for i in range(40):
    time.sleep(3)
    with urllib.request.urlopen(BASE + "/api/tasks", timeout=30) as r:
        tasks = json.loads(r.read())["tasks"]
    t = next((x for x in tasks if x["id"] == tid), None)
    if t and t["status"] in ("done", "error"):
        print("before restart:", t["status"], len(t.get("images", [])))
        break

# 重启 genui（部署脚本）
subprocess.run(["python", r"C:\Users\28437\.openclaw\workspace\sshbox.py", "run",
                "bash /root/autodl-tmp/reload_genui.sh"], capture_output=True, timeout=300)
time.sleep(5)

# 重启后检查
with urllib.request.urlopen(BASE + "/api/tasks", timeout=30) as r:
    tasks = json.loads(r.read())["tasks"]
t = next((x for x in tasks if x["id"] == tid), None)
print("after restart:", t["status"] if t else "MISSING",
      len(t.get("images", [])) if t else "-",
      t.get("error") if t else "")
