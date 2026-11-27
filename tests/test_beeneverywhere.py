import json

import pytest

from been2guessr.beeneverywhere import BeenEverywhereError, load_map_json, parse_source


def test_parse_plain_username():
    assert parse_source("example-user") == ("example-user", None)
    assert parse_source("@example-user") == ("example-user", None)


def test_parse_profile_url():
    assert parse_source("https://beeneverywhere.net/user/example-user") == ("example-user", None)
    assert parse_source("beeneverywhere.net/user/example-user/") == ("example-user", None)


def test_parse_url_with_secret():
    username, secret = parse_source("https://beeneverywhere.net/user/example-user?secret=abc123")
    assert username == "example-user"
    assert secret == "abc123"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://example.com/user/foo",
        "user name",
        "foo/bar",
        "a" * 65,
    ],
)
def test_parse_invalid(value):
    with pytest.raises(BeenEverywhereError):
        parse_source(value)


def test_load_geojson_and_dedupe():
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"geometry": {"coordinates": [20.0, 10.0]}},
            {"geometry": {"coordinates": [20.0, 10.0]}},
            {"geometry": {"coordinates": [21.0, 11.0]}},
        ],
    }
    places = load_map_json(json.dumps(payload))
    assert len(places) == 2
    assert places[0].lat == 10.0
    assert places[0].lon == 20.0
    assert places[1].index == 1


def test_load_invalid_payload():
    with pytest.raises(BeenEverywhereError):
        load_map_json(json.dumps({"type": "Feature"}))
    with pytest.raises(BeenEverywhereError):
        load_map_json("not json")
