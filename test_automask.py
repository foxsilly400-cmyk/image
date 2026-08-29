"""本地验证 auto_mask：body / all_but_face 两种模式的遮罩生成"""
import os
import shutil

import cv2

INPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ComfyUI", "input")
os.makedirs(INPUT, exist_ok=True)

SRC = r"C:\Users\28437\.openclaw\workspace\db_smegma\imgs\11006212_a13d6e7a489ba390aab06ba88dec1010.jpg"
SRC_NAME = "test_automask_src.jpg"
shutil.copy(SRC, os.path.join(INPUT, SRC_NAME))

import app  # noqa: E402  (本地模式，ON_SERVER=False)

for mode in ("body", "all_but_face"):
    fname, nfaces = app.auto_mask(SRC_NAME, mode)
    print(f"[{mode}] mask={fname} faces={nfaces}")
    mask = cv2.imread(os.path.join(INPUT, fname), cv2.IMREAD_UNCHANGED)
    print("  shape:", mask.shape, "alpha min/max:", mask[:, :, 3].min(), mask[:, :, 3].max())
    h, w = mask.shape[:2]
    a = mask[:, :, 3]
    # 分三行统计 alpha=255（前端风格=重绘）比例：上/中/下
    for label, r0, r1 in (("上1/3", 0, h // 3), ("中1/3", h // 3, 2 * h // 3), ("下1/3", 2 * h // 3, h)):
        seg = a[r0:r1, :]
        print(f"  {label}: 重绘占比 {100.0 * (seg > 128).mean():.1f}%")
    os.remove(os.path.join(INPUT, fname))

os.remove(os.path.join(INPUT, SRC_NAME))
print("DONE")
