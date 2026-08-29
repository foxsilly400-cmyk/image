css = open(r"C:\Users\28437\.openclaw\workspace\genui\static\style.css", encoding="utf-8").read()

block = '''
/* 实例复位面板 */
.inst-panel {
  margin-top: 12px; border: 1px solid var(--border); border-radius: 10px;
  padding: 8px 10px; font-size: 12px;
}
.inst-panel summary { cursor: pointer; color: var(--muted); font-weight: 600; user-select: none; }
.inst-panel summary:hover { color: var(--text); }
.inst-panel input {
  width: 100%; box-sizing: border-box; margin: 8px 0 6px;
  background: rgba(10, 12, 18, 0.5); border: 1px solid var(--border); color: var(--text);
  border-radius: 8px; padding: 7px 10px; font-size: 12px;
}
.inst-note { color: var(--muted); margin-top: 6px; word-break: break-all; line-height: 1.5; }
'''
open(r"C:\Users\28437\.openclaw\workspace\genui\static\style.css", "w", encoding="utf-8", newline="\n").write(css.rstrip() + "\n" + block)
print("css appended")
