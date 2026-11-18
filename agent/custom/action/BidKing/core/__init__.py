# -*- coding: utf-8 -*-
"""拍卖之王 —— 框架无关的核心层（位于 BidKing 包内）。

本目录的源码 MUST NOT 导入 `maa`、`custom.action`、`utils` 或 `sources.live`
等与自动化框架或 agent 运行时相关的模块；它只依赖标准库与自身模块。

回放不能走 `custom.action.BidKing.core` 这种包路径导入：那会先执行
`custom/action/__init__.py`，注册全部自定义动作并加载 MaaFramework，使回放
继承实机的管理员依赖。`tools/replay.py` 的做法是把 `BidKing/` 加入
`sys.path` 首位，以顶层包导入 `core.*` 与 `sources.replay`，从而不触发
动作注册、不加载框架。

因此本目录必须自包含：内部只用单点/双点相对导入，不能 `from ...` 跳出
`core`，也不能 `from utils...`（那是 agent 运行时）。
分层检查见 `tools/check_layering.py`（静态扫描 + 运行时导入断言）。
"""

__all__ = ["catalog", "contracts", "decide", "policy", "session", "util"]
