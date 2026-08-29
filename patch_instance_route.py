import re

p = r"C:\Users\28437\.openclaw\workspace\genui\app.py"
src = open(p, encoding="utf-8").read()

route = '''

@app.route("/api/instance", methods=["POST"])
def api_instance():
    """保存新实例 SSH/公网信息（切换实例后复位工作台用）"""
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    m = re.match(r"ssh\\s+-p\\s+(\\d+)\\s+(\\S+@\\S+)\\s+(\\S+)\\s+(https?://\\S+)", text)
    if not m:
        return jsonify({"ok": False,
                        "error": "格式无法解析，示例：ssh -p 25562 root@connect.westc.seetacloud.com 密码 https://公网:8443"})
    port, host, pwd, url = m.groups()
    info = {"ssh_port": port, "ssh_host": host, "ssh_password": pwd,
            "public_url": url, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open("/root/autodl-tmp/instance.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    return jsonify({"ok": True,
                    "instance": {"ssh_port": port, "ssh_host": host, "public_url": url},
                    "note": "已保存。固定入口与本地网关由本地复位脚本同步（scripts/reset_instance.py）"})
'''

anchor = "@app.route(\"/api/cancel\", methods=[\"POST\"])"
i = src.index(anchor)
src = src[:i] + route.strip() + "\n\n\n" + src[i:]
open(p, "w", encoding="utf-8", newline="\n").write(src)
print("inserted, len:", len(src))
