"""测试新功能：clip skip 2 + hires fix + VAE"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"

payload = {
    "checkpoint": "waiIllustriousSDXL_v170.safetensors",
    "loras": [{"name": "blackwhiplash(bwl)-guy90-Illust-Lorav3.safetensors", "weight": 0.8}],
    "vae": "内置 (checkpoint)",
    "prompt": "(tenkyuu chimata,petite,),1girl,dress, (pote (ptkan) ),blackwhiplash,blaash,wide hips, score_9, best quality",
    "negative": "lowres, bad anatomy, bad hands, text, worst quality, low quality, blurry",
    "steps": 45,
    "cfg": 6.5,
    "sampler": "dpmpp_2m_sde",
    "scheduler": "karras",
    "width": 1024,
    "height": 1536,
    "seed": 123,
    "batch": 1,
    "clip_skip": 2,
    "hires": True,
    "hires_scale": 1.5,
    "hires_denoise": 0.4,
    "controlnet": None,
}

req = urllib.request.Request(BASE + "/api/generate", json.dumps(payload).encode(),
                             {"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    resp = json.loads(r.read())
print("generate:", resp)
pid = resp["prompt_id"]

for i in range(300):
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
