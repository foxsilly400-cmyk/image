"""测试 genui 后端：WAI + 新训 smegma LoRA 生成"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"

payload = {
    "checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "loras": [
        {"name": "blackwhiplash(bwl)-guy90-Illust-Lorav3.safetensors", "weight": 0.8},
        {"name": "smegma_illustrious.safetensors", "weight": 0.9},
    ],
    "prompt": "smegma, (tenkyuu chimata,petite,),1girl,dress, (pote (ptkan) ),blackwhiplash,blaash,wide hips, score_9, score_8_up, best quality, absurdres",
    "negative": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
    "steps": 28,
    "cfg": 7,
    "sampler": "euler",
    "scheduler": "normal",
    "width": 1024,
    "height": 1536,
    "seed": 42,
    "batch": 1,
}

req = urllib.request.Request(BASE + "/api/generate", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    resp = json.loads(r.read())
print("generate:", resp)
pid = resp["prompt_id"]

for i in range(200):
    time.sleep(2)
    with urllib.request.urlopen(f"{BASE}/api/status/{pid}", timeout=30) as r:
        st = json.loads(r.read())
    if st.get("done"):
        print("done:", st["images"])
        break
    if i % 15 == 0:
        print(f"waiting... {i*2}s")
else:
    print("timeout")
