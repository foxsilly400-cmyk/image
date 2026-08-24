"""playwright 打开公网页面，提交生成，观察画廊是否出现图片"""
import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(f"[console.{m.type}] {m.text}") if m.type == "error" else None)

    page.goto(BASE + "/", timeout=60000)
    page.wait_for_timeout(3000)
    print("title:", page.title())

    # 填 prompt + 生成
    page.fill("#prompt", "1girl, purple hair, score_9, best quality")
    page.click("#genBtn")
    print("submitted")
    page.wait_for_timeout(3000)

    # 等待任务完成（轮询画廊卡片数量）
    for i in range(40):
        cards = page.locator(".img-card").count()
        status = page.locator("#status").inner_text()
        print(f"  t={i*3}s cards={cards} status={status[:40]}")
        if cards > 0 and "完成" in status:
            break
        page.wait_for_timeout(3000)

    print("page errors:", errors[:5] if errors else "none")
    browser.close()
