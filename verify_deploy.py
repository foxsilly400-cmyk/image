import glob, json, urllib.request, http.cookiejar, time

# 1. 代码检查
src = open('/root/autodl-tmp/genui/app.py', encoding='utf-8', errors='ignore').read()
print("worker threads:", src.count('Thread(target=task_worker'))
print("load_tasks call:", src.count('load_tasks()') - 1)
print("has WebSocketApp:", 'WebSocketApp' in src)
appjs = open('/root/autodl-tmp/genui/static/app.js', encoding='utf-8', errors='ignore').read()
print("app.js createDoneCard loop:", 'for (let idx = 0; idx < items.length; idx++)' in appjs)
print("app.js insert sort:", 'gal.prepend' in appjs)
html = open('/root/autodl-tmp/genui/templates/index.html', encoding='utf-8', errors='ignore').read()
print("html versioned:", 'v=20260829' in html)

# 2. 日志
log = open('/root/autodl-tmp/genui.log', encoding='utf-8', errors='ignore').read()
ws = [l for l in log.splitlines() if '[ws]' in l]
wk = [l for l in log.splitlines() if '[worker]' in l]
print("ws:", ws[-3:])
print("worker:", wk[-3:])

# 3. 提交任务验证（进度 + 单次提交 + 完成）
BASE = "https://u1139344-8e64-c621ed69.westc.seetacloud.com:8443"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def post(path, data):
    req = urllib.request.Request(BASE + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
    with opener.open(req, timeout=30) as r:
        return json.loads(r.read())
def get(path):
    with opener.open(BASE + path, timeout=15) as r:
        return json.loads(r.read())
PWD = open("/root/autodl-tmp/genui_pass.txt").read().strip()
print("login:", post("/api/login", {"password": PWD}))

payload = {"checkpoint": "waiIllustriousSDXL_v170.safetensors",
           "loras": [{"name": "fnf_sarvente_illustriousXL.safetensors", "weight": 1.0}],
           "prompt": "1girl, sarvente, colored skin, nun, final deployment verify", "negative": "",
           "steps": 40, "cfg": 6, "sampler": "euler", "scheduler": "normal",
           "width": 1024, "height": 1536, "seed": 990001, "batch": 1}
r = post("/api/generate", payload)
tid = r["task_id"]
print("submit:", r)
t0 = time.time()
last = -1
while True:
    time.sleep(0.5)
    gt = next((x for x in get("/api/tasks")["tasks"] if x["id"] == tid), None)
    if not gt:
        print("gone"); break
    p = gt.get("progress", 0)
    k = int(p * 20)
    if k != last:
        last = k
        print(f"  +{time.time()-t0:.1f}s {gt['status']} stage={gt.get('stage')} progress={p}")
    if gt["status"] in ("done", "error", "cancelled"):
        print("final:", gt["status"], "images:", len(gt.get("images", [])), "err:", (gt.get("error") or "")[:80])
        break
    if time.time() - t0 > 90:
        print("timeout", gt["status"], gt.get("stage"))
        break
