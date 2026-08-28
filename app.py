"""Civitai 风格生成页面后端 v3：桥接 ComfyUI（队列/收藏/clip skip/VAE/ControlNet/hires fix）"""
import json
import os
import random
import re
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

# ---------- 访问密码（防外人用工作台）----------
# ON_SERVER 时读 /root/autodl-tmp/genui_pass.txt，存在且非空则启用登录验证
# 本地模式不启用；改密码 = 改服务器上该文件内容后重启
def _load_auth_password():
    # 环境变量优先（测试/部署用），其次服务器密码文件；本地模式无文件则不启用
    env = os.environ.get("GENUI_PASSWORD", "")
    if env:
        return env.strip()
    if not os.path.exists("/root/autodl-tmp/ComfyUI"):
        return ""
    try:
        with open("/root/autodl-tmp/genui_pass.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

AUTH_PASSWORD = _load_auth_password()
AUTH_COOKIE = "genui_auth"

@app.before_request
def auth_gate():
    if not AUTH_PASSWORD:
        return None
    if request.path == "/api/login" or request.path.startswith("/static") or request.method == "OPTIONS":
        return None
    if request.cookies.get(AUTH_COOKIE) == AUTH_PASSWORD:
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return render_template("login.html"), 401

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    if data.get("password") == AUTH_PASSWORD:
        resp = jsonify({"ok": True})
        resp.set_cookie(AUTH_COOKIE, AUTH_PASSWORD, max_age=30 * 24 * 3600,
                        httponly=True, samesite="Lax")
        return resp
    return jsonify({"ok": False, "error": "wrong password"}), 401

# 服务器直跑模式：直接本地操作文件，无需 SSH
ON_SERVER = os.path.exists("/root/autodl-tmp/ComfyUI")
SERVER_BASE = "/root/autodl-tmp/ComfyUI"
SSH_KEY = os.path.expanduser(r"~/.ssh/id_ed25519")
SSH_TARGET = "root@connect.westc.seetacloud.com"
SSH_PORT = "36208"

# ---------- 任务队列 ----------
TASKS = {}  # id -> {status, payload, images, error, created}
TASK_LOCK = threading.Lock()
TASK_ORDER = []  # FIFO id 列表
COND = threading.Condition()
TRIGGER_CACHE = {"data": None, "ts": 0}
# 收藏存储：放 genui 目录外（数据盘根），重新部署不影响它
FAVS_FILE = "/root/autodl-tmp/favs.json" if ON_SERVER else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "favs.json")
# 任务记录持久化：重启/部署不丢历史任务
TASKS_FILE = "/root/autodl-tmp/tasks.json" if ON_SERVER else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tasks.json")


def save_tasks():
    try:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump({"order": TASK_ORDER, "tasks": TASKS}, f, ensure_ascii=False)
    except Exception:
        pass


def load_tasks():
    global TASK_ORDER
    try:
        with open(TASKS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        TASK_ORDER = [i for i in d.get("order", []) if i in d.get("tasks", {})]
        for tid, t in d.get("tasks", {}).items():
            if t.get("status") in ("queued", "running"):
                t["status"] = "error"
                t["error"] = "服务重启，任务中断"
            TASKS[tid] = t
        TASK_ORDER = [i for i in TASK_ORDER if TASKS[i]["status"] not in ("queued", "running")]
    except Exception:
        pass


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


SERVER_PUBLIC = "https://u1139344-b01e-c23b1b75.westc.seetacloud.com:8443"


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


NEG_ENHANCE = [
    "(text:1.5)", "(watermark:1.5)", "(signature:1.5)", "(logo:1.5)",
    "(letter:1.4)", "(caption:1.4)", "(subtitles:1.4)", "(ui:1.4)",
    "(border:1.4)", "(frame:1.4)", "(speech bubble:1.4)", "(dialogue:1.4)",
    "(sound effect:1.4)", "(sfx:1.4)", "(japanese text:1.4)", "(english text:1.4)",
    "(typography:1.4)", "(kana:1.4)", "(kanji:1.4)", "(katakana:1.4)", "(hiragana:1.4)",
    "(words:1.3)", "(writing:1.3)", "(font:1.3)", "(label:1.3)", "(slogan:1.3)",
    "(title:1.3)", "(header:1.3)", "(footer:1.3)", "(menu:1.3)", "(icons:1.3)",
    "(number:1.3)", "(timestamp:1.3)", "(date:1.3)", "(url:1.3)", "(email:1.3)",
    "(barcode:1.3)", "(qr code:1.3)",
]


BRACKET_PAT = re.compile(r"\(+[^()]*?\)+")


def convert_weight_brackets(text):
    """把 (((tag))) 括号圈数转换为 ComfyUI 权重语法 (tag:1.05^n)。
    正面词：圈数越多权重越高；负面词同样（负面里权重高 = 更强抑制）。
    已带 : 权重语法的括号组跳过。倍率用 1.05 而非 1.1：
    角色 tag 权重过高（1.331）会拉爆色彩饱和度和画面密度（实测教训）。"""
    if not text:
        return text

    def repl(m):
        s = m.group(0)
        inner = s.strip("()")
        if not inner or ":" in inner:
            return s
        n = min(len(s) - len(s.lstrip("(")), len(s) - len(s.rstrip(")")))
        w = round(1.05 ** n, 3)
        return "(%s:%.3f)" % (inner.strip(), w)

    return BRACKET_PAT.sub(repl, text)


TAGS_CACHE = None
TAGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tags.csv")


def load_tags():
    global TAGS_CACHE
    if TAGS_CACHE is not None:
        return TAGS_CACHE
    tags = []
    if os.path.exists(TAGS_PATH):
        import csv as _csv
        with open(TAGS_PATH, encoding="utf-8") as f:
            rd = _csv.reader(f)
            next(rd, None)
            for row in rd:
                if len(row) >= 2 and row[1].strip():
                    tags.append(row[1].strip())
    TAGS_CACHE = tags
    return tags


@app.route("/api/tag_suggest")
def api_tag_suggest():
    q = request.args.get("q", "").strip().lower()
    tags = load_tags()
    if not q:
        return jsonify({"ok": True, "items": []})
    pref = [t for t in tags if t.lower().startswith(q)][:12]
    sub = [t for t in tags if q in t.lower() and t not in pref][:12]
    return jsonify({"ok": True, "items": pref + sub})


NL_MODEL = None
NL_TOKENIZER = None


def _load_nl():
    global NL_MODEL, NL_TOKENIZER
    if NL_MODEL is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "Qwen2.5-1.5B-Instruct")
        NL_TOKENIZER = AutoTokenizer.from_pretrained(p)
        NL_MODEL = AutoModelForCausalLM.from_pretrained(p, torch_dtype="auto", device_map="auto")
    return NL_MODEL, NL_TOKENIZER


@app.route("/api/nl2tags", methods=["POST"])
def api_nl2tags():
    d = request.get_json(force=True)
    text = (d.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"})
    try:
        model, tok = _load_nl()
        sys_prompt = ("把用户的画面描述转换为逗号分隔的英文 danbooru 标签列表。"
                      "对必须出现的核心画面要素（主体人物、显著外貌特征、核心表情/动作/服装）用双重括号包裹，"
                      "例如 ((1girl))、((green hair))、((smile))、((dress))；"
                      "背景氛围等次要要素不加括号。只输出标签列表本身，不要任何解释。"
                      "例：'绿发女孩穿着连衣裙微笑' -> ((1girl)), ((green hair)), dress, ((smile))")
        prompt_text = tok.apply_chat_template(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}],
            tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt_text, return_tensors="pt")
        if hasattr(model, "device"):
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
        out = model.generate(**inputs, max_new_tokens=256, do_sample=False)
        resp = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return jsonify({"ok": True, "tags": resp.strip()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def enhance_negative(neg: str) -> str:
    """加强负面词：保留用户输入，追加带权重的文字/水印屏蔽词库（已在负面词中的项不重复追加）。"""
    parts = [neg.strip()] if neg and neg.strip() else []
    for item in NEG_ENHANCE:
        tag = item.split(":")[0].lstrip("(")
        if tag not in neg:
            parts.append(item)
    return ", ".join(parts)


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
                  "inputs": {"clip": cur_clip, "text": enhance_negative(base.get("negative", ""))}}
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
            save_tasks()
        with COND:
            TASK_ORDER.pop(0)
            COND.notify_all()
        save_tasks()


threading.Thread(target=task_worker, daemon=True).start()
load_tasks()


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
    src_image = p.get("src_image")
    denoise = float(p.get("denoise", 0.5))

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
    neg = {"class_type": "CLIPTextEncode", "inputs": {"clip": cur_clip, "text": enhance_negative(p.get("negative", ""))}}
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
    latent_ref, ks_denoise = ["3", 0], 1.0
    # img2img：参考图编码为 latent，用 denoise 控制重绘幅度
    if src_image:
        nodes["src"] = {"class_type": "LoadImage", "inputs": {"image": src_image}}
        nodes["enc"] = {"class_type": "VAEEncode",
                         "inputs": {"pixels": ["src", 0], "vae": vae_ref}}
        latent_ref, ks_denoise = ["enc", 0], denoise
    nodes["10"] = {"class_type": "KSampler",
                   "inputs": {"model": cur_model, "positive": pos_ref, "negative": neg_ref,
                              "latent_image": latent_ref, "seed": seed, "steps": steps, "cfg": cfg,
                              "sampler_name": sampler, "scheduler": scheduler, "denoise": ks_denoise}}

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
    save_tasks()
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
    save_tasks()
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
    save_tasks()
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
    if ON_SERVER:
        dest = os.path.join(SERVER_BASE, dest_dir, fname)
        try:
            os.replace(local_tmp, dest)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})
        return jsonify({"ok": True, "name": fname, "size_mb": round(total / 1e6, 1),
                        "dest": dest_dir})
    dest = f"/root/autodl-tmp/ComfyUI/models/{dest_dir}/{fname}"
    key = os.path.expanduser(r"~/.ssh/id_ed25519")
    cmd = ["scp", "-P", SSH_PORT, "-i", key, "-o", "StrictHostKeyChecking=accept-new",
           local_tmp, f"{SSH_TARGET}:{dest}"]
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
