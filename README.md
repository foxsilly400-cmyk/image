# 生成工作台（genui）
Civitai 风格图像生成面板：Flask + ComfyUI 桥接，支持队列生成、画廊、收藏、触发词、模型导入。
- 后端：app.py（Flask，桥接 ComfyUI API）
- 前端：templates/ + static/
- 部署：服务器直跑或本机 + SSH 隧道
