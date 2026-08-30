#!/root/miniconda3/bin/python
"""扫描 ComfyUI 模型目录，读取 safetensors metadata 中的触发词

优先级：
0. 手动配置（/root/autodl-tmp/lora_triggers.json，{文件名: [触发词列表]}）——完整保留，不过滤通用词
1. 明确字段: modelspec.trigger_phrase / ss_trigger_word / trigger_word
2. ss_tag_frequency 的 character/artist/copyright 类（基本就是触发词）
3. ss_tag_frequency 的 dataset/general 类（过滤通用词后取最高频）
4. ss_output_name（kohya 输出名，通常含触发词）
5. 文件名兜底
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "/root/miniconda3/lib/python3.12/site-packages")

from safetensors import safe_open

BASE = "/root/autodl-tmp/ComfyUI/models"
MANUAL_FILE = "/root/autodl-tmp/lora_triggers.json"
result = {"checkpoints": {}, "loras": {}}

# 通用 danbooru 标签黑名单（不可能是触发词；手动配置不过滤）
COMMON_TAGS = {
    "1girl", "1boy", "1other", "1male", "solo", "multiple girls", "multiple boys",
    "multiple people", "looking at viewer", "smile", "blush", "open mouth",
    "short hair", "long hair", "bangs", "ahoge", "twintails", "ponytail", "hair bun",
    "red eyes", "blue eyes", "green eyes", "yellow eyes", "purple eyes", "brown eyes",
    "black hair", "white hair", "blonde hair", "brown hair", "purple hair",
    "blue hair", "green hair", "red hair", "pink hair", "grey hair",
    "simple background", "white background", "black background", "grey background",
    "colored background", "solid background", "upper body", "close-up", "cowboy shot",
    "full body", "standing", "sitting", "lying", "kneeling", "crouching",
    "breasts", "medium breasts", "large breasts", "small breasts", "navel",
    "nipples", "pussy", "ass", "anus", "nude", "uncensored", "censored",
    "score_9", "score_8_up", "score_7_up", "best quality", "amazing quality",
    "masterpiece", "absurdres", "highres", "very aesthetic", "normal quality",
    "low quality", "worst quality", "watermark", "signature", "text", "username",
    "artist name", "commentary request", "translation request",
}


def load_manual():
    try:
        with open(MANUAL_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def clean_words(words):
    out = []
    for w in words:
        w = w.strip().strip(",").strip()
        if not w or w.lower() in COMMON_TAGS:
            continue
        if w not in out:
            out.append(w)
    return out


def extract_words(path, fname):
    words = []
    try:
        with safe_open(path, framework="pt") as f:
            meta = f.metadata() or {}
    except Exception:
        meta = {}

    # 1. 明确字段
    for k in ("modelspec.trigger_phrase", "ss_trigger_word", "trigger_word"):
        if meta.get(k):
            words.extend([w.strip() for w in str(meta[k]).split(",") if w.strip()])

    # 2/3. tag_frequency（类名可能是 character/artist/copyright，也可能是 dataset/general/文件夹名如 4_haniwa）
    tf = meta.get("ss_tag_frequency")
    if tf:
        try:
            data = json.loads(tf)
            for cls in ("character", "artist", "copyright"):
                if cls in data:
                    top = sorted(data[cls].items(), key=lambda x: -x[1])[:3]
                    words.extend(w for w, _ in top)
            # 其余所有类（dataset/general/数字前缀文件夹名）合并后取最高频，供黑名单过滤
            rest = []
            for cls, items in data.items():
                if cls in ("character", "artist", "copyright"):
                    continue
                rest.extend(sorted(items.items(), key=lambda x: -x[1])[:3])
            rest.sort(key=lambda x: -x[1])
            words.extend(w for w, _ in rest[:4])
        except Exception:
            pass

    words = clean_words(words)

    # 4. output_name（仅在无其他候选时兜底，避免把 LoRA 名当触发词）
    if not words:
        on = meta.get("ss_output_name")
        if on:
            words.append(on)
            words = clean_words(words)

    # 5. 文件名兜底
    if not words:
        base = os.path.splitext(fname)[0]
        for suf in ("IllustriousV2", "Illustrious", "IL", "V2", "v2", "V1", "v1", "10",
                    "CIVITAI", "civitai", "LoRA", "lora", "Style", "style", "IXL", "IXL-10"):
            if base.endswith(suf):
                base = base[: -len(suf)].rstrip("-_ ")
        base = base.replace("_", " ").replace("-", " ").strip()
        words = [base] if base else []
    return list(dict.fromkeys(words))[:6]


manual = load_manual()

for sub, key in (("checkpoints", "checkpoints"), ("loras", "loras")):
    d = os.path.join(BASE, sub)
    if not os.path.isdir(d):
        continue
    for fname in sorted(os.listdir(d)):
        if fname.endswith(".safetensors"):
            if fname in manual:
                # 手动配置优先：完整保留用户给的触发词，不做通用词过滤
                words = [w.strip() for w in manual[fname] if w and w.strip()]
                result[key][fname] = words[:30]
            else:
                result[key][fname] = extract_words(os.path.join(d, fname), fname)

print(json.dumps(result, ensure_ascii=False))
