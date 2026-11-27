from been2guessr.panos import (
    _metadata_url,
    is_third_party_panoid,
    parse_coverage_tile,
    parse_find_response,
    parse_metadata_response,
    to_protobuf_url,
)


def test_third_party_detection():
    assert is_third_party_panoid("CIHM0ogKEICAgIDE0viwSQ")
    assert is_third_party_panoid("AF1QipNxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    assert not is_third_party_panoid("ABCDEFGHIJKLMNOPQRSTUV")


def test_protobuf_url_builder():
    assert to_protobuf_url({1: {1: "x"}}) == "!1m1!1sx"
    assert to_protobuf_url({3: {1: True}}) == "!3m1!1b1"


def test_metadata_url_contains_panoid():
    url = _metadata_url("ABCDEFGHIJKLMNOPQRSTUV")
    assert url.startswith("https://www.google.com/maps/photometa/v1?")
    assert "ABCDEFGHIJKLMNOPQRSTUV" in url


def _message() -> list:
    return [
        [1],
        [None, "PANO123"],
        None,
        [None, None, [["1 Example St", "en"], ["Example City", "en"]]],
        None,
        [[None, [[None, None, 10.0, 20.0], None, None, None, "FR"]]],
        [None, None, None, None, None, [None, None, "launch"], None, [2024, 5]],
    ]


def test_parse_metadata_response():
    payload = [None, [_message()]]
    pano = parse_metadata_response(payload)
    assert pano is not None
    assert pano.id == "PANO123"
    assert pano.lat == 10.0
    assert pano.lon == 20.0
    assert pano.country_code == "FR"
    assert pano.source == "launch"
    assert pano.date == "2024-05"
    assert pano.address == ["1 Example St", "Example City"]
    assert pano.third_party is False


def test_parse_metadata_not_found():
    assert parse_metadata_response([None, [[[2]]]]) is None


def test_parse_find_response():
    payload = [[0], _message()]
    pano = parse_find_response(payload)
    assert pano is not None and pano.id == "PANO123"
    assert parse_find_response([[5], None]) is None


def test_parse_coverage_tile():
    raw = [[[None, "PANO123"], None, [[None, None, 10.0, 20.0]]]]
    payload = [None, [None, [raw]]]
    panos = parse_coverage_tile(payload)
    assert len(panos) == 1
    assert panos[0].id == "PANO123"
    assert panos[0].lat == 10.0
    assert panos[0].lon == 20.0


def test_parse_empty_coverage_tile():
    assert parse_coverage_tile([None, None]) == []
