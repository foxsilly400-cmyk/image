# -*- coding: utf-8 -*-
# 修复 genui/app.py 中指向旧实例的引用（迁移 9e22/cwgd -> 39l0）
import io

P = "/root/autodl-tmp/genui/app.py"
with io.open(P, encoding="utf-8") as f:
    s = f.read()

orig = s
s = s.replace('SSH_TARGET = "root@connect.westc.seetacloud.com"',
              'SSH_TARGET = "root@connect.weste.seetacloud.com"')
s = s.replace('SSH_PORT = "21647"', 'SSH_PORT = "39513"')
s = s.replace("https://u1139344-cwgd-cadc1936.weste.seetacloud.com:8443",
              "https://u1139344-39l0-9623d590.weste.seetacloud.com:8443")

if s == orig:
    print("NO_CHANGE")
else:
    with io.open(P, "w", encoding="utf-8") as f:
        f.write(s)
    print("PATCHED")

for line in s.splitlines():
    if line.startswith(("SSH_TARGET", "SSH_PORT", "SERVER_PUBLIC")):
        print(line)
