"""测试 RAIZENGAX 画风 LoRA"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"

payload = {
    "checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "loras": [{"name": "raizengax_style.safetensors", "weight": 0.8}],
    "vae": "内置 (checkpoint)",
    "prompt": "raizengax, 1girl, dress, wide hips, score_9, best quality, absurdres",
    "negative": "lowres, bad anatomy, bad hands, text, worst quality, low quality, blurry",
    "steps": 30, "cfg": 7, "sampler": "euler", "scheduler": "normal",
    "width": 1024, "height": 1536, "seed": 888, "batch": 2,
    "clip_skip": 1, "hires": False,
}
req = urllib.request.Request(BASE + "/api/generate", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=30) as r:
    resp = json.loads(r.read())
print("generate:", resp)
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
