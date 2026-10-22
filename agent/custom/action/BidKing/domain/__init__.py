# -*- coding: utf-8 -*-
"""拍卖之王 —— 框架无关的核心层（位于 BidKing 包内）。

本目录的源码 MUST NOT 导入 `maa`、`custom.action`、`utils`、`perceive`、`capture`
等与自动化框架或 agent 运行时相关的模块；它只依赖标准库与自身模块。

回放不能走 `custom.action.BidKing.domain` 这种包路径导入：那会先执行
`custom/action/__init__.py`，注册全部自定义动作并加载 MaaFramework，使回放
继承实机的管理员依赖。`tools/replay.py` 的做法是把 `BidKing/` 加入
`sys.path` 首位，以顶层包导入 `domain.*`，从而不触发动作注册、不加载框架。

因此本目录必须自包含：内部只用单点/双点相对导入，不能 `from ...utils`
或 `from utils...`（后者还会被同目录的 `BidKing/utils.py` 遮蔽）。
分层检查见 `tools/check_layering.py`（静态扫描 + 运行时导入断言）。
"""

__all__ = ["contracts", "catalog"]
