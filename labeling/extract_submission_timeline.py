"""Export the enabled OJ submission timeline using primary-key pagination.

MySQL is read-only. The output is used to derive causal pre-submission context
and post-hoc objective outcomes for the cleaned keystroke sessions.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import pymysql


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "clean_oj" / "submission_timeline.csv"
DEFAULT_CHECKPOINT = ROOT / "data" / "clean_oj" / "submission_timeline_checkpoint.json"
RESULT_MAP = {
    0: "Pending",
    4: "AC",
    5: "PE",
    6: "WA",
    7: "TLE",
    8: "MLE",
    9: "OLE",
    10: "NoData",
    11: "CE",
    13: "RE",
}
FIELDS = [
    "solution_id",
    "created_by",
    "problem_id",
    "result",
    "result_name",
    "created_time",
    "code_length",
    "language",
    "contest_id",
    "solution_type",
]


def load_password(env_name: str) -> str:
    password = os.environ.get(env_name, "")
    if password:
        return password
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == env_name:
                return value.strip().strip("\"'")
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--batch-size", type=int, default=20_000)
    parser.add_argument("--password-env", default="OJ_DB_PASSWORD")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    password = load_password(args.password_env)
    if not password:
        raise SystemExit(f"{args.password_env} is empty")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if args.reset:
        for path in (args.out, args.checkpoint):
            if path.exists():
                path.unlink()

    last_id = 0
    written = 0
    append = False
    if args.resume and args.out.exists() and args.checkpoint.exists():
        state = json.loads(args.checkpoint.read_text(encoding="utf-8"))
        last_id = int(state.get("last_id", 0))
        written = int(state.get("written", 0))
        append = True
        print(f"resume_after_solution_id={last_id:,} written={written:,}")

    conn = pymysql.connect(
        host="122.207.108.6",
        port=53306,
        user="root",
        password=password,
        database="csuoj_db",
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=180,
        autocommit=True,
    )
    mode = "a" if append else "w"
    encoding = "utf-8" if append else "utf-8-sig"
    try:
        with args.out.open(mode, newline="", encoding=encoding) as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            if not append:
                writer.writeheader()
            while True:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT id, created_by, problem_id, result, created_time,
                                  code_length, language, contest_id, solution_type
                           FROM solution
                           WHERE id > %s AND enable = 1
                           ORDER BY id
                           LIMIT %s""",
                        (last_id, args.batch_size),
                    )
                    rows = cur.fetchall()
                if not rows:
                    break
                for row in rows:
                    (solution_id, created_by, problem_id, result, created_time,
                     code_length, language, contest_id, solution_type) = row
                    writer.writerow({
                        "solution_id": solution_id,
                        "created_by": created_by if created_by is not None else "",
                        "problem_id": problem_id if problem_id is not None else "",
                        "result": result if result is not None else "",
                        "result_name": RESULT_MAP.get(result, "Unknown"),
                        "created_time": created_time.isoformat(sep=" ") if created_time else "",
                        "code_length": code_length if code_length is not None else "",
                        "language": language if language is not None else "",
                        "contest_id": contest_id if contest_id is not None else "",
                        "solution_type": solution_type if solution_type is not None else "",
                    })
                handle.flush()
                last_id = int(rows[-1][0])
                written += len(rows)
                args.checkpoint.write_text(
                    json.dumps({"last_id": last_id, "written": written}, indent=2),
                    encoding="utf-8",
                )
                print(f"last_id={last_id:,} written={written:,}")
    finally:
        conn.close()
    print(f"timeline_rows={written:,}")
    print(f"output={args.out}")


if __name__ == "__main__":
    main()
