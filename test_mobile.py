"""手机视口（390x844）完整流程：提交生成 → 观察画廊"""
import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 390, "height": 844},
                              is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.on("pageerror", lambda e: print("PAGEERROR:", str(e)[:200]))

    page.goto(BASE + "/", timeout=60000)
    page.wait_for_timeout(3000)

    # 检查 tabbar 是否可见（移动端）
    tab_display = page.evaluate("getComputedStyle(document.getElementById('tabbar')).display")
    print("tabbar display:", tab_display)

    # 提交生成
    page.fill("#prompt", "1girl, score_9, best quality")
    page.click("#genBtn")
    print("submitted")
    page.wait_for_timeout(4000)

    # 观察：当前显示哪个 tab，gallery 状态
    state = page.evaluate("""() => {
        const gen = document.querySelector('.page-gen');
        const imgs = document.querySelector('.page-imgs');
        return {
            genActive: gen.classList.contains('active'),
            imgsActive: imgs.classList.contains('active'),
            genDisplay: getComputedStyle(gen).display,
            imgsDisplay: getComputedStyle(imgs).display,
            status: document.getElementById('status').textContent,
            galleryCards: document.querySelectorAll('#gallery .img-card').length,
        };
    }""")
    print("state:", state)

    # 等任务完成
    for i in range(30):
        page.wait_for_timeout(4000)
        st = page.evaluate("""() => ({
            status: document.getElementById('status').textContent,
            cards: document.querySelectorAll('#gallery .img-card').length,
        })""")
        print(i, st)
        if "完成" in st["status"] or st["cards"] > 0:
            break
    browser.close()
