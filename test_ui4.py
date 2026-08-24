"""直接调用页面 pollTasks，检查 gallery 渲染结果"""
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
            await pollTasks();
            out.galLen = document.getElementById('gallery').innerHTML.length;
            out.galHtml = document.getElementById('gallery').innerHTML.slice(0, 300);
        } catch (e) {
            out.err = String(e);
        }
        return out;
    }""")
    print(result)
    browser.close()
