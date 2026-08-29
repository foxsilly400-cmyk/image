src = open(r"C:\Users\28437\.openclaw\workspace\genui\static\app.js", encoding="utf-8").read()

block = '''
// ---------- 实例复位面板（切换 AutoDL 实例后保存新 SSH/公网信息）----------
if (document.getElementById("instBtn")) {
  $("instBtn").onclick = async () => {
    const text = $("instInput").value.trim();
    if (!text) { $("instNote").textContent = "请粘贴实例信息"; return; }
    $("instBtn").disabled = true;
    try {
      const r = await api("/api/instance", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (r.ok) {
        $("instNote").textContent = `已保存: ${r.instance.public_url}（SSH 端口 ${r.instance.ssh_port}）。` + (r.note || "");
        $("instInput").value = "";
      } else {
        $("instNote").textContent = "保存失败: " + (r.error || "");
      }
    } catch (e) {
      $("instNote").textContent = "错误: " + e.message;
    }
    $("instBtn").disabled = false;
  };
}
'''
src = src.rstrip() + "\n" + block
open(r"C:\Users\28437\.openclaw\workspace\genui\static\app.js", "w", encoding="utf-8", newline="\n").write(src)
print("appended, len:", len(src))
