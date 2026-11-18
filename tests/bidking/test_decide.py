import core.policy as policy
from core.contracts import Observation
from core.decide import decide


def test_lower_bound_reads_valuation():
    decision = decide(Observation(valuation=8055), "lower_bound")
    assert decision.amount == 8055
    assert decision.reason == "lower_bound"


def test_valuation_alias_is_equivalent():
    observation = Observation(valuation=8055)
    assert decide(observation, "valuation").amount == decide(
        observation, "lower_bound"
    ).amount


def test_unknown_strategy_falls_back_to_default():
    decision = decide(Observation(valuation=8055), "does_not_exist")
    assert decision.amount == 1
    assert decision.reason == "fixed"


def test_zero_valuation_falls_back_to_one():
    decision = decide(Observation(valuation=0), "lower_bound")
    assert decision.amount == 1
    assert decision.reason == "lower_bound_zero"


def test_unreadable_valuation_uses_last_bid():
    decision = decide(Observation(valuation=None, last_bid=12000), "lower_bound")
    assert decision.amount == 12000
    assert decision.reason == "lower_bound_last_bid"


def test_unreadable_valuation_without_history_uses_one():
    decision = decide(Observation(valuation=None, last_bid=None), "lower_bound")
    assert decision.amount == 1
    assert decision.reason == "lower_bound_fallback_one"


def test_strategy_exception_falls_back_to_one():
    def boom(observation, params):
        raise RuntimeError("boom")

    policy.STRATEGIES["__boom__"] = boom
    try:
        decision = decide(Observation(valuation=8055), "__boom__")
    finally:
        policy.STRATEGIES.pop("__boom__", None)

    assert decision.amount == 1
    assert decision.reason == "observe_error"


def test_invalid_result_falls_back_to_one():
    def invalid(observation, params):
        return None

    policy.STRATEGIES["__invalid__"] = invalid
    try:
        decision = decide(Observation(valuation=8055), "__invalid__")
    finally:
        policy.STRATEGIES.pop("__invalid__", None)

    assert decision.amount == 1
    assert decision.reason == "observe_error"
