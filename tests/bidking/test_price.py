from core.util import extract_price, to_positive_int


def test_thousands_with_comma():
    assert extract_price("8,055") == 8055


def test_dot_as_thousands_separator():
    assert extract_price("14.346") == 14346


def test_plain_small_price():
    assert extract_price("91") == 91
    assert extract_price("0") == 0


def test_prompt_text_is_rejected():
    assert extract_price("可输入范围0~2,524,741") is None


def test_compact_notation_is_rejected():
    assert extract_price("1.23M") is None


def test_to_positive_int():
    assert to_positive_int("5000") == 5000
    assert to_positive_int(5000) == 5000
    assert to_positive_int("0") is None
    assert to_positive_int("-3") is None
    assert to_positive_int("abc") is None
    assert to_positive_int(None) is None
