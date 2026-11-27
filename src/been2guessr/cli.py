"""Command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import __version__
from .beeneverywhere import BeenEverywhereError, parse_source
from .geoguessr import filename, to_array, to_csv, to_geoguessr
from .models import BuildOptions, Progress
from .panos import PanoError
from .pipeline import build_from_file, build_from_source, summarize


def _printer(quiet: bool):
    def progress(update: Progress) -> None:
        if quiet:
            return
        if update.stage in ("places", "panoramas"):
            if update.current == update.total or update.current % 10 == 0:
                print(f"  [{update.current:>4}/{update.total}] {update.message}", flush=True)
        elif update.stage in ("selecting", "done"):
            print(f"  {update.message}", flush=True)

    return progress


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", nargs="?", help="BeenEverywhere username or profile URL")
    parser.add_argument("--input", metavar="FILE", help="Use a saved /query-visits JSON file instead")
    parser.add_argument("-n", "--count", type=int, default=300, help="Locations to generate (default: 300)")
    parser.add_argument(
        "--max-radius",
        type=float,
        default=1600,
        metavar="M",
        help="Search radius around each visited place in metres (default: 1600)",
    )
    parser.add_argument(
        "--min-spacing",
        type=float,
        default=100,
        metavar="M",
        help="Minimum distance between selected panoramas in metres (default: 100)",
    )
    parser.add_argument("--per-place-min", type=int, default=1, help="Minimum locations per visited place")
    parser.add_argument("--per-place-max", type=int, default=8, help="Maximum locations per visited place")
    parser.add_argument("--official-only", action="store_true", help="Never use user photospheres")
    parser.add_argument(
        "--no-photospheres",
        action="store_true",
        help="Alias for --official-only",
    )
    parser.add_argument(
        "--no-recent-bias",
        action="store_true",
        help="Do not prefer newer captures",
    )
    parser.add_argument("--seed", type=int, help="Seed for starting headings (reproducible output)")
    parser.add_argument("--concurrency", type=int, default=12, help="Parallel request limit (default: 12)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Only print the final summary")


def _options(args: argparse.Namespace) -> BuildOptions:
    return BuildOptions(
        count=args.count,
        max_radius_m=args.max_radius,
        min_spacing_m=args.min_spacing,
        per_place_min=args.per_place_min,
        per_place_max=args.per_place_max,
        include_photospheres=not (args.official_only or args.no_photospheres),
        official_only=args.official_only or args.no_photospheres,
        prefer_recent=not args.no_recent_bias,
        seed=args.seed,
        concurrency=args.concurrency,
    )


def _write_outputs(args: argparse.Namespace, result, output: Path) -> None:
    payload = to_array(result) if args.array else to_geoguessr(result, seed=args.seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.csv:
        csv_path = output.with_suffix(".csv")
        csv_path.write_text(to_csv(result), encoding="utf-8")
        print(f"  report: {csv_path}")


def _print_summary(args: argparse.Namespace, result, output: Path) -> None:
    summary = summarize(result)
    print()
    print(f"  Map:             {output}")
    print(f"  Locations:       {summary['produced']} / {summary['requested']} requested")
    print(f"  Places covered:  {summary['places_covered']} / {summary['places_total']}")
    print(f"  Official:        {summary['official']}")
    print(f"  Photospheres:    {summary['third_party']}")
    if summary["countries"]:
        countries = ", ".join(f"{code} {count}" for code, count in summary["countries"].items())
        print(f"  Countries:       {countries}")
    for warning in summary["warnings"]:
        print(f"  ! {warning}")
    print()
    print("  Import it in the GeoGuessr map editor with 'Import locations'.")
    print("  If the editor wants a bare list, rerun with --array.")


def cmd_build(args: argparse.Namespace) -> int:
    if bool(args.source) == bool(args.input):
        print("error: provide either a username/URL or --input (not both)", file=sys.stderr)
        return 2

    options = _options(args)
    try:
        options.validate()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    progress = _printer(args.quiet)
    print("been2guessr " + __version__)

    try:
        if args.input:
            result = asyncio.run(build_from_file(args.input, options, progress=progress))
        else:
            username, _ = parse_source(args.source)
            print(f"  map: {username}")
            result = asyncio.run(build_from_source(args.source, options, progress=progress))
    except (BeenEverywhereError, PanoError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    if not result.panos:
        print("error: no locations could be built", file=sys.stderr)
        return 1

    output = Path(args.output) if args.output else Path(filename(result.username, len(result.panos)))
    _write_outputs(args, result, output)
    _print_summary(args, result, output)
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    from .beeneverywhere import fetch_map, load_map_file

    try:
        if args.input:
            places = load_map_file(args.input)
            username = Path(args.input).stem
            payload = {}
        else:
            username, places, payload = fetch_map(args.source)
    except (BeenEverywhereError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"User:    {username}")
    print(f"Places:  {len(places)}")
    stats = payload.get("stats") or {}
    if stats.get("places_visited"):
        print(f"Visited: {stats['places_visited']} (BeenEverywhere)")
    if stats.get("un"):
        countries = ", ".join(f"{code} {count}" for code, count in stats["un"].items())
        print(f"UN:      {countries}")
    if stats.get("most_nothern"):
        n = stats["most_nothern"]
        print(f"North:   {n.get('name')} ({n.get('lat'):.4f}, {n.get('lon'):.4f})")
    if stats.get("most_southern"):
        s = stats["most_southern"]
        print(f"South:   {s.get('name')} ({s.get('lat'):.4f}, {s.get('lon'):.4f})")
    print()
    print("First 10 places:")
    for place in places[:10]:
        print(f"  {place.index + 1:>3}. {place.lat:.5f}, {place.lon:.5f}")
    if len(places) > 10:
        print(f"  ... and {len(places) - 10} more")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("error: web dependencies are missing; run: pip install fastapi uvicorn", file=sys.stderr)
        return 1

    uvicorn.run(
        "been2guessr.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="been2guessr",
        description="Turn a BeenEverywhere travel map into a GeoGuessr custom map.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build a GeoGuessr JSON file")
    _add_common(build)
    build.add_argument("-o", "--output", help="Output JSON path")
    build.add_argument("--csv", action="store_true", help="Also write a CSV report")
    build.add_argument(
        "--array",
        action="store_true",
        help="Write a bare location array instead of the map object",
    )
    build.set_defaults(func=cmd_build)

    inspect = subparsers.add_parser("inspect", help="Show a map's places without building")
    inspect.add_argument("source", nargs="?", help="BeenEverywhere username or profile URL")
    inspect.add_argument("--input", metavar="FILE", help="Use a saved /query-visits JSON file")
    inspect.set_defaults(func=cmd_inspect)

    serve = subparsers.add_parser("serve", help="Run the web UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "inspect" and not args.source and not args.input:
        parser.error("inspect needs a username/URL or --input")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
