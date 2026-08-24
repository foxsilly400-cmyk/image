"""Civitai 风格生成页面后端 v3：桥接 ComfyUI（队列/收藏/clip skip/VAE/ControlNet/hires fix）"""
import json
import os
import random
import subprocess
import threading
import time
import uuid
import urllib.request
from io import BytesIO

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

COMFY = "http://127.0.0.1:8188"
app = Flask(__name__, static_folder="static", template_folder="templates")

# 服务器直跑模式：直接本地操作文件，无需 SSH
ON_SERVER = os.path.exists("/root/autodl-tmp/ComfyUI")
SERVER_BASE = "/root/autodl-tmp/ComfyUI"
SSH_KEY = os.path.expanduser(r"~/.ssh/id_ed25519")
SSH_TARGET = "root@connect.westc.seetacloud.com"
SSH_PORT = "21647"

# ---------- 任务队列 ----------
TASKS = {}  # id -> {status, payload, images, error, created}
TASK_LOCK = threading.Lock()
TASK_ORDER = []  # FIFO id 列表
COND = threading.Condition()
TRIGGER_CACHE = {"data": None, "ts": 0}
# 收藏存储：放 genui 目录外（数据盘根），重新部署不影响它
FAVS_FILE = "/root/autodl-tmp/favs.json" if ON_SERVER else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "favs.json")


def load_favs():
    try:
        with open(FAVS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_favs(favs):
    with open(FAVS_FILE, "w", encoding="utf-8") as f:
        json.dump(favs[:200], f, ensure_ascii=False, indent=1)


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
    return resp


SERVER_PUBLIC = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"


@app.route("/api/favs", methods=["GET", "POST", "OPTIONS"])
def api_favs():
    """收藏：服务器端存储（多端同步）；本地模式转发到服务器"""
    if not ON_SERVER:
        try:
            if request.method == "GET":
                with urllib.request.urlopen(SERVER_PUBLIC + "/api/favs", timeout=30) as r:
                    return r.read()
            data = request.get_json(force=True)
            req = urllib.request.Request(SERVER_PUBLIC + "/api/favs",
                                         json.dumps(data).encode(),
                                         {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
    if request.method == "GET":
        return jsonify({"ok": True, "favs": load_favs()})
    data = request.get_json(force=True)
    favs = data.get("favs", [])
    save_favs(favs)
    return jsonify({"ok": True, "count": len(favs)})


def build_upscale_workflow(p):
    """对已生成图片二次采样：LoadImage → 像素放大 → VAEEncode → KSampler(低denoise) → 输出"""
    base = p.get("base", {})
    ckpt = base.get("checkpoint", "waiIllustriousSDXL_v170.safetensors")
    loras = base.get("loras", [])
    steps = int(p.get("steps", base.get("steps", 25)))
    cfg = float(p.get("cfg", base.get("cfg", 7)))
    sampler = p.get("sampler", base.get("sampler", "euler"))
    scheduler = p.get("scheduler", base.get("scheduler", "normal"))
    denoise = float(p.get("denoise", 0.4))
    scale = float(p.get("scale", 1.5))
    seed = int(p.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**31)
    w = int(base.get("width", 1024) * scale // 8 * 8)
    h = int(base.get("height", 1536) * scale // 8 * 8)

    nodes = {
        "src": {"class_type": "LoadImage", "inputs": {"image": p.get("src_image", "upscale_src.png")}},
        "scale": {"class_type": "ImageScale",
                  "inputs": {"image": ["src", 0], "upscale_method": "bicubic",
                             "width": w, "height": h, "crop": "disabled"}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
    }
    cur_model, cur_clip = ["4", 0], ["4", 1]
    for i, l in enumerate(loras):
        nid = f"5_{i}"
        nodes[nid] = {"class_type": "LoraLoader",
                      "inputs": {"model": cur_model, "clip": cur_clip,
                                 "lora_name": l["name"],
                                 "strength_model": float(l.get("weight", 0.8)),
                                 "strength_clip": float(l.get("weight", 0.8))}}
        cur_model, cur_clip = [nid, 0], [nid, 1]
    nodes["6"] = {"class_type": "CLIPTextEncode",
                  "inputs": {"clip": cur_clip, "text": base.get("prompt", "")}}
    nodes["7"] = {"class_type": "CLIPTextEncode",
                  "inputs": {"clip": cur_clip, "text": base.get("negative", "")}}
    nodes["enc"] = {"class_type": "VAEEncode",
                     "inputs": {"pixels": ["scale", 0], "vae": ["4", 2]}}
    nodes["ks"] = {"class_type": "KSampler",
                    "inputs": {"model": cur_model, "positive": ["6", 0], "negative": ["7", 0],
                               "latent_image": ["enc", 0], "seed": seed, "steps": steps,
                               "cfg": cfg, "sampler_name": sampler,
                               "scheduler": scheduler, "denoise": denoise}}
    nodes["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["4", 2]}}
    nodes["9"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["8", 0], "filename_prefix": "up"}}
    return nodes


def task_worker():
    while True:
        with COND:
            while not TASK_ORDER:
                COND.wait()
            tid = TASK_ORDER[0]
        with TASK_LOCK:
            TASKS[tid]["status"] = "running"
            payload = TASKS[tid]["payload"]
        try:
            if payload.get("mode") == "upscale":
                # 复制源图到 input 目录（供 LoadImage 使用）
                src = payload.get("src_image", "upscale_src.png")
                if ON_SERVER:
                    import shutil
                    out_f = os.path.join(SERVER_BASE, "output", src)
                    in_f = os.path.join(SERVER_BASE, "input", src)
                    if os.path.exists(out_f):
                        shutil.copy(out_f, in_f)
                wf = build_upscale_workflow(payload)
            else:
                wf = build_workflow(payload)
            resp = comfy_post("/prompt", {"prompt": wf})
            pid = resp["prompt_id"]
            # 轮询 ComfyUI 完成
            for _ in range(1200):
                time.sleep(2)
                try:
                    h = comfy_get(f"/history/{pid}")
                except Exception:
                    continue
                if pid in h:
                    break
            imgs = []
            for out in h.get(pid, {}).get("outputs", {}).values():
                for img in out.get("images", []):
                    imgs.append({"filename": img["filename"],
                                 "subfolder": img.get("subfolder", ""),
                                 "type": img["type"]})
            with TASK_LOCK:
                TASKS[tid]["images"] = imgs
                TASKS[tid]["status"] = "done"
                seed_node = wf.get("10", wf.get("ks"))
                if seed_node:
                    TASKS[tid]["seed"] = seed_node["inputs"]["seed"]
        except Exception as e:
            with TASK_LOCK:
                TASKS[tid]["status"] = "error"
                TASKS[tid]["error"] = str(e)
        with COND:
            TASK_ORDER.pop(0)
            COND.notify_all()


threading.Thread(target=task_worker, daemon=True).start()


def comfy_get(path):
    with urllib.request.urlopen(COMFY + path, timeout=30) as r:
        return json.loads(r.read())


def comfy_post(path, data):
    req = urllib.request.Request(COMFY + path, json.dumps(data).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


@app.route("/")
def index():
    return render_template("index.html")


def _obj_names(class_type, key):
    try:
        info = comfy_get(f"/object_info/{class_type}")
        return [n for n in info[class_type]["input"]["required"][key][0]]
    except Exception:
        return []


@app.route("/api/checkpoints")
def api_checkpoints():
    return jsonify({"ok": True, "items": _obj_names("CheckpointLoaderSimple", "ckpt_name")})


@app.route("/api/loras")
def api_loras():
    return jsonify({"ok": True, "items": _obj_names("LoraLoader", "lora_name")})


@app.route("/api/vaes")
def api_vaes():
    items = _obj_names("VAELoader", "vae_name")
    return jsonify({"ok": True, "items": ["内置 (checkpoint)"] + items})


@app.route("/api/controlnets")
def api_controlnets():
    return jsonify({"ok": True, "items": _obj_names("ControlNetLoader", "control_net_name")})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """上传参考图到 ComfyUI input 目录"""
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "error": "no file"})
    fname = secure_filename(f.filename)
    data = f.read()
    boundary = "----genui" + str(random.randint(10**9, 10**10))
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{fname}"\r\n'
            f"Content-Type: image/png\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(COMFY + "/upload/image", body,
                                 {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
        return jsonify({"ok": True, "name": resp.get("name", fname)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def build_workflow(p):
    ckpt = p["checkpoint"]
    loras = p.get("loras", [])
    steps = int(p.get("steps", 28))
    cfg = float(p.get("cfg", 7))
    sampler = p.get("sampler", "euler")
    scheduler = p.get("scheduler", "normal")
    width = int(p.get("width", 1024))
    height = int(p.get("height", 1536))
    seed = int(p.get("seed", -1))
    if seed < 0:
        seed = random.randint(0, 2**31)
    batch = int(p.get("batch", 1))
    clip_skip = int(p.get("clip_skip", 1))
    vae_name = p.get("vae", "内置 (checkpoint)")
    hires = p.get("hires", False)
    hires_scale = float(p.get("hires_scale", 1.5))
    hires_denoise = float(p.get("hires_denoise", 0.4))
    cn = p.get("controlnet")  # {enabled, image, model, strength} or None

    nodes = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
    }
    cur_model, cur_clip = ["4", 0], ["4", 1]

    # LoRA 链
    for i, l in enumerate(loras):
        nid = f"5_{i}"
        nodes[nid] = {"class_type": "LoraLoader",
                      "inputs": {"model": cur_model, "clip": cur_clip,
                                 "lora_name": l["name"],
                                 "strength_model": float(l.get("weight", 0.8)),
                                 "strength_clip": float(l.get("weight", 0.8))}}
        cur_model, cur_clip = [nid, 0], [nid, 1]

    # CLIP skip
    if clip_skip > 1:
        nodes["cs"] = {"class_type": "CLIPSetLastLayer",
                       "inputs": {"clip": cur_clip, "stop_at_clip_layer": -clip_skip}}
        cur_clip = ["cs", 0]

    # VAE
    vae_ref = ["4", 2]
    if vae_name != "内置 (checkpoint)":
        nodes["vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}}
        vae_ref = ["vae", 0]

    pos = {"class_type": "CLIPTextEncode", "inputs": {"clip": cur_clip, "text": p["prompt"]}}
    neg = {"class_type": "CLIPTextEncode", "inputs": {"clip": cur_clip, "text": p.get("negative", "")}}
    nodes["6"], nodes["7"] = pos, neg

    # ControlNet
    pos_ref, neg_ref = ["6", 0], ["7", 0]
    if cn and cn.get("enabled") and cn.get("image"):
        nodes["cn_img"] = {"class_type": "LoadImage", "inputs": {"image": cn["image"]}}
        nodes["cn_net"] = {"class_type": "ControlNetLoader",
                           "inputs": {"control_net_name": cn.get("model", "")}}
        nodes["cn_apply"] = {"class_type": "ControlNetApplyAdvanced",
                             "inputs": {"positive": pos_ref, "negative": neg_ref,
                                        "control_net": ["cn_net", 0], "image": ["cn_img", 0],
                                        "strength": float(cn.get("strength", 0.8)),
                                        "start_percent": 0.0, "end_percent": 1.0}}
        pos_ref, neg_ref = ["cn_apply", 0], ["cn_apply", 1]

    nodes["3"] = {"class_type": "EmptyLatentImage",
                  "inputs": {"width": width, "height": height, "batch_size": batch}}
    nodes["10"] = {"class_type": "KSampler",
                   "inputs": {"model": cur_model, "positive": pos_ref, "negative": neg_ref,
                              "latent_image": ["3", 0], "seed": seed, "steps": steps, "cfg": cfg,
                              "sampler_name": sampler, "scheduler": scheduler, "denoise": 1}}

    # Hires fix：潜空间放大 + 二次采样
    samp_ref = ["10", 0]
    if hires:
        hw = int(width * hires_scale // 8 * 8)
        hh = int(height * hires_scale // 8 * 8)
        nodes["11"] = {"class_type": "LatentUpscale",
                       "inputs": {"samples": samp_ref, "upscale_method": "nearest-exact",
                                  "width": hw, "height": hh, "crop": "disabled"}}
        nodes["12"] = {"class_type": "KSampler",
                       "inputs": {"model": cur_model, "positive": pos_ref, "negative": neg_ref,
                                  "latent_image": ["11", 0], "seed": seed + 1,
                                  "steps": int(steps * 0.8), "cfg": cfg,
                                  "sampler_name": sampler, "scheduler": scheduler,
                                  "denoise": hires_denoise}}
        samp_ref = ["12", 0]

    nodes["8"] = {"class_type": "VAEDecode", "inputs": {"samples": samp_ref, "vae": vae_ref}}
    prefix = p.get("prefix", "gen")
    nodes["9"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["8", 0], "filename_prefix": prefix}}
    return nodes


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """入队生成，立即返回 task_id"""
    p = request.get_json(force=True)
    tid = uuid.uuid4().hex[:12]
    p = {**p, "prefix": f"gen_{tid}"}
    with TASK_LOCK:
        TASKS[tid] = {"status": "queued", "payload": p, "images": [],
                      "error": None, "created": time.time()}
    with COND:
        TASK_ORDER.append(tid)
        COND.notify_all()
    return jsonify({"ok": True, "task_id": tid})


@app.route("/api/upscale", methods=["POST"])
def api_upscale():
    """对已生成图片二次采样（Hires Fix 后处理）：入队"""
    data = request.get_json(force=True)
    fn = data.get("filename", "")
    if not fn or ".." in fn or "/" in fn:
        return jsonify({"ok": False, "error": "非法文件名"})
    # 找该图所属任务的 payload 作为基础设置
    base = None
    with TASK_LOCK:
        for t in TASKS.values():
            for im in t.get("images", []):
                if im.get("filename") == fn:
                    base = dict(t["payload"])
                    break
            if base:
                break
    if base is None:
        base = {"checkpoint": "waiIllustriousSDXL_v170.safetensors",
                "loras": [], "prompt": "", "negative": "",
                "steps": 25, "cfg": 7, "sampler": "euler", "scheduler": "normal",
                "width": 1024, "height": 1536}
    base.pop("mode", None)
    payload = {"mode": "upscale", "src_image": fn,
               "base": base,
               "scale": float(data.get("scale", 1.5)),
               "denoise": float(data.get("denoise", 0.4)),
               "steps": int(data.get("steps", 25)),
               "cfg": float(data.get("cfg", 7)),
               "sampler": data.get("sampler", "euler"),
               "scheduler": data.get("scheduler", "normal"),
               "seed": int(data.get("seed", -1)),
               "prefix": "up"}
    tid = uuid.uuid4().hex[:12]
    with TASK_LOCK:
        TASKS[tid] = {"status": "queued", "payload": payload, "images": [],
                      "error": None, "created": time.time()}
    with COND:
        TASK_ORDER.append(tid)
        COND.notify_all()
    return jsonify({"ok": True, "task_id": tid})


@app.route("/api/tasks")
def api_tasks():
    with TASK_LOCK:
        items = [{"id": tid, "status": t["status"], "images": t["images"],
                  "error": t["error"], "created": t["created"],
                  "prompt": t["payload"].get("prompt", "")[:80],
                  "payload": t["payload"]}
                 for tid, t in TASKS.items()]
    items.sort(key=lambda x: x["created"], reverse=True)
    return jsonify({"ok": True, "tasks": items[:50]})


@app.route("/api/status/<pid>")
def api_status(pid):
    try:
        h = comfy_get(f"/history/{pid}")
        if pid not in h:
            return jsonify({"ok": True, "done": False})
        imgs = []
        for out in h[pid].get("outputs", {}).values():
            for img in out.get("images", []):
                imgs.append({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                             "type": img["type"]})
        return jsonify({"ok": True, "done": True, "images": imgs})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/image")
def api_image():
    fn = request.args.get("filename", "")
    sub = request.args.get("subfolder", "")
    typ = request.args.get("type", "output")
    try:
        with urllib.request.urlopen(f"{COMFY}/view?filename={fn}&subfolder={sub}&type={typ}",
                                    timeout=60) as r:
            return send_file(BytesIO(r.read()), mimetype="image/png")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def _ssh(args):
    """本地模式经 SSH 执行；服务器模式直接本地执行"""
    if ON_SERVER:
        return subprocess.run(args, capture_output=True, timeout=120)
    cmd = ["ssh", "-i", SSH_KEY, "-p", SSH_PORT, "-o", "StrictHostKeyChecking=accept-new",
           SSH_TARGET] + args
    return subprocess.run(cmd, capture_output=True, timeout=120)


@app.route("/api/delete_image", methods=["POST"])
def api_delete_image():
    """删除服务器 ComfyUI output 中的图片文件，并同步移除任务记录"""
    data = request.get_json(force=True)
    fn = data.get("filename", "")
    if not fn or ".." in fn or "/" in fn or "\\" in fn:
        return jsonify({"ok": False, "error": "非法文件名"})
    if ON_SERVER:
        p = os.path.join(SERVER_BASE, "output", fn)
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
    else:
        r = _ssh([f"/root/miniconda3/bin/python -c 'import os; os.remove(\"{SERVER_BASE}/output/{fn}\")'"])
        if r.returncode != 0:
            return jsonify({"ok": False, "error": r.stderr.decode()[:200]})
    # 同步从内存任务记录中移除（防止前端轮询重新渲染）
    with TASK_LOCK:
        for t in TASKS.values():
            t["images"] = [i for i in t.get("images", []) if i.get("filename") != fn]
    return jsonify({"ok": True})


@app.route("/api/import", methods=["POST"])
def api_import():
    """导入 safetensors：收文件 → scp 到服务器对应目录"""
    f = request.files.get("file")
    kind = request.form.get("kind", "lora")
    if not f:
        return jsonify({"ok": False, "error": "no file"})
    fname = secure_filename(f.filename)
    if not fname.endswith(".safetensors"):
        return jsonify({"ok": False, "error": "只支持 .safetensors"})
    dest_dir = "checkpoints" if kind == "checkpoint" else "loras"
    local_tmp = os.path.join("upload_tmp", fname)
    os.makedirs("upload_tmp", exist_ok=True)
    total = 0
    with open(local_tmp, "wb") as out:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            total += len(chunk)
    dest = f"/root/autodl-tmp/ComfyUI/models/{dest_dir}/{fname}"
    key = os.path.expanduser(r"~/.ssh/id_ed25519")
    cmd = ["scp", "-P", "21647", "-i", key, "-o", "StrictHostKeyChecking=accept-new",
           local_tmp, f"root@connect.westc.seetacloud.com:{dest}"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=7200)
        if r.returncode != 0:
            return jsonify({"ok": False, "error": r.stderr.decode()[:300]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
    finally:
        try:
            os.remove(local_tmp)
        except Exception:
            pass
    return jsonify({"ok": True, "name": fname, "size_mb": round(total / 1e6, 1),
                    "dest": dest_dir})


@app.route("/api/triggers")
def api_triggers():
    """读取服务器模型 metadata 中的触发词（缓存 120s）"""
    now = time.time()
    if TRIGGER_CACHE["data"] and now - TRIGGER_CACHE["ts"] < 120:
        return jsonify({"ok": True, **TRIGGER_CACHE["data"]})
    if ON_SERVER:
        r = subprocess.run(["/root/miniconda3/bin/python", "/root/autodl-tmp/read_triggers.py"],
                           capture_output=True, timeout=120)
    else:
        r = _ssh(["/root/miniconda3/bin/python /root/autodl-tmp/read_triggers.py"])
    try:
        if r.returncode != 0:
            return jsonify({"ok": False, "error": r.stderr.decode()[:200]})
        data = json.loads(r.stdout.decode())
        TRIGGER_CACHE.update({"data": data, "ts": now})
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("GENUI_PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
