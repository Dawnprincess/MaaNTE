# -*- coding: utf-8 -*-
"""拍卖之王 —— 对局观测契约（核心层，零框架依赖）

本模块只描述「一局对局留下了什么」，不关心它来自实机、回放还是模拟器。
所有结构都能无损往返 JSON，便于落盘与回放。

可见性三分（见 openspec design D2）：

    公开 public   ：拍卖师情报、对手出价（天黑场为名次）
    私有 private  ：角色技能揭示的内容、仪器结果、点击轮廓查到的类型
    自身 self     ：自己的资产、上轮出价、本轮决策（是「已知」，不是「揭示」）

`Observation` 是旧 `RoundSnapshot` 的超集：前五个字段同名同义，
因此现有策略代码不需要改动。
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Optional

# 会话格式版本；新增字段时递增，读取方按已知字段解析并保留未知字段。
SCHEMA_VERSION = 1

# Event.source 的取值，仅作约定，不做强校验
SOURCE_INTEL = "intel"  # 拍卖师情报
SOURCE_SKILL = "skill"  # 角色技能
SOURCE_INSTRUMENT = "instrument"  # 仪器
SOURCE_DERIVED = "derived"  # 由操作派生（如点击轮廓查类型）


@dataclass
class Event:
    """一条证据：游戏在某一刻告诉了你什么。

    0a 只定义信封；具体 kind 与 data 字段在下一变更（感知提取）中确定。
    未知 kind 与未知字段原样保留，保证旧回放能读新数据。
    """

    kind: str
    data: dict[str, Any] = dc_field(default_factory=dict)
    source: str = SOURCE_INTEL

    def to_dict(self) -> dict:
        return {"kind": self.kind, "data": dict(self.data), "source": self.source}

    @classmethod
    def from_dict(cls, raw: dict) -> "Event":
        return cls(
            kind=str(raw.get("kind", "")),
            data=dict(raw.get("data") or {}),
            source=str(raw.get("source") or SOURCE_INTEL),
        )


@dataclass
class Observation:
    """一回合的观测。

    前五个字段沿用 `RoundSnapshot` 的含义；新增字段只增加信息，不改变旧语义。
    """

    # ---- 帧解析/界面读数（与 RoundSnapshot 一致）----
    round: Optional[int] = None
    valuation: Optional[int] = None
    balance: Optional[int] = None
    countdown: Optional[int] = None

    # ---- 自身记录 ----
    last_bid: Optional[int] = None

    # ---- 揭示（按可见性分开）----
    public_events: list[Event] = dc_field(default_factory=list)
    private_events: list[Event] = dc_field(default_factory=list)

    # ---- 对手出价；天黑场为 None，只留名次 ----
    public_bids: list[Optional[int]] = dc_field(default_factory=list)

    # ---- 本轮决策（实机写入；回放用于比对）----
    decision: Optional[int] = None

    # 未知字段原样保留（前向兼容）
    extra: dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "round": self.round,
            "valuation": self.valuation,
            "balance": self.balance,
            "countdown": self.countdown,
            "last_bid": self.last_bid,
            "public_events": [e.to_dict() for e in self.public_events],
            "private_events": [e.to_dict() for e in self.private_events],
            "public_bids": list(self.public_bids),
            "decision": self.decision,
        }
        payload.update(self.extra)
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> "Observation":
        known = {
            "round",
            "valuation",
            "balance",
            "countdown",
            "last_bid",
            "public_events",
            "private_events",
            "public_bids",
            "decision",
        }
        extra = {k: v for k, v in raw.items() if k not in known}
        return cls(
            round=_opt_int(raw.get("round")),
            valuation=_opt_int(raw.get("valuation")),
            balance=_opt_int(raw.get("balance")),
            countdown=_opt_int(raw.get("countdown")),
            last_bid=_opt_int(raw.get("last_bid")),
            public_events=[Event.from_dict(e) for e in raw.get("public_events") or []],
            private_events=[Event.from_dict(e) for e in raw.get("private_events") or []],
            public_bids=[_opt_int(b) for b in raw.get("public_bids") or []],
            decision=_opt_int(raw.get("decision")),
            extra=extra,
        )


@dataclass(frozen=True)
class Item:
    """物品表 / 结算清单中的一件物品。"""

    name: str
    quality: str
    shape: tuple[int, int]
    price: int
    type: Optional[str] = None
    pos: Optional[tuple[int, int]] = None  # (列, 行)

    def to_dict(self) -> dict:
        data = {
            "name": self.name,
            "quality": self.quality,
            "shape": list(self.shape),
            "price": self.price,
        }
        if self.type is not None:
            data["type"] = self.type
        if self.pos is not None:
            data["pos"] = list(self.pos)
        return data

    @classmethod
    def from_dict(cls, raw: dict) -> "Item":
        shape = raw.get("shape") or (0, 0)
        pos = raw.get("pos")
        return cls(
            name=str(raw.get("name", "")),
            quality=str(raw.get("quality", "")),
            shape=(int(shape[0]), int(shape[1])),
            price=int(raw.get("price", 0)),
            type=raw.get("type"),
            pos=(int(pos[0]), int(pos[1])) if pos else None,
        )


@dataclass
class Settlement:
    """结算真值（上帝视角，不进入对局观测）。"""

    value: int
    items: list[Item] = dc_field(default_factory=list)
    outcome: str = "deal"  # deal | unsold
    price: Optional[int] = None
    extra: dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "value": self.value,
            "items": [i.to_dict() for i in self.items],
            "outcome": self.outcome,
            "price": self.price,
        }
        payload.update(self.extra)
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> "Settlement":
        known = {"value", "items", "outcome", "price"}
        extra = {k: v for k, v in raw.items() if k not in known}
        return cls(
            value=int(raw.get("value", 0)),
            items=[Item.from_dict(i) for i in raw.get("items") or []],
            outcome=str(raw.get("outcome", "deal")),
            price=_opt_int(raw.get("price")),
            extra=extra,
        )


@dataclass
class Meta:
    """一局对局的元数据。"""

    schema_version: int = SCHEMA_VERSION
    source: str = "live"  # live | sim
    venue: Optional[str] = None
    field: Optional[str] = None
    character: Optional[str] = None
    instruments: list[str] = dc_field(default_factory=list)
    strategy: Optional[str] = None
    strategy_param: dict[str, Any] = dc_field(default_factory=dict)
    started_at: Optional[str] = None
    resolution: Optional[list[int]] = None
    extra: dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "venue": self.venue,
            "field": self.field,
            "character": self.character,
            "instruments": list(self.instruments),
            "strategy": self.strategy,
            "strategy_param": dict(self.strategy_param),
            "started_at": self.started_at,
            "resolution": list(self.resolution) if self.resolution else None,
        }
        payload.update(self.extra)
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> "Meta":
        known = {
            "schema_version",
            "source",
            "venue",
            "field",
            "character",
            "instruments",
            "strategy",
            "strategy_param",
            "started_at",
            "resolution",
        }
        extra = {k: v for k, v in raw.items() if k not in known}
        resolution = raw.get("resolution")
        return cls(
            schema_version=int(raw.get("schema_version", SCHEMA_VERSION)),
            source=str(raw.get("source", "live")),
            venue=raw.get("venue"),
            field=raw.get("field"),
            character=raw.get("character"),
            instruments=list(raw.get("instruments") or []),
            strategy=raw.get("strategy"),
            strategy_param=dict(raw.get("strategy_param") or {}),
            started_at=raw.get("started_at"),
            resolution=[int(x) for x in resolution] if resolution else None,
            extra=extra,
        )


@dataclass
class Session:
    """一局对局：元数据 + 逐轮观测 + 可选结算真值。"""

    meta: Meta
    rounds: list[Observation] = dc_field(default_factory=list)
    settlement: Optional[Settlement] = None
    extra: dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "meta": self.meta.to_dict(),
            "rounds": [r.to_dict() for r in self.rounds],
            "settlement": self.settlement.to_dict() if self.settlement else None,
        }
        payload.update(self.extra)
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> "Session":
        known = {"meta", "rounds", "settlement"}
        extra = {k: v for k, v in raw.items() if k not in known}
        settlement = raw.get("settlement")
        return cls(
            meta=Meta.from_dict(raw.get("meta") or {}),
            rounds=[Observation.from_dict(r) for r in raw.get("rounds") or []],
            settlement=Settlement.from_dict(settlement) if settlement else None,
            extra=extra,
        )


def _opt_int(value: Any) -> Optional[int]:
    """把 JSON 中的数字安全转成 int；None/空串/非法值一律当 None。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
