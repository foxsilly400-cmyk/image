#!/bin/bash
# 启动 ComfyUI（8188）。AUX_ANNOTATOR_CKPTS_PATH 让 controlnet_aux 从 models/annotator 找 DW 模型
export AUX_ANNOTATOR_CKPTS_PATH=/root/autodl-tmp/ComfyUI/models/annotator
cd /root/autodl-tmp/ComfyUI
/root/miniconda3/bin/python main.py --listen 0.0.0.0 --port 8188
