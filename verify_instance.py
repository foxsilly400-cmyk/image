import json, urllib.request, http.cookiejar

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

# 测试 /api/instance（用当前实例信息）
text = "ssh -p 25562 root@connect.westc.seetacloud.com b1j+7G45IlEm https://u1139344-8e64-c621ed69.westc.seetacloud.com:8443"
r = post("/api/instance", {"text": text})
print("instance resp:", json.dumps(r, ensure_ascii=False))

# 错误格式
r2 = post("/api/instance", {"text": "随便写点什么"})
print("bad format:", json.dumps(r2, ensure_ascii=False)[:120])

# 确认保存的文件
import os
p = "/root/autodl-tmp/instance.json"
if os.path.exists(p):
    print("file:", open(p).read()[:200])
