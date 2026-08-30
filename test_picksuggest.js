// 验证 pickSuggest 修复：模拟替换逻辑（与 app.js 中修复后逻辑一致）
function currentTag(v, pos) {
  const before = v.slice(0, pos);
  const lastSep = Math.max(before.lastIndexOf(","), before.lastIndexOf("\n"));
  let start = lastSep + 1;
  while (start < before.length && v[start] === " ") start++;
  const cur = before.slice(start);
  return { cur, start };
}

function pick(v, suggestStart, item) {
  let start = suggestStart;
  if (start < 0 || start > v.length) start = currentTag(v, v.length).start;
  let end = start;
  while (end < v.length && v[end] !== "," && v[end] !== "\n") end++;
  const after = v.slice(end);
  const sep = after ? (after.startsWith(",") || after.startsWith("\n") ? after : ", " + after) : "";
  return v.slice(0, start) + item + sep;
}

let pass = 0, fail = 0;
function check(name, got, want) {
  if (got === want) { pass++; console.log("PASS", name); }
  else { fail++; console.log("FAIL", name, "\n  got :", JSON.stringify(got), "\n  want:", JSON.stringify(want)); }
}

// 1. 普通单行：词后无逗号
check("单行词尾", pick("score_9, 1girl", 9, "1girl, solo"), "score_9, 1girl, solo");
// 2. 词后有逗号+后续词
check("逗号后续词", pick("score_9, 1girl, best quality", 9, "1girl, solo"), "score_9, 1girl, solo, best quality");
// 3. 词后换行+后续行（原 bug：后续行被吞）
check("换行后内容保留", pick("score_9, 1girl\nbest quality", 9, "1girl, solo"), "score_9, 1girl, solo\nbest quality");
// 4. 换行后内容保留 + 光标在换行后的行（原 bug：currentTag 把换行算进词）
const t4 = currentTag("score_9, 1girl\nbest q", 24);
check("换行行首定位", t4.cur, "best q");
check("换行行首替换", pick("score_9, 1girl\nbest q", t4.start, "best quality"), "score_9, 1girl\nbest quality");
// 5. 词后逗号+换行：逗号保留，换行保留
check("逗号换行", pick("score_9, 1girl,\nbest quality", 9, "1girl, solo"), "score_9, 1girl, solo,\nbest quality");
// 6. 词是最后一段且紧跟换行
check("词后直接换行", pick("1girl\nbest", 0, "1girl, solo"), "1girl, solo\nbest");
// 7. 光标在词中间，整体替换（start 由 currentTag 推导，模拟真实流程）
const t7 = currentTag("a, 1g, b", 5);
check("词中间定位", t7.cur, "1g");
check("词中间", pick("a, 1g, b", t7.start, "1girl, solo"), "a, 1girl, solo, b");
// 8. 文本只有当前词
check("单词", pick("1girl", 0, "1girl, solo"), "1girl, solo");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
