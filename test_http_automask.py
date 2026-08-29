"""本地 HTTP 验证 /api/automask 接口（临时端口 8011）"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
INPUT = os.path.join(BASE, "ComfyUI", "input")
os.makedirs(INPUT, exist_ok=True)
shutil.copy(r"C:\Users\28437\.openclaw\workspace\db_smegma\imgs\11318591_358861ce796061175123605db7243655.jpg",
            os.path.join(INPUT, "http_src.jpg"))

env = dict(os.environ, GENUI_PORT="8011")
proc = subprocess.Popen([sys.executable, os.path.join(BASE, "app.py")],
                        cwd=BASE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(3)
    for mode in ("body", "all_but_face"):
        req = urllib.request.Request("http://127.0.0.1:8011/api/automask",
                                     json.dumps({"src_image": "http_src.jpg", "mode": mode}).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read())
        print(mode, "->", j)
        assert j.get("ok") and j.get("mask_image"), "接口失败"
        p = os.path.join(INPUT, j["mask_image"])
        assert os.path.exists(p), "mask 文件不存在"
        os.remove(p)
    # 缺参容错
    req = urllib.request.Request("http://127.0.0.1:8011/api/automask",
                                 json.dumps({}).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read())
    print("empty ->", j)
    assert not j.get("ok")
    print("HTTP OK")
finally:
    proc.terminate()
    try:
        os.remove(os.path.join(INPUT, "http_src.jpg"))
    except OSError:
        pass
