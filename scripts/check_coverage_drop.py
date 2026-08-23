#!/usr/bin/env python3
"""Fail CI if PR coverage drops more than --max-drop percentage points
versus the PR's base branch. Tolerant of a missing base coverage file
(e.g. the base branch predates coverage tooling) - in that case it warns
and exits 0, since the 80% floor check (a separate CI step) already
guards the absolute minimum.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _read_percent(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data["totals"]["percent_covered"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head", required=True, type=Path)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--max-drop", required=True, type=float)
    args = parser.parse_args()

    head_pct = _read_percent(args.head)
    if head_pct is None:
        print(f"::error::Could not read head coverage from {args.head}")
        return 1

    base_pct = _read_percent(args.base)
    if base_pct is None:
        print(
            "::warning::No base-branch coverage available (base branch may predate "
            "coverage tooling) - skipping the drop check, only the 80% floor applies."
        )
        return 0

    drop = base_pct - head_pct
    print(f"Base coverage: {base_pct:.2f}%  Head coverage: {head_pct:.2f}%  Drop: {drop:.2f}pp")

    if drop > args.max_drop:
        print(
            f"::error::Coverage dropped by {drop:.2f} percentage points, "
            f"more than the allowed {args.max_drop}."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
