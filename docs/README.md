# 稳定入口（GitHub Pages）

`index.html` 是固定网址入口：读取 `target.json` 里的当前实例地址，健康检查通过后自动跳转，失败则显示手动进入按钮。

- 稳定网址（启用 Pages 后）：https://foxsilly400-cmyk.github.io/image/
- 换实例：改 `target.json` 的 `target` 字段并推送 main 分支即可，入口网址不变。
- Pages 配置：Settings → Pages → Deploy from a branch → main /docs。
- 注意：genui 的 /api/* 已带 `Access-Control-Allow-Origin: *`，所以页面可以直接做跨域健康检查。
