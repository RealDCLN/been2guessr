"""Core data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Place:
    """A visited place from a BeenEverywhere map."""

    index: int
    lat: float
    lon: float
    name: str | None = None
    country_code: str | None = None

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        return f"{self.lat:.4f}, {self.lon:.4f}"


@dataclass(slots=True)
class Pano:
    """A Street View panorama (official or third-party)."""

    id: str
    lat: float
    lon: float
    source: str | None = None
    country_code: str | None = None
    date: str | None = None
    address: list[str] = field(default_factory=list)
    third_party: bool = False

    # Populated by the selector.
    distance_m: float = 0.0
    score: float = 0.0
    place_index: int | None = None
    place_label: str | None = None


@dataclass(slots=True)
class BuildOptions:
    """Knobs for a map build."""

    count: int = 300
    max_radius_m: float = 1600.0
    min_spacing_m: float = 100.0
    per_place_min: int = 1
    per_place_max: int = 8
    include_photospheres: bool = True
    official_only: bool = False
    prefer_recent: bool = True
    seed: int | None = None
    concurrency: int = 12
    pool_size: int = 14

    def validate(self) -> None:
        if not 1 <= self.count <= 10_000:
            raise ValueError("count must be between 1 and 10000")
        if not 0 <= self.max_radius_m <= 100_000:
            raise ValueError("max_radius_m must be between 0 and 100000")
        if not 0 <= self.min_spacing_m <= 100_000:
            raise ValueError("min_spacing_m must be between 0 and 100000")
        if not 0 <= self.per_place_min <= 100:
            raise ValueError("per_place_min must be between 0 and 100")
        if not 0 <= self.per_place_max <= 200:
            raise ValueError("per_place_max must be between 0 and 200")
        if self.per_place_max < self.per_place_min:
            raise ValueError("per_place_max must be >= per_place_min")
        if not 1 <= self.concurrency <= 64:
            raise ValueError("concurrency must be between 1 and 64")
        if not 1 <= self.pool_size <= 60:
            raise ValueError("pool_size must be between 1 and 60")


@dataclass(slots=True)
class Progress:
    """A single progress update emitted by the pipeline."""

    stage: str
    current: int = 0
    total: int = 0
    message: str = ""


@dataclass(slots=True)
class BuildStats:
    """Summary of a finished build."""

    requested: int
    produced: int
    places_total: int
    places_covered: int
    official: int
    third_party: int
    countries: dict[str, int]
    skipped_places: list[str]
    warnings: list[str]
