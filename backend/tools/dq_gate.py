#!/usr/bin/env python3
"""
Data Quality Gate for Cinemate

This is designed to run in CI/CD as a hard release gate.
It checks basic data contracts for the `recommendation_events` table:
- required columns exist
- minimum event volume (optional)
- freshness of served_at (optional)
- null-rate checks for key fields
- range checks for latency_ms and reward
- duplicate rate check on a simple event key
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import create_engine, text


REQUIRED_COLUMNS: tuple[str, ...] = (
    "user_id",
    "movie_id",
    "algorithm",
    "created_at",
    # Bandit/analytics fields that power the dashboard/guardrails
    "experiment_id",
    "policy",
    "arm_id",
    "p_score",
    "latency_ms",
    "reward",
    "served_at",
)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    message: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fail(msg: str) -> GateResult:
    return GateResult(ok=False, message=msg)


def _ok(msg: str) -> GateResult:
    return GateResult(ok=True, message=msg)


def _check_required_columns(conn) -> GateResult:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'recommendation_events'
            """
        )
    ).fetchall()

    if not rows:
        return _fail("recommendation_events table not found (or no access)")

    cols = {r[0] for r in rows}
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        return _fail(f"Missing required columns in recommendation_events: {missing}")
    return _ok("Required columns present")


def _count_events(conn, window_hours: int | None) -> int:
    if window_hours is None:
        return int(conn.execute(text("SELECT COUNT(*) FROM recommendation_events")).scalar() or 0)
    cutoff = _utcnow() - timedelta(hours=window_hours)
    return int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM recommendation_events
                WHERE created_at >= :cutoff
                """
            ),
            {"cutoff": cutoff},
        ).scalar()
        or 0
    )


def _check_min_events(conn, min_events: int, window_hours: int | None) -> GateResult:
    cnt = _count_events(conn, window_hours=window_hours)
    if cnt < min_events:
        scope = "all time" if window_hours is None else f"last {window_hours}h"
        return _fail(f"Event volume too low: {cnt} < {min_events} ({scope})")
    return _ok(f"Event volume ok: {cnt} >= {min_events}")


def _check_freshness(conn, max_age_minutes: int) -> GateResult:
    latest = conn.execute(
        text("SELECT MAX(served_at) FROM recommendation_events WHERE served_at IS NOT NULL")
    ).scalar()
    if latest is None:
        return _fail("Freshness check failed: no served_at values found")

    # SQLAlchemy returns naive datetime in many configs; treat as UTC.
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)

    age = _utcnow() - latest
    if age > timedelta(minutes=max_age_minutes):
        return _fail(f"Freshness check failed: newest served_at is {age} old (> {max_age_minutes}m)")
    return _ok(f"Freshness ok: newest served_at age {age}")


def _check_null_rates(conn, window_hours: int | None, max_null_pct: float) -> GateResult:
    where = ""
    params = {}
    if window_hours is not None:
        where = "WHERE created_at >= :cutoff"
        params["cutoff"] = _utcnow() - timedelta(hours=window_hours)

    total = int(conn.execute(text(f"SELECT COUNT(*) FROM recommendation_events {where}"), params).scalar() or 0)
    if total == 0:
        return _ok("Null-rate check skipped: no events in window")

    # Key fields we expect to be populated for experiment analytics
    fields = ["policy", "arm_id", "served_at"]
    failures: list[str] = []
    for f in fields:
        nulls = int(
            conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM recommendation_events
                    {where}
                      {"AND" if where else "WHERE"} {f} IS NULL
                    """
                ),
                params,
            ).scalar()
            or 0
        )
        pct = (nulls / total) * 100.0
        if pct > max_null_pct:
            failures.append(f"{f}: {pct:.2f}% nulls (> {max_null_pct:.2f}%)")

    if failures:
        return _fail("Null-rate check failed: " + "; ".join(failures))
    return _ok(f"Null-rate ok (max {max_null_pct:.2f}%)")


def _check_ranges(conn, window_hours: int | None) -> GateResult:
    where = ""
    params = {}
    if window_hours is not None:
        where = "WHERE created_at >= :cutoff"
        params["cutoff"] = _utcnow() - timedelta(hours=window_hours)

    total = int(conn.execute(text(f"SELECT COUNT(*) FROM recommendation_events {where}"), params).scalar() or 0)
    if total == 0:
        return _ok("Range checks skipped: no events in window")

    bad_latency = int(
        conn.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM recommendation_events
                {where}
                  {"AND" if where else "WHERE"} latency_ms IS NOT NULL
                  AND (latency_ms < 0 OR latency_ms > 60000)
                """
            ),
            params,
        ).scalar()
        or 0
    )
    if bad_latency > 0:
        return _fail(f"Range check failed: {bad_latency} events with latency_ms outside [0, 60000]")

    bad_reward = int(
        conn.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM recommendation_events
                {where}
                  {"AND" if where else "WHERE"} reward IS NOT NULL
                  AND (reward < -1.0 OR reward > 1.0)
                """
            ),
            params,
        ).scalar()
        or 0
    )
    if bad_reward > 0:
        return _fail(f"Range check failed: {bad_reward} events with reward outside [-1.0, 1.0]")

    return _ok("Range checks ok")


def _check_duplicates(conn, window_hours: int | None, max_dupe_pct: float) -> GateResult:
    where = ""
    params = {}
    if window_hours is not None:
        where = "WHERE created_at >= :cutoff"
        params["cutoff"] = _utcnow() - timedelta(hours=window_hours)

    total = int(conn.execute(text(f"SELECT COUNT(*) FROM recommendation_events {where}"), params).scalar() or 0)
    if total == 0:
        return _ok("Duplicate check skipped: no events in window")

    # Approximate event identity. This is intentionally simple and pragmatic for a gate.
    dupes = int(
        conn.execute(
            text(
                f"""
                WITH keyed AS (
                  SELECT
                    user_id, movie_id, policy, arm_id, served_at,
                    COUNT(*) AS c
                  FROM recommendation_events
                  {where}
                  GROUP BY user_id, movie_id, policy, arm_id, served_at
                )
                SELECT COALESCE(SUM(c - 1), 0)
                FROM keyed
                WHERE c > 1
                """
            ),
            params,
        ).scalar()
        or 0
    )
    pct = (dupes / total) * 100.0
    if pct > max_dupe_pct:
        return _fail(f"Duplicate rate too high: {pct:.2f}% (> {max_dupe_pct:.2f}%)")
    return _ok(f"Duplicate rate ok: {pct:.2f}%")


def run_checks(
    database_url: str,
    min_events: int,
    window_hours: int | None,
    freshness_minutes: int | None,
    max_null_pct: float,
    max_dupe_pct: float,
) -> Iterable[GateResult]:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        yield _check_required_columns(conn)
        yield _check_min_events(conn, min_events=min_events, window_hours=window_hours)
        if freshness_minutes is not None:
            yield _check_freshness(conn, max_age_minutes=freshness_minutes)
        yield _check_null_rates(conn, window_hours=window_hours, max_null_pct=max_null_pct)
        yield _check_ranges(conn, window_hours=window_hours)
        yield _check_duplicates(conn, window_hours=window_hours, max_dupe_pct=max_dupe_pct)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Cinemate data-quality gate")
    parser.add_argument("--database-url", required=True, help="SQLAlchemy DB URL")
    parser.add_argument("--min-events", type=int, default=0, help="Minimum events in window")
    parser.add_argument(
        "--window-hours",
        type=int,
        default=24,
        help="Window size (hours) for volume/null/dupe/range checks; set 0 to mean all-time",
    )
    parser.add_argument(
        "--freshness-minutes",
        type=int,
        default=None,
        help="Max age (minutes) of latest served_at; unset disables freshness check",
    )
    parser.add_argument("--max-null-pct", type=float, default=10.0, help="Max allowed null percent for key fields")
    parser.add_argument("--max-dupe-pct", type=float, default=1.0, help="Max allowed duplicate percent")

    args = parser.parse_args(argv)
    window_hours = None if args.window_hours == 0 else int(args.window_hours)

    results = list(
        run_checks(
            database_url=args.database_url,
            min_events=int(args.min_events),
            window_hours=window_hours,
            freshness_minutes=args.freshness_minutes,
            max_null_pct=float(args.max_null_pct),
            max_dupe_pct=float(args.max_dupe_pct),
        )
    )

    ok = True
    for r in results:
        prefix = "PASS" if r.ok else "FAIL"
        print(f"[{prefix}] {r.message}")
        ok = ok and r.ok

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


