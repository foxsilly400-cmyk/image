"""实例切换复位脚本：解析 AutoDL ssh 信息 → 更新 genui 仓库配置 → 推送 GitHub → 热切本地网关 → SSH 远端恢复服务

用法:
  python reset_instance.py "ssh -p 25562 root@connect.westc.seetacloud.com b1j+7G45IlEm https://u1139344-8e64-c621ed69.westc.seetacloud.com:8443"

更新内容:
  1. genui/app.py         -> SSH_TARGET / SSH_PORT / SERVER_PUBLIC
  2. genui/docs/target.json        -> GitHub Pages 稳定入口
  3. genui/stable_gateway/current.json -> 本地网关 6008
  4. 本地网关 /__set 热切换（不重启）
  5. git commit + push（代理 7890），GitHub Pages 自动更新
  6. SSH 到新实例跑 restore_after_boot.sh（拉起 ComfyUI + genui + watchdog）
"""
import sys
import re
import json
import time
import os
import subprocess
import urllib.request

GENUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def parse(text):
    m = re.match(r"ssh\s+-p\s+(\d+)\s+(\S+@\S+)\s+(\S+)\s+(https?://\S+)", text.strip())
    if not m:
        raise SystemExit("格式无法解析。示例:\n  ssh -p 25562 root@connect.westc.seetacloud.com 密码 https://u1139344-xxx.westc.seetacloud.com:8443")
    port, userhost, pwd, url = m.groups()
    user, _, host = userhost.partition("@")
    return port, user, host, pwd, url


def update_app_py(port, host, url):
    p = os.path.join(GENUI, "app.py")
    src = open(p, encoding="utf-8").read()
    before = src
    src = re.sub(r'SSH_TARGET = "[^"]*"', f'SSH_TARGET = "{host}"', src)
    src = re.sub(r'SSH_PORT = "[^"]*"', f'SSH_PORT = "{port}"', src)
    src = re.sub(r'SERVER_PUBLIC = "[^"]*"', f'SERVER_PUBLIC = "{url}"', src)
    if src == before:
        if 'SSH_TARGET = "' in src and 'SSH_PORT = "' in src and 'SERVER_PUBLIC = "' in src:
            print("  [app.py] 配置值无变化")
        else:
            print("  [app.py] 未匹配到配置项（检查正则），跳过")
    else:
        open(p, "w", encoding="utf-8", newline="\n").write(src)
        print("  [app.py] SSH_TARGET=%s SSH_PORT=%s SERVER_PUBLIC=%s" % (host, port, url))


def update_target_json(url):
    p = os.path.join(GENUI, "docs", "target.json")
    data = {"target": url, "updated": time.strftime("%Y-%m-%d %H:%M +08:00")}
    open(p, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False))
    print("  [target.json] ->", url)


def update_gateway_json(url):
    p = os.path.join(GENUI, "stable_gateway", "current.json")
    open(p, "w", encoding="utf-8").write(json.dumps({"target": url}))
    print("  [current.json] ->", url)
    # 热切换运行中的网关（不重启）
    try:
        with urllib.request.urlopen("http://127.0.0.1:6008/__set?url=" + urllib.request.quote(url, safe=""), timeout=5) as r:
            print("  [gateway] /__set:", r.read().decode().strip())
    except Exception as e:
        print("  [gateway] 未运行或切换失败（可忽略）:", e)


def git_push(url):
    subprocess.run(["git", "add", "-A"], cwd=GENUI, check=True)
    subprocess.run(["git", "commit", "-m", "chore: 实例切换复位 -> %s" % url], cwd=GENUI)
    r = subprocess.run(["git", "-c", "http.proxy=http://127.0.0.1:7890", "push", "origin", "main"], cwd=GENUI, capture_output=True, text=True)
    print("  [git] push:", (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "OK")


def _resolve_ip(host):
    """解析主机 IP：先 socket.getaddrinfo，失败则 nslookup 兜底（返回最后一个 IPv4）。"""
    import socket
    try:
        return socket.getaddrinfo(host, 1)[0][4][0]
    except Exception:
        pass
    try:
        r = subprocess.run(["nslookup", host], capture_output=True, text=True, timeout=15)
        ips = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", (r.stdout or "") + (r.stderr or ""))
        if ips:
            return ips[-1]
    except Exception:
        pass
    return None


def ssh_restore(host, user, port, pwd):
    """SSH 到新实例跑恢复脚本（拉起 ComfyUI + genui + watchdog）。
    restore_after_boot.sh 需已存在于数据盘 /root/autodl-tmp/（换实例后数据盘保留）。"""
    import paramiko
    print("== SSH 远端恢复 ==")
    connect_host = host
    ip = _resolve_ip(host)
    if ip:
        connect_host = ip
        print("  [dns] %s -> %s" % (host, ip))
    else:
        print("  [dns] 解析失败，将直接尝试 %s" % host)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    last_err = None
    for attempt in range(3):
        try:
            client.connect(connect_host, port=int(port), username=user, password=pwd, timeout=20)
            last_err = None
            break
        except Exception as e:
            last_err = e
            print("  [ssh] 第 %d 次连接失败: %s" % (attempt + 1, e))
            if attempt < 2:
                time.sleep(5)
    if last_err:
        print("  请手动 SSH 后执行: bash /root/autodl-tmp/restore_after_boot.sh")
        return
    stdin, stdout, stderr = client.exec_command("bash /root/autodl-tmp/restore_after_boot.sh", timeout=200)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    print(out)
    if err.strip():
        print("  [stderr]", err.strip().splitlines()[-1])
    if code == 0:
        print("  [OK] 新实例服务已恢复")
    elif code == 2:
        print("  [FATAL] 系统盘 miniconda 丢失，需先恢复环境（用保存镜像或重装）")
    else:
        print("  [WARN] 恢复未完全成功（code=%s），看远端 comfy.log / genui.log" % code)
    client.close()


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    text = sys.argv[1]
    print("== 解析输入 ==")
    port, user, host, pwd, url = parse(text)
    print("  SSH 端口:", port)
    print("  SSH 用户:", user)
    print("  SSH 主机:", host)
    print("  公网地址:", url)
    print("== 更新配置 ==")
    update_app_py(port, host, url)
    update_target_json(url)
    update_gateway_json(url)
    print("== SSH 远端恢复（先恢复服务，再切入口）==")
    ssh_restore(host, user, port, pwd)
    print("== 推送 GitHub（稳定入口生效）==")
    git_push(url)
    print("== 完成 ==")
    print("固定入口: https://ranbow400.github.io/image/")
    print("本地网关: http://127.0.0.1:6008")


if __name__ == "__main__":
    main()
