from core.contracts import Item, Meta, Observation, Settlement
from core.session import append_observation, read_session, write_meta, write_settlement


def test_round_trip(tmp_path):
    write_meta(tmp_path, Meta(strategy="fixed", strategy_param={"price": 1}))
    append_observation(tmp_path, Observation(round=1, valuation=100, decision=1))
    append_observation(
        tmp_path,
        Observation(round=2, valuation=200, last_bid=1, decision=200),
    )

    session = read_session(tmp_path)

    assert session.meta.strategy == "fixed"
    assert session.meta.strategy_param == {"price": 1}
    assert session.meta.started_at
    assert [r.round for r in session.rounds] == [1, 2]
    assert session.rounds[1].last_bid == 1
    assert session.settlement is None


def test_bad_line_is_skipped(tmp_path):
    append_observation(tmp_path, Observation(round=1, decision=1))
    with open(tmp_path / "observations.jsonl", "a", encoding="utf-8") as handle:
        handle.write("not json\n")
    append_observation(tmp_path, Observation(round=2, decision=2))

    session = read_session(tmp_path)

    assert [r.round for r in session.rounds] == [1, 2]


def test_missing_files_are_tolerated(tmp_path):
    session = read_session(tmp_path / "missing")
    assert session.rounds == []
    assert session.settlement is None
    assert session.meta.schema_version == 1


def test_settlement_round_trip(tmp_path):
    settlement = Settlement(
        value=12345,
        items=[Item(name="物品", quality="金", shape=(2, 2), price=12345, pos=(3, 4))],
        outcome="deal",
        price=10000,
    )
    write_settlement(tmp_path, settlement)

    session = read_session(tmp_path)

    assert session.settlement == settlement
    assert session.settlement.items[0].pos == (3, 4)
