"""Extract and clean OJ sessions from the two MySQL databases.

The source tables live on different MySQL ports.  This script therefore joins
them locally, streams ``key_action`` by its primary key, and writes only
normalized ``type=down`` events for sessions that are usable for causal-window
analysis.  A SQLite staging table makes the scan resumable and keeps duplicate
``solution_id`` rows under control without holding action JSON in memory.

Usage (from the project root)::

    python extract_clean_dataset.py --password-env OJ_DB_PASSWORD

The default output is ``data/clean_oj``.  The script is read-only with respect
to MySQL; it only creates local output files.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

try:
    import pymysql
    from pymysql.cursors import SSCursor
except ImportError:  # Keep --help and static checks usable without DB extras.
    pymysql = None
    SSCursor = None


ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "data" / "clean_oj"
HOST = "122.207.108.6"
PORT_KEY = 19106
PORT_SOL = 53306
USER = "root"


def parse_time(value: object) -> datetime | None:
    """Parse the timestamp variants present in key_action JSON."""
    if value is None:
        return None
    text = str(value).strip().replace("T", " ")
    text = re.sub(r":(\d{1,6})$", r".\1", text)
    for fmt in (
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
        "%m/%d/%Y, %I:%M:%S %p.%f",
        "%Y-%m-%d %I:%M:%S %p.%f",
        "%d/%m/%Y, %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def normalize_action(raw: object) -> tuple[list[dict], int, int]:
    """Return normalized down events, total down items, and invalid count."""
    try:
        actions = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return [], 0, 0
    if not isinstance(actions, list):
        return [], 0, 0

    events: list[dict] = []
    down_total = 0
    invalid = 0
    for item in actions:
        if not isinstance(item, dict) or str(item.get("type", "")).lower() != "down":
            continue
        down_total += 1
        ts = parse_time(item.get("time"))
        if ts is None:
            invalid += 1
            continue
        events.append({
            "key": str(item.get("key", "?")),
            "time": ts.isoformat(sep=" "),
            "type": "down",
            "row": safe_int(item.get("row")),
            "column": safe_int(item.get("column")),
        })
    events.sort(key=lambda event: event["time"])
    return events, down_total, invalid


def quality(events: list[dict], down_total: int) -> tuple[float, int, str, str]:
    if not events:
        return 0.0, 0, "", ""
    first = events[0]["time"]
    last = events[-1]["time"]
    start = datetime.fromisoformat(first)
    end = datetime.fromisoformat(last)
    duration = max(0.0, (end - start).total_seconds())
    ratio = len(events) / down_total if down_total else 0.0
    return ratio, round(duration, 3), first, last


def connect(port: int, database: str, password: str):
    if pymysql is None:
        raise RuntimeError("pymysql is required; install it in the environment running this script")
    return pymysql.connect(
        host=HOST,
        port=port,
        user=USER,
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=300,
        write_timeout=300,
        autocommit=True,
    )


def init_stage(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS candidates (
            solution_id INTEGER PRIMARY KEY,
            key_action_id INTEGER NOT NULL,
            problem_id INTEGER,
            created_by INTEGER,
            start_time TEXT,
            created_time TEXT,
            action TEXT NOT NULL,
            event_count INTEGER NOT NULL,
            down_total INTEGER NOT NULL,
            parse_ratio REAL NOT NULL,
            duration_s REAL NOT NULL,
            first_event_time TEXT NOT NULL,
            last_event_time TEXT NOT NULL
        )"""
    )
    conn.commit()
    return conn


def is_better(new: tuple, old: tuple | None) -> bool:
    if old is None:
        return True
    # Prefer cleaner parses, then more events, then longer observed activity.
    return (new[9], new[7], new[10]) > (old[9], old[7], old[10])


def scan_key_actions(args: argparse.Namespace, stage: sqlite3.Connection, password: str) -> dict[str, int]:
    checkpoint = args.output / "scan_checkpoint.json"
    last_id = 0
    counters = {"rows_seen": 0, "rows_with_events": 0, "rows_kept": 0, "rows_rejected": 0}
    if args.resume and checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        last_id = int(state.get("last_id", 0))
        counters.update({k: int(v) for k, v in state.get("counters", {}).items() if k in counters})
        print(f"resuming key_action scan after id={last_id:,}")

    conn = connect(PORT_KEY, "experiment_data", password)
    try:
        while True:
            with conn.cursor(SSCursor) as cur:
                cur.execute(
                    """SELECT id, action, solution_id, start_time, problem_id,
                              created_by, created_time
                       FROM key_action
                       WHERE id > %s
                       ORDER BY id
                       LIMIT %s""",
                    (last_id, args.batch_size),
                )
                rows = cur.fetchall()
            if not rows:
                break
            for row_id, raw_action, sid, start_time, problem_id, created_by, created_time in rows:
                last_id = max(last_id, safe_int(row_id))
                counters["rows_seen"] += 1
                sid = safe_int(sid)
                if sid <= 0 or safe_int(problem_id) <= 0:
                    counters["rows_rejected"] += 1
                    continue
                events, down_total, invalid = normalize_action(raw_action)
                if not events:
                    counters["rows_rejected"] += 1
                    continue
                counters["rows_with_events"] += 1
                ratio, duration, first, last = quality(events, down_total)
                if (
                    len(events) < args.min_keys
                    or duration < args.min_duration
                    or duration > args.max_duration
                    or ratio < args.min_parse_ratio
                ):
                    counters["rows_rejected"] += 1
                    continue
                normalized = json.dumps(events, ensure_ascii=False, separators=(",", ":"))
                candidate = (
                    sid, safe_int(row_id), safe_int(problem_id),
                    safe_int(created_by) if created_by is not None else None,
                    str(start_time or ""), str(created_time or ""), normalized,
                    len(events), down_total, ratio, duration, first, last,
                )
                old = stage.execute(
                    "SELECT * FROM candidates WHERE solution_id = ?", (sid,)
                ).fetchone()
                if is_better(candidate, old):
                    stage.execute(
                        """INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(solution_id) DO UPDATE SET
                             key_action_id=excluded.key_action_id,
                             problem_id=excluded.problem_id,
                             created_by=excluded.created_by,
                             start_time=excluded.start_time,
                             created_time=excluded.created_time,
                             action=excluded.action,
                             event_count=excluded.event_count,
                             down_total=excluded.down_total,
                             parse_ratio=excluded.parse_ratio,
                             duration_s=excluded.duration_s,
                             first_event_time=excluded.first_event_time,
                             last_event_time=excluded.last_event_time""",
                        candidate,
                    )
                    counters["rows_kept"] += 1
            stage.commit()
            checkpoint.write_text(
                json.dumps({"last_id": last_id, "counters": counters}, indent=2),
                encoding="utf-8",
            )
            if counters["rows_seen"] % args.progress_every < args.batch_size:
                print(
                    f"scanned={counters['rows_seen']:,} kept={counters['rows_kept']:,} "
                    f"last_id={last_id:,}"
                )
    finally:
        conn.close()
    return counters


def chunks(values: list[int], size: int) -> Iterator[list[int]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def fetch_solution_meta(ids: list[int], password: str) -> dict[int, tuple]:
    result: dict[int, tuple] = {}
    conn = connect(PORT_SOL, "csuoj_db", password)
    try:
        with conn.cursor() as cur:
            for group in chunks(ids, 1000):
                placeholders = ",".join(["%s"] * len(group))
                cur.execute(
                    f"SELECT id, problem_id, created_by, created_time, result, code_length "
                    f"FROM solution WHERE id IN ({placeholders})",
                    group,
                )
                for row in cur.fetchall():
                    result[int(row[0])] = row[1:]
    finally:
        conn.close()
    return result


def fetch_code_meta(ids: list[int], password: str) -> dict[int, int]:
    result: dict[int, int] = {}
    conn = connect(PORT_SOL, "csuoj_db", password)
    try:
        with conn.cursor() as cur:
            for group in chunks(ids, 1000):
                placeholders = ",".join(["%s"] * len(group))
                cur.execute(
                    f"SELECT solution_id, CHAR_LENGTH(code) FROM source_code "
                    f"WHERE solution_id IN ({placeholders})",
                    group,
                )
                for sid, length in cur.fetchall():
                    result[int(sid)] = int(length or 0)
    finally:
        conn.close()
    return result


def export_outputs(args: argparse.Namespace, stage: sqlite3.Connection, password: str) -> None:
    rows = stage.execute("SELECT * FROM candidates ORDER BY solution_id").fetchall()
    ids = [int(row[0]) for row in rows]
    meta = fetch_solution_meta(ids, password)
    missing_meta = len(rows) - len(meta)
    rows = [row for row in rows if int(row[0]) in meta]
    ids = [int(row[0]) for row in rows]
    code_lengths = fetch_code_meta(ids, password)
    result_map = {4: "AC", 5: "PE", 6: "WA", 7: "TLE", 8: "MLE",
                  9: "OLE", 10: "NoData", 11: "CE", 13: "RE"}

    sessions_path = args.output / "clean_sessions.csv"
    with sessions_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "solution_id", "key_action_id", "problem_id", "created_by",
            "solution_created_time", "final_result_code", "final_judge",
            "code_length_solution", "submitted_code_length", "has_code",
            "event_count", "down_total", "parse_ratio", "duration_s",
            "first_event_time", "last_event_time",
        ])
        for row in rows:
            sid = int(row[0])
            solution_problem, solution_user, solution_time, final_result, solution_len = meta.get(
                sid, (row[2], row[3], "", None, None)
            )
            code_len = code_lengths.get(sid, 0)
            writer.writerow([
                sid, row[1], solution_problem, solution_user, solution_time or "",
                final_result if final_result is not None else "",
                result_map.get(final_result, "?") if final_result is not None else "?",
                solution_len if solution_len is not None else "", code_len, int(code_len > 10),
                row[7], row[8], f"{row[9]:.6f}", f"{row[10]:.3f}", row[11], row[12],
            ])

    export_dir = args.output / "events"
    export_dir.mkdir(exist_ok=True)
    events_path = export_dir / "key_action_clean.csv"
    with events_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "id", "action", "solution_id", "start_time", "problem_id",
            "created_by", "created_time",
        ])
        for row in rows:
            normalized_events = json.loads(row[6])
            for event in normalized_events:
                event.setdefault("type", "down")
            writer.writerow([
                row[1], json.dumps(normalized_events, ensure_ascii=False, separators=(",", ":")),
                row[0], row[4], row[2], row[3], row[5],
            ])
    print(f"sessions={len(rows):,}")
    print(f"dropped_missing_solution_meta={missing_meta:,}")
    print(f"with_solution_meta={len(rows):,}")
    print(f"with_code={sum(int(row[0]) in code_lengths for row in rows):,}")
    print(f"clean_sessions={sessions_path}")
    print(f"clean_events={events_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password-env", default="OJ_DB_PASSWORD")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--progress-every", type=int, default=10000)
    parser.add_argument("--min-duration", type=float, default=60.0)
    parser.add_argument("--max-duration", type=float, default=1800.0)
    parser.add_argument("--min-keys", type=int, default=30)
    parser.add_argument("--min-parse-ratio", type=float, default=0.8)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reset", action="store_true", help="delete local staging/checkpoint before scanning")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    password = os.environ.get(args.password_env, "")
    if not password:
        dotenv = ROOT / ".env"
        if dotenv.exists():
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() == args.password_env:
                    password = value.strip().strip("\"'")
                    break
    if not password:
        raise SystemExit(f"{args.password_env} is empty; load the project .env into the environment first")
    stage_path = args.output / "candidates.sqlite3"
    if args.reset:
        for path in (stage_path, args.output / "scan_checkpoint.json"):
            if path.exists():
                path.unlink()
    stage = init_stage(stage_path)
    started = time.time()
    try:
        counters = scan_key_actions(args, stage, password)
        print("scan_summary=" + json.dumps(counters, ensure_ascii=False))
        export_outputs(args, stage, password)
    finally:
        stage.close()
    print(f"elapsed_s={time.time() - started:.1f}")


if __name__ == "__main__":
    main()
