from core.contracts import Event, Item, Meta, Observation, Session, Settlement


def test_session_round_trip():
    observation = Observation(
        round=3,
        valuation=110675,
        balance=10496619,
        countdown=39,
        last_bid=1,
        decision=110675,
        public_events=[Event(kind="intel", data={"text": "紫色占格 11"}, source="intel")],
        private_events=[
            Event(kind="shape", data={"pos": [1, 2], "shape": [2, 3]}, source="skill")
            for _ in range(6)
        ],
        public_bids=[None, 550000, 450000, 1],
    )
    observation.extra = {"unknown_obs": {"a": 1}}

    settlement = Settlement(
        value=500000,
        items=[
            Item(
                name="测试物品",
                quality="红",
                shape=(1, 1),
                price=500000,
                type="宝石类",
                pos=(0, 0),
            )
        ],
        outcome="deal",
        price=110675,
    )
    session = Session(
        meta=Meta(
            strategy="lower_bound",
            package_tendency="完整的保险箱",
            model_versions={"valuation": "v0"},
        ),
        rounds=[observation],
        settlement=settlement,
        extra={"unknown_session": True},
    )

    restored = Session.from_dict(session.to_dict())

    assert restored == session
    assert restored.rounds[0].extra["unknown_obs"] == {"a": 1}
    assert restored.extra["unknown_session"] is True


def test_unknown_event_kind_preserved():
    event = Event(kind="future_kind", data={"x": 1}, source="instrument")
    restored = Event.from_dict(event.to_dict())
    assert restored == event


def test_meta_defaults():
    meta = Meta()
    assert meta.schema_version == 1
    assert meta.source == "live"
    assert meta.instruments == []
    assert meta.strategy_param == {}
    assert meta.model_versions == {}


def test_observation_defaults():
    observation = Observation()
    assert observation.round is None
    assert observation.valuation is None
    assert observation.public_events == []
    assert observation.private_events == []
    assert observation.public_bids == []
    assert observation.decision is None
