"""公网端到端验证：登录 -> 上传测试图 -> /api/automask(body) -> 取回遮罩并校验"""
import io
import json
import os
import ssl
import urllib.request

BASE = "https://u1139344-8e64-c621ed69.westc.seetacloud.com:8443"
PASSWORD = "ersansan2333"
SRC = r"C:\Users\28437\.openclaw\workspace\db_smegma\imgs\11318591_358861ce796061175123605db7243655.jpg"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def req(path, data=None, headers=None, timeout=60):
    r = urllib.request.Request(BASE + path, data=data, headers=headers or {})
    return urllib.request.urlopen(r, timeout=timeout, context=CTX)


# 1. 登录
body = json.dumps({"password": PASSWORD}).encode()
with req("/api/login", body, {"Content-Type": "application/json"}) as r:
    cookie = r.headers.get("Set-Cookie", "").split(";")[0]
    print("login:", r.status, "cookie:", cookie[:20], "...")
assert cookie

H = {"Cookie": cookie}

# 2. 上传测试图
with open(SRC, "rb") as f:
    data = f.read()
boundary = "----genui_e2e_test"
body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"e2e_src.jpg\"\r\n"
        f"Content-Type: image/jpeg\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
with req("/api/upload", body, {"Cookie": cookie, "Content-Type": f"multipart/form-data; boundary={boundary}"}) as r:
    j = json.loads(r.read())
print("upload:", j)
assert j.get("ok") and j.get("name")
src_name = j["name"]

# 3. automask
for mode in ("body", "all_but_face"):
    body = json.dumps({"src_image": src_name, "mode": mode}).encode()
    with req("/api/automask", body, {"Cookie": cookie, "Content-Type": "application/json"}) as r:
        j = json.loads(r.read())
    print("automask", mode, "->", j)
    assert j.get("ok") and j.get("mask_image")
    # 4. 取回遮罩
    with req("/api/image?filename=" + j["mask_image"] + "&type=input", headers=H) as r:
        png = r.read()
    print("  mask bytes:", len(png))
    assert len(png) > 1000
    # 本地校验 alpha 结构
    import cv2
    import numpy as np
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert arr.shape[2] == 4, "mask 必须是 RGBA"
    a = arr[:, :, 3]
    h, w = arr.shape[:2]
    for label, r0, r1 in (("上1/3", 0, h // 3), ("中1/3", h // 3, 2 * h // 3), ("下1/3", 2 * h // 3, h)):
        print(f"  {label}: 重绘占比 {100.0 * (a[r0:r1, :] > 128).mean():.1f}%")

print("E2E OK")
