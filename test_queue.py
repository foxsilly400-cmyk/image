"""测试队列：连发 2 个任务"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"

def gen(prompt, seed):
    payload = {
        "checkpoint": "waiIllustriousSDXL_v170.safetensors",
        "loras": [{"name": "blackwhiplash(bwl)-guy90-Illust-Lorav3.safetensors", "weight": 0.8}],
        "vae": "内置 (checkpoint)",
        "prompt": prompt,
        "negative": "lowres, bad anatomy, bad hands, text, worst quality, low quality, blurry",
        "steps": 20, "cfg": 7, "sampler": "euler", "scheduler": "normal",
        "width": 832, "height": 1216, "seed": seed, "batch": 1,
        "clip_skip": 1, "hires": False, "controlnet": None,
    }
    req = urllib.request.Request(BASE + "/api/generate", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

r1 = gen("1girl, dress, wide hips, score_9", 100)
r2 = gen("1boy, penis, close-up, score_9", 200)
print("task1:", r1)
print("task2:", r2)

for i in range(30):
    time.sleep(3)
    with urllib.request.urlopen(BASE + "/api/tasks", timeout=30) as r:
        tasks = json.loads(r.read())["tasks"]
    st = [(t["id"][:8], t["status"]) for t in tasks]
    print(i, st)
    if all(t["status"] in ("done", "error") for t in tasks):
        break
