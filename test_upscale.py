"""测试二次采样（upscale）：对已生成图片做 Hires Fix 后处理"""
import json
import time
import urllib.request

BASE = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"

# 用之前生成的测试图
fn = "gen_69f56335ce06_00001_.png"
payload = {"filename": fn, "scale": 1.5, "denoise": 0.4}
req = urllib.request.Request(BASE + "/api/upscale", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    resp = json.loads(r.read())
print("upscale:", resp)
tid = resp["task_id"]

for i in range(90):
    time.sleep(3)
    with urllib.request.urlopen(BASE + "/api/tasks", timeout=30) as r:
        tasks = json.loads(r.read())["tasks"]
    t = next((x for x in tasks if x["id"] == tid), None)
    if not t:
        print("not found")
        break
    if t["status"] in ("done", "error"):
        print("final:", t["status"], t.get("images"), t.get("error"))
        break
