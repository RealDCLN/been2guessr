from been2guessr.models import BuildOptions, Pano
from been2guessr.selector import _spread_pool, allocate_targets, select_global


def make_panos(place: int, count: int, *, start_lat: float | None = None, step: float = 0.01) -> list[Pano]:
    base = 40.0 + place * 1.0 if start_lat is None else start_lat
    return [Pano(id=f"P{place}-{i}", lat=base + i * step, lon=20.0) for i in range(count)]


def test_allocate_balances_and_redistributes():
    targets = allocate_targets({0: 10, 1: 2, 2: 0}, 5, 1, 3)
    assert sum(targets.values()) == 5
    assert targets[0] == 3
    assert targets[1] == 2
    assert 2 not in targets


def test_allocate_small_count_picks_strongest_places():
    targets = allocate_targets({0: 10, 1: 8, 2: 3}, 2, 1, 3)
    assert targets == {0: 1, 1: 1}


def test_allocate_handles_zero_and_impossible():
    assert allocate_targets({0: 10}, 0, 1, 3) == {}
    assert sum(allocate_targets({0: 2, 1: 1}, 100, 1, 8).values()) == 3


def test_select_global_spreads_across_places():
    ranked = {index: make_panos(index, 5) for index in range(3)}
    targets = allocate_targets({index: 5 for index in range(3)}, 6, 1, 3)
    selected = select_global(ranked, targets, 6, 50, 3)
    assert len(selected) == 6
    assert len({pano.id for pano in selected}) == 6
    counts = {index: sum(1 for pano in selected if pano.id.startswith(f"P{index}-")) for index in range(3)}
    assert counts == {0: 2, 1: 2, 2: 2}


def test_select_global_respects_spacing():
    ranked = {
        0: [Pano(id="A", lat=40.0, lon=20.0)],
        1: [Pano(id="B", lat=40.000001, lon=20.0)],
    }
    targets = {0: 1, 1: 1}
    selected = select_global(ranked, targets, 2, 100, 2)
    assert len(selected) == 1


def test_select_global_never_duplicates_ids():
    same = Pano(id="SAME", lat=40.0, lon=20.0)
    ranked = {0: [same], 1: [same]}
    selected = select_global(ranked, {0: 1, 1: 1}, 2, 0, 2)
    assert len(selected) == 1


def test_spread_pool_avoids_clustered_panos():
    cluster = [Pano(id=f"C{i}", lat=35.0, lon=24.0) for i in range(20)]
    options = BuildOptions(pool_size=14)
    assert len(_spread_pool(cluster, options)) == 1


def test_spread_pool_keeps_distinct_panos():
    panos = [Pano(id=f"D{i}", lat=35.0 + i * 0.01, lon=24.0) for i in range(10)]
    options = BuildOptions(pool_size=14)
    assert len(_spread_pool(panos, options)) == 10
