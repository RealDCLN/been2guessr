import csv
import io

from been2guessr.geoguessr import filename, to_array, to_csv, to_geoguessr
from been2guessr.models import BuildStats, Pano
from been2guessr.selector import BuildResult


def make_result() -> BuildResult:
    panos = [
        Pano(id="PANO000000000000000001", lat=10.0, lon=20.0, country_code="FR"),
        Pano(id="PANO000000000000000002", lat=11.0, lon=21.0, country_code="FR"),
        Pano(id="CIHM0ogKEICAgIDE0viwSQ", lat=12.0, lon=22.0, country_code="FR", third_party=True),
    ]
    stats = BuildStats(
        requested=3,
        produced=3,
        places_total=3,
        places_covered=3,
        official=2,
        third_party=1,
        countries={"FR": 3},
        skipped_places=[],
        warnings=[],
    )
    return BuildResult(panos=panos, stats=stats, username="tester")


def test_geoguessr_shape():
    payload = to_geoguessr(make_result(), seed=7)
    assert payload["name"].startswith("tester")
    coords = payload["customCoordinates"]
    assert len(coords) == 3
    assert len({c["panoId"] for c in coords}) == 3
    for coord in coords:
        assert 0 <= coord["heading"] <= 359
        assert coord["pitch"] == 0
        assert coord["zoom"] == 0
        assert coord["stateCode"] is None
        assert isinstance(coord["lat"], float)


def test_seed_is_reproducible():
    first = to_geoguessr(make_result(), seed=42)
    second = to_geoguessr(make_result(), seed=42)
    assert first == second


def test_bare_array():
    assert len(to_array(make_result())) == 3


def test_csv_report():
    text = to_csv(make_result())
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "#"
    assert len(rows) == 4
    assert rows[1][2] == "FR"
    assert "\r\r" not in text


def test_filename_slug():
    assert filename("marin manos", 300) == "marin-manos-geoguessr-300.json"
    assert filename(None, 10, "csv") == "been2guessr-geoguessr-10.csv"
