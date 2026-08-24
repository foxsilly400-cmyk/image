const $ = (id) => document.getElementById(id);
const LS_KEY = "***";
const LS_FAV = "genui_favs_v1";

const CONTROLS = ["ckpt", "vae", "prompt", "negative", "steps", "cfg", "sampler", "scheduler",
                  "width", "height", "seed", "batch", "clipSkip", "enhCompat", "hires",
                  "hiresScale", "hiresDenoise"];

async function api(path, opts) {
  const r = await fetch(path, opts);
  return r.json();
}

// ---------- 设置持久化 ----------
function saveSettings() {
  const s = {};
  for (const id of CONTROLS) {
    const el = $(id);
    if (!el) continue;
    s[id] = el.type === "checkbox" ? el.checked : el.value;
  }
  s.loras = [...document.querySelectorAll(".lora-row")].map(r => ({
    name: r.querySelector("select").value,
    weight: r.querySelector("input").value,
  }));
  localStorage.setItem(LS_KEY, JSON.stringify(s));
}

function loadSettings() {
  let s = {};
  try { s = JSON.parse(localStorage.getItem(LS_KEY)) || {}; } catch (e) {}
  for (const id of CONTROLS) {
    const el = $(id);
    if (!el || !(id in s)) continue;
    if (el.type === "checkbox") el.checked = !!s[id];
    else el.value = s[id];
  }
  window.PENDING_LORAS = s.loras || [];
}

CONTROLS.forEach(id => {
  const el = $(id);
  if (el) el.addEventListener("change", saveSettings);
});
document.querySelectorAll("textarea, input").forEach(el => {
  if (!el.id) return;
  el.addEventListener("input", saveSettings);
});

// ---------- 收藏（服务器端存储） ----------
let FAVS_CACHE = [];

async function loadFavs() {
  try {
    const r = await api("/api/favs");
    if (r.ok) {
      FAVS_CACHE = r.favs || [];
      // 迁移：本地旧数据合并上传（仅旧页面 origin 有）
      let old = [];
      try { old = JSON.parse(localStorage.getItem(LS_FAV)) || []; } catch (e) {}
      if (old.length) {
        const merged = [...old, ...FAVS_CACHE];
        const seen = new Set();
        const uniq = merged.filter(f => { const k = f.img && f.img.filename; if (!k || seen.has(k)) return false; seen.add(k); return true; });
        FAVS_CACHE = uniq;
        await saveFavs();
        localStorage.removeItem(LS_FAV);
        console.log("收藏已迁移到服务器:", uniq.length);
      }
      updateFavCount();
      renderFavs();
    }
  } catch (e) {}
}

async function saveFavs() {
  try {
    await api("/api/favs", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ favs: FAVS_CACHE }),
    });
  } catch (e) {}
}

function getFavs() { return FAVS_CACHE; }

function setFavs(f) { FAVS_CACHE = f; saveFavs(); updateFavCount(); }
function updateFavCount() { $("favCount").textContent = FAVS_CACHE.length; }

function collectSettings() {
  const loras = [...document.querySelectorAll(".lora-row")].map(r => ({
    name: r.querySelector("select").value,
    weight: parseFloat(r.querySelector("input").value),
  })).filter(l => l.name && l.name !== "None");
  return {
    checkpoint: $("ckpt").value, loras, vae: $("vae").value,
    prompt: $("prompt").value, negative: $("negative").value,
    steps: parseInt($("steps").value), cfg: parseFloat($("cfg").value),
    sampler: $("sampler").value, scheduler: $("scheduler").value,
    width: parseInt($("width").value), height: parseInt($("height").value),
    seed: parseInt($("seed").value), batch: parseInt($("batch").value),
    clip_skip: parseInt($("clipSkip").value) || 1,
    hires: $("hires").checked,
    hires_scale: parseFloat($("hiresScale").value),
    hires_denoise: parseFloat($("hiresDenoise").value),
  };
}

function buildPayload() {
  const p = collectSettings();
  if ($("enhCompat").checked) {
    p.sampler = "euler"; p.scheduler = "normal"; p.cfg = 5; p.clip_skip = 1;
  }
  return p;
}

async function addFav(img, settings) {
  FAVS_CACHE.unshift({ id: Date.now().toString(36), img, settings, time: Date.now() });
  await saveFavs();
  updateFavCount();
  renderFavs();
}

function removeFav(id) {
  FAVS_CACHE = FAVS_CACHE.filter(f => f.id !== id);
  saveFavs();
  updateFavCount();
  renderFavs();
}

function applySettings(s) {
  for (const k of CONTROLS) {
    if (s[k] === undefined) continue;
    const el = $(k);
    if (!el) continue;
    if (el.type === "checkbox") el.checked = !!s[k];
    else el.value = s[k];
  }
  const box = $("loraList");
  box.innerHTML = "";
  if (s.loras && s.loras.length) s.loras.forEach(l => addLoraRow(l.name, l.weight));
  else addLoraRow();
  saveSettings();
}

function imgUrl(img) {
  return `/api/image?filename=${encodeURIComponent(img.filename)}&subfolder=${encodeURIComponent(img.subfolder || "")}&type=${img.type || "output"}`;
}

// 已删除图片记录（sessionStorage，防轮询重新渲染）
let DELETED = new Set();
try { DELETED = new Set(JSON.parse(sessionStorage.getItem("genui_deleted") || "[]")); } catch (e) {}
function markDeleted(fn) {
  DELETED.add(fn);
  sessionStorage.setItem("genui_deleted", JSON.stringify([...DELETED]));
}

function renderFavs() {
  const list = $("favList");
  const favs = getFavs();
  list.innerHTML = "";
  if (!favs.length) { list.innerHTML = '<div class="hint" style="padding:10px">还没有收藏</div>'; return; }
  for (const f of favs) {
    const item = document.createElement("div");
    item.className = "fav-item";
    const im = document.createElement("img");
    im.src = imgUrl(f.img);
    im.onclick = () => openLightbox(imgUrl(f.img), "收藏图片", f.settings);
    const info = document.createElement("div");
    info.className = "f-info";
    const pr = document.createElement("div");
    pr.className = "f-prompt";
    pr.textContent = (f.settings.prompt || "").slice(0, 120);
    const acts = document.createElement("div");
    acts.className = "f-actions";
    const b1 = document.createElement("button");
    b1.textContent = "填入";
    b1.onclick = () => { applySettings(f.settings); $("favPanel").classList.add("hidden"); };
    const b2 = document.createElement("button");
    b2.textContent = "重新生成";
    b2.onclick = () => { applySettings(f.settings); submitGen(); $("favPanel").classList.add("hidden"); };
    const b3 = document.createElement("button");
    b3.textContent = "删";
    b3.className = "f-del";
    b3.onclick = () => removeFav(f.id);
    acts.append(b1, b2, b3);
    info.append(pr, acts);
    item.append(im, info);
    list.appendChild(item);
  }
}

$("favBtn").onclick = () => {
  renderFavs();
  $("favPanel").classList.toggle("hidden");
};
$("favClose").onclick = () => $("favPanel").classList.add("hidden");

// ---------- 初始化 ----------
async function init() {
  loadSettings();
  updateFavCount();
  try {
    const [ck, lr, vae] = await Promise.all([
      api("/api/checkpoints"), api("/api/loras"), api("/api/vaes"),
    ]);
    if (ck.ok && lr.ok && vae.ok) {
      $("conn").textContent = "已连接";
      $("conn").classList.add("ok");
      $("ckpt").innerHTML = ck.items.map(n => `<option>${n}</option>`).join("");
      $("vae").innerHTML = vae.items.map(n => `<option>${n}</option>`).join("");
      window.LORAS = lr.items;
      const pend = window.PENDING_LORAS;
      if (pend && pend.length) pend.forEach(l => addLoraRow(l.name, l.weight));
      else addLoraRow();
      const s = JSON.parse(localStorage.getItem(LS_KEY) || "{}");
      for (const id of ["ckpt", "vae"]) {
        if (s[id] && $(id).querySelector(`option[value="${s[id]}"]`)) $(id).value = s[id];
      }
    } else {
      $("conn").textContent = "连接失败";
      $("conn").classList.add("bad");
      addLoraRow();
    }
    refreshTriggers();
  } catch (e) {
    $("conn").textContent = "连接失败";
    $("conn").classList.add("bad");
    addLoraRow();
  }
}

function addLoraRow(name = "", weight = 0.8) {
  const box = $("loraList");
  const row = document.createElement("div");
  row.className = "lora-row";
  const sel = document.createElement("select");
  sel.innerHTML = (window.LORAS || []).map(n => `<option ${n === name ? "selected" : ""}>${n}</option>`).join("");
  const w = document.createElement("input");
  w.type = "number"; w.step = "0.05"; w.min = "0"; w.max = "2"; w.value = weight;
  const del = document.createElement("button");
  del.className = "del"; del.textContent = "✕";
  del.onclick = () => { row.remove(); saveSettings(); };
  sel.onchange = saveSettings; w.oninput = saveSettings;
  row.append(sel, w, del);
  box.appendChild(row);
}

$("addLora").onclick = () => { addLoraRow(); saveSettings(); };

document.querySelectorAll(".chip").forEach(ch => {
  ch.onclick = () => { $("width").value = ch.dataset.w; $("height").value = ch.dataset.h; saveSettings(); };
});

$("seedRandom").onclick = () => {
  $("seed").value = Math.floor(Math.random() * 2**31);
  saveSettings();
};

// ---------- 导入模型 ----------
$("importBtn").onclick = () => {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".safetensors";
  inp.onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const kind = f.size > 1024 * 1024 * 1024 ? "checkpoint" :
      (confirm("导入为 LoRA？（取消 = 作为 Checkpoint）") ? "lora" : "checkpoint");
    const fd = new FormData();
    fd.append("file", f);
    fd.append("kind", kind);
    $("status").textContent = `导入中 (${(f.size/1e6).toFixed(0)} MB)... 上传到服务器可能需要几分钟`;
    const r = await api("/api/import", { method: "POST", body: fd });
    if (r.ok) {
      $("status").textContent = `导入完成: ${r.name} → ${r.dest}`;
      // 刷新列表
      const [ck, lr] = await Promise.all([api("/api/checkpoints"), api("/api/loras")]);
      $("ckpt").innerHTML = ck.items.map(n => `<option>${n}</option>`).join("");
      window.LORAS = lr.items;
      addLoraRow(r.name);
    } else {
      $("status").textContent = "导入失败: " + r.error;
    }
  };
  inp.click();
};

// ---------- 豪横预设 ----------
$("luxBtn").onclick = () => {
  $("steps").value = 45;
  $("cfg").value = 6.5;
  $("sampler").value = "dpmpp_2m_sde";
  $("scheduler").value = "karras";
  $("hires").checked = true;
  $("hiresScale").value = 1.5;
  $("hiresDenoise").value = 0.4;
  const extra = "score_9, score_8_up, score_7_up, best quality, amazing quality, very aesthetic, absurdres";
  const cur = $("prompt").value.trim();
  const has = ["score_9", "best quality", "absurdres"].some(t => cur.includes(t));
  if (cur && !has) $("prompt").value = cur + ", " + extra;
  else if (!cur) $("prompt").value = extra;
  if (!$("negative").value.trim()) {
    $("negative").value = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry";
  }
  saveSettings();
  $("status").textContent = "已应用豪横预设";
};

// ---------- 触发词按钮 ----------
let TRIGGERS = { checkpoints: {}, loras: {} };

async function refreshTriggers() {
  try {
    const r = await api("/api/triggers");
    if (r.ok) {
      TRIGGERS = r;
      renderTriggers();
    }
  } catch (e) {}
}

function renderTriggers() {
  const box = $("triggers");
  if (!box) return;
  const words = [];
  const ck = $("ckpt").value;
  if (ck && TRIGGERS.checkpoints[ck]) words.push(...TRIGGERS.checkpoints[ck]);
  document.querySelectorAll(".lora-row select").forEach(sel => {
    const v = sel.value;
    if (v && TRIGGERS.loras[v]) words.push(...TRIGGERS.loras[v]);
  });
  const uniq = [...new Set(words)];
  box.innerHTML = "";
  if (!uniq.length) return;
  const lab = document.createElement("span");
  lab.className = "trig-label";
  lab.textContent = "触发词:";
  box.appendChild(lab);
  for (const w of uniq) {
    const b = document.createElement("button");
    b.className = "trig";
    b.textContent = w;
    b.onclick = async () => {
      try {
        await navigator.clipboard.writeText(w);
      } catch (e) {
        // 兼容非 https 环境
        const ta = document.createElement("textarea");
        ta.value = w;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      b.textContent = "✓ 已复制";
      b.classList.add("copied");
      setTimeout(() => { b.textContent = w; b.classList.remove("copied"); }, 1200);
    };
    box.appendChild(b);
  }
}

$("ckpt").addEventListener("change", renderTriggers);
$("loraList").addEventListener("change", renderTriggers);

// ---------- 手机端 Tab 切换 ----------
document.querySelectorAll(".tab").forEach(t => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    const page = t.dataset.page;
    document.querySelectorAll(".page-gen, .page-imgs").forEach(x => x.classList.remove("active"));
    document.querySelector(`.page-${page}`).classList.add("active");
  };
});

// ---------- 生成（队列） ----------
async function submitGen() {
  const payload = buildPayload();
  $("status").textContent = "已加入队列";
  const resp = await api("/api/generate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) { $("status").textContent = "错误: " + resp.error; return; }
  $("status").textContent = "任务 " + resp.task_id + " 已入队";
  // 移动端自动切到图片页看进度
  if (getComputedStyle($("tabbar")).display !== "none") {
    document.querySelector(".tab[data-page=imgs]").click();
  }
}

$("genBtn").onclick = submitGen;

// ---------- 任务列表 + 画廊 ----------
function settingsSummary(s) {
  if (!s) return "";
  const l = (s.loras || []).map(x => `${x.name.split(".")[0]}:${x.weight}`).join(", ");
  return [
    `Checkpoint: ${(s.checkpoint || "").split(".")[0]}`,
    l ? `LoRA: ${l}` : "",
    `Steps ${s.steps} / CFG ${s.cfg} / ${s.sampler} ${s.scheduler}`,
    `${s.width}x${s.height} / seed ${s.seed} / batch ${s.batch}`,
    s.hires ? `Hires ${s.hires_scale}x d${s.hires_denoise}` : "",
    s.clip_skip > 1 ? `CLIP Skip ${s.clip_skip}` : "",
  ].filter(Boolean).join("\n");
}

async function pollTasks() {
  try {
    const r = await api("/api/tasks");
    if (!r.ok) return;
    const gal = $("gallery");
    gal.innerHTML = "";
    const running = r.tasks.filter(t => t.status === "running" || t.status === "queued").length;
    if (running) $("status").textContent = `队列中 ${running} 个任务...`;
    for (const t of r.tasks.slice(0, 10)) {
      // 进行中的任务：占位卡
      if (t.status === "queued" || t.status === "running") {
        const card = document.createElement("div");
        card.className = "img-card pending";
        const ph = document.createElement("div");
        ph.className = "pending-ph";
        ph.innerHTML = `<span class="spinner"></span><div>${t.status === "queued" ? "排队中" : "生成中"}</div>`;
        const bar = document.createElement("div");
        bar.className = "bar";
        const pr = document.createElement("span");
        pr.className = "t-prompt";
        pr.textContent = (t.prompt || "").slice(0, 60);
        bar.appendChild(pr);
        card.append(ph, bar);
        gal.appendChild(card);
        continue;
      }
      if (t.status === "error") {
        const card = document.createElement("div");
        card.className = "img-card error";
        const ph = document.createElement("div");
        ph.className = "pending-ph";
        ph.innerHTML = `<div style="color:#e5484d">失败</div><div class="t-prompt">${(t.error || "").slice(0, 60)}</div>`;
        card.appendChild(ph);
        gal.appendChild(card);
        continue;
      }
      // 完成：每张图都展示（已删除的跳过）
      if (t.status === "done" && t.images && t.images.length) {
        for (const img of t.images) {
          if (DELETED.has(img.filename)) continue;
          const card = document.createElement("div");
          card.className = "img-card";
          const im = document.createElement("img");
          im.src = imgUrl(img);
          im.onerror = () => { im.style.visibility = "hidden"; card.style.minHeight = "120px"; };
          im.onclick = () => openLightbox(imgUrl(img), img.filename, t.payload);
          const bar = document.createElement("div");
          bar.className = "bar";
          const fav = document.createElement("button");
          fav.className = "fav-btn";
          const isFav = getFavs().some(f => f.img.filename === img.filename);
          fav.textContent = isFav ? "★" : "☆";
          fav.classList.toggle("on", isFav);
          fav.title = isFav ? "已收藏（点击取消收藏）" : "收藏此图的提示词和设置";
          fav.onclick = () => {
            if (isFav) {
              const favs = getFavs().filter(f => f.img.filename !== img.filename);
              setFavs(favs);
              renderFavs();
              fav.textContent = "☆";
              fav.classList.remove("on");
              fav.title = "收藏此图的提示词和设置";
            } else {
              addFav(img, t.payload || {});
              fav.textContent = "★";
              fav.classList.add("on");
              fav.title = "已收藏（点击取消收藏）";
            }
          };
          const del = document.createElement("button");
          del.className = "fav-btn del-btn";
          del.textContent = "🗑";
          del.title = "删除此图片（服务器文件）";
          del.onclick = () => {
            if (!confirm("删除这张图片？（服务器文件将移除）")) return;
            // 先移除 UI，再异步删后台（不阻塞）
            markDeleted(img.filename);
            card.remove();
            $("status").textContent = "已删除";
            api("/api/delete_image", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ filename: img.filename }),
            }).then(r => {
              if (!r.ok) $("status").textContent = "后台删除失败: " + (r.error || "");
            });
          };
          const dl = document.createElement("a");
          dl.href = imgUrl(img);
          dl.download = "";
          dl.textContent = "下载";
          bar.append(fav, del, dl);
          card.append(im, bar);
          gal.appendChild(card);
        }
      }
    }
  } catch (e) {}
}
setInterval(pollTasks, 2000);

// ---------- Lightbox：大图 + 侧边信息 ----------
let lbScale = 1, lbX = 0, lbY = 0, lbDrag = null;
function openLightbox(url, name, settings) {
  const lb = $("lightbox");
  $("lbImg").src = url;
  lbScale = 1; lbX = 0; lbY = 0;
  applyLbTransform();
  // 侧边信息面板
  const side = $("lbSide");
  side.innerHTML = "";
  if (settings) {
    const h = document.createElement("h4");
    h.textContent = name || "图片信息";
    side.appendChild(h);
    const pre = document.createElement("pre");
    pre.className = "lb-settings";
    pre.textContent = settingsSummary(settings);
    side.appendChild(pre);
    const fill = document.createElement("button");
    fill.className = "btn-primary";
    fill.textContent = "📝 填入提示词及设置";
    fill.onclick = () => { applySettings(settings); };
    side.appendChild(fill);
    const reg = document.createElement("button");
    reg.className = "btn-ghost";
    reg.textContent = "🔄 用此设置重新生成";
    reg.onclick = () => { applySettings(settings); submitGen(); };
    side.appendChild(reg);
    const fav = document.createElement("button");
    fav.className = "btn-ghost";
    fav.textContent = "⭐ 收藏";
    fav.onclick = () => {
      const img = { filename: url.split("filename=")[1].split("&")[0], subfolder: "", type: "output" };
      addFav(img, settings);
    };
    side.appendChild(fav);
  } else {
    const h = document.createElement("h4");
    h.textContent = name || "图片信息";
    side.appendChild(h);
  }
  $("lbInfo").textContent = "滚轮缩放 / 拖拽移动 / Esc 关闭";
  lb.classList.remove("hidden");
}
function applyLbTransform() {
  $("lbImg").style.transform = `translate(${lbX}px, ${lbY}px) scale(${lbScale})`;
}
$("lbClose").onclick = () => $("lightbox").classList.add("hidden");
$("lightbox").addEventListener("click", (e) => {
  if (e.target === $("lightbox")) $("lightbox").classList.add("hidden");
});
$("lbStage").addEventListener("wheel", (e) => {
  e.preventDefault();
  const delta = e.deltaY > 0 ? 0.9 : 1.1;
  lbScale = Math.min(12, Math.max(0.2, lbScale * delta));
  applyLbTransform();
}, { passive: false });
$("lbStage").addEventListener("mousedown", (e) => {
  lbDrag = { x: e.clientX - lbX, y: e.clientY - lbY };
  e.preventDefault();
});
window.addEventListener("mousemove", (e) => {
  if (lbDrag) { lbX = e.clientX - lbDrag.x; lbY = e.clientY - lbDrag.y; applyLbTransform(); }
});
window.addEventListener("mouseup", () => lbDrag = null);
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { $("lightbox").classList.add("hidden"); $("favPanel").classList.add("hidden"); }
});

init();
pollTasks();
refreshTriggers();
loadFavs();
