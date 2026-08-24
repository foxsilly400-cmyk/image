"""测试 ControlNet：上传参考图 + 控制生成"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
REF = r"C:\Users\28437\.openclaw\workspace\gen_out\lux_test2.png"

# 1. 上传参考图
boundary = "----cntest" + str(int(time.time()))
with open(REF, "rb") as f:
    data = f.read()
body = (f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="ref.png"\r\n'
        f"Content-Type: image/png\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
req = urllib.request.Request(BASE + "/api/upload", body,
                             {"Content-Type": f"multipart/form-data; boundary={boundary}"})
with urllib.request.urlopen(req, timeout=60) as r:
    up = json.loads(r.read())
print("upload:", up)

# 2. 带 controlnet 生成
payload = {
    "checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "loras": [],
    "vae": "内置 (checkpoint)",
    "prompt": "1girl, dress, wide hips, score_9, best quality",
    "negative": "lowres, bad anatomy, worst quality, blurry",
    "steps": 25, "cfg": 7, "sampler": "euler", "scheduler": "normal",
    "width": 1024, "height": 1536, "seed": 777, "batch": 1,
    "clip_skip": 1, "hires": False,
    "controlnet": {"enabled": True, "image": up["name"],
                   "model": "controlnet-canny-sdxl-1.0.fp16.safetensors", "strength": 0.8},
}
req = urllib.request.Request(BASE + "/api/generate", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=30) as r:
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
    if t["status"] in ("done", "error"):
        print("final:", t["status"], t.get("images"), t.get("error"))
        break
    if i % 5 == 0:
        print("waiting", t["status"])
