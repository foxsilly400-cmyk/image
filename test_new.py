"""新实例验证：ranbow LoRA 生成"""
import json
import time
import urllib.request

BASE = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"

payload = {
    "checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "loras": [{"name": "ranbow_char.safetensors", "weight": 1.0}],
    "vae": "内置 (checkpoint)",
    "prompt": "ranbow, 1girl, purple hair, twintails, fake animal ears, white dress, solo, score_9, best quality",
    "negative": "lowres, bad anatomy, bad hands, text, worst quality, low quality, blurry",
    "steps": 28, "cfg": 7, "sampler": "euler", "scheduler": "normal",
    "width": 1024, "height": 1536, "seed": 99, "batch": 1,
    "clip_skip": 1, "hires": False,
}
req = urllib.request.Request(BASE + "/api/generate", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
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
