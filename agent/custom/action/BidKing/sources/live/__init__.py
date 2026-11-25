# -*- coding: utf-8 -*-
"""实机来源：唯一接触 MaaFramework、屏幕截图与 OCR 的目录。

capture / perceive / actions 都是 live source 的内部实现；核心层不得 import
本包。

`perceive/warehouse/` 是例外：纯 cv2/numpy 的仓库感知库，不接触 Maa/utils，
可被实时观察窗口、定盘预览、离线 CLI 与 pytest 共用；`perceive/__init__.py`
必须保持轻量，不能 import Maa。
"""
