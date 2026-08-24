"""页面上下文模拟 done 分支，抓真实异常"""
import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(BASE + "/", timeout=60000)
    page.wait_for_timeout(4000)

    result = page.evaluate("""async () => {
        const out = {};
        try {
            out.favs = getFavs();
            out.favsLen = (out.favs || []).length;
        } catch (e) {
            out.getFavsErr = String(e);
        }
        try {
            const r = await fetch('/api/tasks');
            const d = await r.json();
            const t = d.tasks.find(x => x.status === 'done');
            out.task = t ? {id: t.id, imgs: t.images.length} : null;
            if (t) {
                const items = [];
                for (const img of t.images) {
                    items.push({ url: '/x', name: img.filename, settings: t.payload, filename: img.filename });
                }
                for (let idx = 0; idx < items.length; idx++) {
                    const it = items[idx];
                    const isFav = getFavs().some(f => f.img.filename === it.filename);
                    out.isFav = isFav;
                }
                out.itemsLen = items.length;
            }
        } catch (e) {
            out.doneErr = String(e);
        }
        out.statusText = document.getElementById('status').textContent;
        return out;
    }""")
    print(result)
    browser.close()
