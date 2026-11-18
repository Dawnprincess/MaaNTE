from sources.live import state
from sources.live.state import PendingBid


def test_take_pending_clears_once():
    state.reset()
    state.set_pending(PendingBid(8055, "fixed", "fixed"))
    assert state.take_pending().amount == 8055
    assert state.take_pending() is None


def test_begin_round_clears_pending_but_keeps_last_bid():
    state.reset()
    state.set_pending(PendingBid(8055, "fixed", "fixed"))
    state.set_last_bid(12000)

    state.begin_round()

    assert state.take_pending() is None
    assert state.last_bid() == 12000
    state.reset()
