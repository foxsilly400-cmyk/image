js = open("static/app.js", encoding="utf-8").read()
old = 'poll error: " + e.message'
new = 'poll error: " + (e.stack || e.message)'
assert old in js, "pattern not found"
js = js.replace(old, new)
open("static/app.js", "w", encoding="utf-8").write(js)
print("patched stack")
