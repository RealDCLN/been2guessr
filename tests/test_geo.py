from been2guessr.geo import box_tiles, haversine_m, ring_tiles, tile_xy


def test_haversine_one_degree():
    distance = haversine_m(0.0, 0.0, 0.0, 1.0)
    assert 110_000 < distance < 112_000


def test_haversine_is_zero_for_same_point():
    assert haversine_m(35.0, 24.0, 35.0, 24.0) == 0


def test_tile_coordinates():
    assert tile_xy(0, 0, 0) == (0, 0)
    assert tile_xy(0, 0, 1) == (1, 1)
    assert tile_xy(0, 0, 17) == (65536, 65536)


def test_ring_and_box_tiles():
    assert ring_tiles(10, 10, 0) == [(10, 10)]
    assert len(ring_tiles(10, 10, 1)) == 8
    assert len(ring_tiles(10, 10, 2)) == 16
    assert len(box_tiles(10, 10, 1)) == 9
