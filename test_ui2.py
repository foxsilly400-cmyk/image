"""dump 页面 DOM 状态：提交任务后观察 gallery/status/浏览器视角 tasks"""
import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.on("pageerror", lambda e: print("PAGEERROR:", str(e)[:200]))

    page.goto(BASE + "/", timeout=60000)
    page.wait_for_timeout(3000)
    page.fill("#prompt", "1girl, score_9, best quality")
    page.click("#genBtn")
    page.wait_for_timeout(35000)

    # 浏览器视角的 tasks
    tasks = page.evaluate("""async () => {
        const r = await fetch('/api/tasks');
        const d = await r.json();
        return d.tasks.slice(0, 5).map(t => ({id: t.id, status: t.status, imgs: (t.images||[]).length}));
    }""")
    print("browser tasks:", tasks)

    status = page.locator("#status").inner_text()
    print("status:", status)
    gal_html = page.locator("#gallery").inner_html()
    print("gallery html len:", len(gal_html))
    print("gallery html:", gal_html[:400])
    browser.close()
