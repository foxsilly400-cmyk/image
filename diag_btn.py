import json, urllib.request, http.cookiejar

# 1. 服务器 app.js 的按钮代码
js = open('/root/autodl-tmp/genui/static/app.js', encoding='utf-8', errors='ignore').read()
print("del-btn count:", js.count('del-btn'))
print("fav-btn count:", js.count('fav-btn'))
print("bar.append:", 'bar.append(fav, up, del, dl)' in js)
print("createDoneCard:", 'function createDoneCard' in js)
# 打印 createDoneCard 的 bar 部分
i = js.find('const bar = document.createElement("div");')
print(js[i:i+200])

# 2. 任务状态
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
post("/api/login", {"password": PWD})
tasks = get("/api/tasks")["tasks"]
from collections import Counter
print("status counts:", Counter(t["status"] for t in tasks))
for t in tasks[:10]:
    print(t["id"], t["status"], "images:", len(t.get("images", [])), "|", (t.get("prompt") or "")[:30])
