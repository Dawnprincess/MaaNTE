from collections import defaultdict

import pytest

from core.catalog import Catalog


@pytest.fixture(scope="module")
def catalog():
    return Catalog.load()


def test_item_count(catalog):
    assert len(catalog) == 227


def test_shape_and_quality(catalog):
    candidates = catalog.candidates(shape=(1, 1), quality="红")
    assert len(candidates) == 4
    assert all(item.shape == (1, 1) and item.quality == "红" for item in candidates)


def test_shape_quality_combinations(catalog):
    combos = defaultdict(list)
    for item in catalog.items:
        combos[(item.shape, item.quality)].append(item)

    assert len(combos) == 65
    assert sum(1 for items in combos.values() if len(items) == 1) == 23


def test_unknown_condition_returns_empty(catalog):
    assert catalog.candidates(shape=(99, 99)) == []


def test_by_type(catalog):
    candidates = catalog.candidates(item_type="宝石类")
    assert candidates
    assert all(item.type == "宝石类" for item in candidates)
