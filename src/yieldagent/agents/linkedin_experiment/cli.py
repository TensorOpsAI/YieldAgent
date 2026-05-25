"""CLI entry point for the LinkedIn experiment agent.

Usage::

    python -m yieldagent.agents.linkedin_experiment \\
        --creative urn:li:sponsoredCreative:111 \\
        --creative urn:li:sponsoredCreative:222 \\
        --start 2026-05-01 --end 2026-05-21 \\
        --metric ctr --min-impressions 1000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date

from .graph import ExperimentConfig, run_experiment


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Date must be ISO YYYY-MM-DD: {value!r}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="linkedin-experiment",
        description=(
            "Rank LinkedIn creative variants over an evaluation window and emit "
            "a pause/scale recommendation."
        ),
    )
    parser.add_argument(
        "--creative",
        dest="creatives",
        action="append",
        required=True,
        help="Creative URN (urn:li:sponsoredCreative:...) — repeat for each variant.",
    )
    parser.add_argument("--start", type=_parse_date, required=True, help="ISO date YYYY-MM-DD")
    parser.add_argument("--end", type=_parse_date, required=True, help="ISO date YYYY-MM-DD")
    parser.add_argument(
        "--metric",
        choices=("ctr", "cpc", "cpl"),
        default="ctr",
        help="Primary scoring metric. CTR ranks descending; CPC/CPL rank ascending.",
    )
    parser.add_argument(
        "--min-impressions",
        type=int,
        default=1000,
        help="Variants below this impressions floor are held as 'needs_data'.",
    )
    args = parser.parse_args(argv)

    config = ExperimentConfig(
        creative_urns=args.creatives,
        date_start=args.start,
        date_end=args.end,
        primary_metric=args.metric,
        min_impressions=args.min_impressions,
    )
    result = asyncio.run(run_experiment(config))
    json.dump(result.to_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
