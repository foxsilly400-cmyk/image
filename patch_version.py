p = r"C:\Users\28437\.openclaw\workspace\genui\templates\index.html"
s = open(p, encoding="utf-8").read()
s2 = s.replace("v=20260829d", "v=20260829e")
print("replaced:", s != s2, "| has e:", "v=20260829e" in s2)
open(p, "w", encoding="utf-8", newline="\n").write(s2)
