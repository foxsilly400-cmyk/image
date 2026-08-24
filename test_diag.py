"""诊断：生成后任务 images 是否正常返回"""
import json
import time
import urllib.request

BASE = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"

payload = {
    "checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "loras": [], "vae": "内置 (checkpoint)",
    "prompt": "1girl, score_9, best quality",
    "negative": "lowres, worst quality, blurry",
    "steps": 12, "cfg": 7, "sampler": "euler", "scheduler": "normal",
    "width": 832, "height": 1216, "seed": 5, "batch": 1,
    "clip_skip": 1,
}
req = urllib.request.Request(BASE + "/api/generate", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    resp = json.loads(r.read())
print("generate:", resp)
tid = resp["task_id"]

for i in range(60):
    time.sleep(3)
    with urllib.request.urlopen(BASE + "/api/tasks", timeout=30) as r:
        tasks = json.loads(r.read())["tasks"]
    t = next((x for x in tasks if x["id"] == tid), None)
    if not t:
        print("task not found")
        break
    print(i, t["status"], "images:", len(t.get("images", [])), "err:", t.get("error"))
    if t["status"] in ("done", "error"):
        break
