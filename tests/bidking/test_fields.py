from core.util import parse_countdown, parse_round


def test_parse_round_accepts_whole_sentence():
    assert parse_round("竞拍第3回合") == 3
    assert parse_round("竞拍第 3 回合") == 3
    assert parse_round("第1回合") == 1
    assert parse_round("竞拍第12回合") == 12


def test_parse_round_rejects_other_text():
    assert parse_round("共12件藏品") is None
    assert parse_round("回合3") is None
    assert parse_round("竞拍第3回合 剩余39秒") is None
    assert parse_round("") is None
    assert parse_round(None) is None


def test_parse_countdown_accepts_mm_ss():
    assert parse_countdown("00:39") == 39
    assert parse_countdown("1:05") == 65
    assert parse_countdown("00：39") == 39
    assert parse_countdown("00 : 39") == 39
    assert parse_countdown("0:0") == 0


def test_parse_countdown_rejects_invalid():
    assert parse_countdown("00:75") is None
    assert parse_countdown("39") is None
    assert parse_countdown("100:00") is None
    assert parse_countdown("") is None
    assert parse_countdown(None) is None
