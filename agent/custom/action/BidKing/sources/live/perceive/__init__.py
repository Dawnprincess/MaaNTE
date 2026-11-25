# -*- coding: utf-8 -*-
"""拍卖之王 - 实时感知层。

实时对局把截图看懂的地方：

  - `fields.py`       OCR 字段（接触 MaaFramework）
  - `observation.py`  字段编排，产出 Observation
  - `warehouse/`      纯 cv2/numpy 的仓库三页合并、块判定与预览，
                      实时观察窗口、定盘预览、离线 CLI 与 pytest 共用

本包自身的导入不接触 Maa / utils，保证离线工具可以 import
`sources.live.perceive.warehouse` 而不把框架带进进程。
"""

__all__: list[str] = []
