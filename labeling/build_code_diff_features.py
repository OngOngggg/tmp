"""Build submission-level code-diff features from the OJ source_code table.

For every cleaned keystroke session we compare its final submitted code against
the immediately previous submission of the same (user, problem). The result is
objective and does not depend on keystroke replay.

Causality note:
  - ``code_diff_ratio`` / ``net_growth`` / ``repeat_submit_no_change`` describe
    the *current* submission and are therefore known only AFTER the session ends.
    They are post-hoc / evaluation-level, NOT causal window features.
  - The same quantity shifted back one submission (the previous submission's diff)
    is known before the current session starts and is a causal feature. This shift
    is exposed as ``prev_submit_code_diff`` / ``prev_submit_net_growth``.

Design decisions (fixes vs v1):
  1. "Previous submission" is defined on the FULL submission timeline (shift on
     all submissions of the same user/problem), NOT on the clean-only subset.
     Concretely: prev_submit_diff = diff(prev_code, prev_prev_code), where prev
     and prev_prev are the true immediately-preceding submissions in time, whether
     or not they are themselves cleaned sessions. This keeps the causal feature on
     the same footing as the post-hoc feature (both compare consecutive
     submissions in time).
  2. Primary signal is LINE-level diff (changed lines / total lines). Char-level
     SequenceMatcher is kept as a secondary column only. Line-level is robust to
     re-indentation / formatter noise that destroys char-level similarity.
  3. Similarity thresholds are NOT hard-coded blindly; the report prints the
     distribution (P50..P99) of similarity so the ``repeat_submit_no_change``
     threshold can be anchored to an observed breakpoint (cf. the 30s=P99
     methodology used for IDLE).
"""
from __future__ import annotations

import argparse
import os
from difflib import SequenceMatcher
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "clean_oj"

MAX_DIFF_CHARS = 50_000   # cap string length for LINE-level diff (splitlines first)
MAX_CHAR_SIM_CHARS = 2_000  # char-level SequenceMatcher is O(n^2); hard-cap it


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


def fetch_codes(conn, solution_ids: list[int]) -> dict[int, str]:
    """Return the code per solution_id (source_code.solution_id is 1:1)."""
    codes: dict[int, str] = {}
    ids = sorted(set(int(x) for x in solution_ids if x))
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        placeholders = ",".join(["%s"] * len(chunk))
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT solution_id, code FROM source_code "
                f"WHERE solution_id IN ({placeholders}) AND enable = 1",
                chunk,
            )
            for sid, code in cur.fetchall():
                codes[int(sid)] = code or ""
    return codes


def _lines(code: str) -> list[str]:
    return code[:MAX_DIFF_CHARS].splitlines()


def diff_metrics(code: str, prev_code: str) -> dict:
    """Line-level primary + char-level secondary diff metrics."""
    a = code[:MAX_DIFF_CHARS]
    b = prev_code[:MAX_DIFF_CHARS]

    if not a and not b:
        return {
            "line_similarity": 1.0,
            "line_diff_ratio": 0.0,
            "changed_lines": 0,
            "total_lines": 0,
            "char_similarity": 1.0,
            "char_diff_ratio": 0.0,
        }
    if not a or not b:
        total = max(len(_lines(a)), len(_lines(b)))
        return {
            "line_similarity": 0.0,
            "line_diff_ratio": 1.0,
            "changed_lines": total,
            "total_lines": total,
            "char_similarity": 0.0,
            "char_diff_ratio": 1.0,
        }

    la, lb = _lines(a), _lines(b)
    sm = SequenceMatcher(None, la, lb, autojunk=False)
    line_sim = sm.ratio()
    changed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)
    total_lines = max(len(la), len(lb))

    # char-level (secondary), capped to bound O(n^2)
    char_sim = SequenceMatcher(None, a[:MAX_CHAR_SIM_CHARS], b[:MAX_CHAR_SIM_CHARS], autojunk=False).ratio()

    return {
        "line_similarity": round(line_sim, 6),
        "line_diff_ratio": round(1.0 - line_sim, 6),
        "changed_lines": changed,
        "total_lines": total_lines,
        "char_similarity": round(char_sim, 6),
        "char_diff_ratio": round(1.0 - char_sim, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, default=DEFAULT_DATA / "submission_timeline.csv")
    parser.add_argument("--context", type=Path, default=DEFAULT_DATA / "session_submission_context.csv")
    parser.add_argument("--out", type=Path, default=DEFAULT_DATA / "code_diff_features.csv")
    parser.add_argument("--report", type=Path, default=DEFAULT_DATA / "code_diff_features.md")
    parser.add_argument("--password-env", default="OJ_DB_PASSWORD")
    args = parser.parse_args()

    import pandas as pd

    timeline = pd.read_csv(args.timeline, parse_dates=["created_time"])
    context = pd.read_csv(args.context)
    for column in ("solution_id", "created_by", "problem_id"):
        timeline[column] = pd.to_numeric(timeline[column], errors="coerce")
    timeline = timeline.dropna(subset=["solution_id", "created_by", "problem_id", "created_time"])
    timeline[["solution_id", "created_by", "problem_id"]] = timeline[
        ["solution_id", "created_by", "problem_id"]
    ].astype("int64")
    timeline = timeline.sort_values(
        ["created_by", "problem_id", "created_time", "solution_id"], kind="stable"
    ).reset_index(drop=True)

    # ---- FIX #1: previous submission defined on the FULL timeline ----
    grouped = timeline.groupby(["created_by", "problem_id"], sort=False)
    timeline["prev_solution_id"] = grouped["solution_id"].shift(1)
    timeline["prev_prev_solution_id"] = grouped["solution_id"].shift(2)

    clean_ids = set(pd.to_numeric(context["solution_id"], errors="coerce").dropna().astype("int64"))
    clean_mask = timeline["solution_id"].isin(clean_ids)

    # Only need codes for clean rows, their immediate predecessor, and that
    # predecessor's predecessor (to compute prev_submit_diff).
    needed = set(timeline.loc[clean_mask, "solution_id"])
    for col in ("prev_solution_id", "prev_prev_solution_id"):
        needed |= set(timeline.loc[clean_mask, col].dropna().astype("int64"))

    password = load_password(args.password_env)
    if not password:
        raise SystemExit(f"{args.password_env} is empty")

    conn = pymysql.connect(
        host="122.207.108.6",
        port=53306,
        user="root",
        password=password,
        database="csuoj_db",
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=300,
        autocommit=True,
    )
    try:
        codes = fetch_codes(conn, sorted(needed))
    finally:
        conn.close()

    timeline["code"] = timeline["solution_id"].map(codes)
    timeline["prev_code"] = timeline["prev_solution_id"].map(codes)
    timeline["prev_prev_code"] = timeline["prev_prev_solution_id"].map(codes)

    def _valid(v):
        """True only for a genuine non-empty code string (NaN/float excluded)."""
        return isinstance(v, str)

    clean = timeline[clean_mask].copy()

    rows = []
    missing = 0
    n = len(clean)
    for idx, (_, row) in enumerate(clean.iterrows()):
        if idx % 5000 == 0:
            print(f"  diff progress: {idx}/{n}", flush=True)
        code = row.get("code")
        prev_code = row.get("prev_code")
        prev_prev_code = row.get("prev_prev_code")

        # post-hoc: current vs its immediately-preceding submission
        cur_metrics = diff_metrics(code, prev_code) if _valid(code) and _valid(prev_code) else {}
        # causal: previous submission vs the one before it (known before this session)
        prev_metrics = (
            diff_metrics(prev_code, prev_prev_code)
            if _valid(prev_code) and _valid(prev_prev_code)
            else {}
        )

        missing += int(not _valid(code) or not _valid(prev_code))

        rows.append({
            "solution_id": int(row["solution_id"]),
            "created_by": int(row["created_by"]),
            "problem_id": int(row["problem_id"]),
            "prev_solution_id": int(row["prev_solution_id"]) if pd.notna(row["prev_solution_id"]) else "",
            "code_len": len(code) if _valid(code) else "",
            "prev_code_len": len(prev_code) if _valid(prev_code) else "",
            # post-hoc: this submission vs previous
            "net_growth": (len(code) - len(prev_code)) if _valid(code) and _valid(prev_code) else "",
            "line_similarity": cur_metrics.get("line_similarity", ""),
            "line_diff_ratio": cur_metrics.get("line_diff_ratio", ""),
            "changed_lines": cur_metrics.get("changed_lines", ""),
            "total_lines": cur_metrics.get("total_lines", ""),
            "char_similarity": cur_metrics.get("char_similarity", ""),
            "char_diff_ratio": cur_metrics.get("char_diff_ratio", ""),
            # causal: previous submission vs the one before it
            "prev_submit_net_growth": (len(prev_code) - len(prev_prev_code))
            if _valid(prev_code) and _valid(prev_prev_code) else "",
            "prev_submit_line_diff": prev_metrics.get("line_diff_ratio", ""),
            "prev_submit_char_diff": prev_metrics.get("char_diff_ratio", ""),
        })

    out = pd.DataFrame(rows)
    num_cols = ["code_len", "prev_code_len", "net_growth", "changed_lines", "total_lines",
                "line_similarity", "line_diff_ratio", "char_similarity", "char_diff_ratio",
                "prev_submit_net_growth", "prev_submit_line_diff", "prev_submit_char_diff"]
    for column in num_cols:
        out[column] = pd.to_numeric(out[column], errors="coerce")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")

    # ---- FIX #3: similarity distribution to anchor the no-change threshold ----
    sim = out["line_similarity"].dropna()
    quantiles = sim.quantile([0.50, 0.75, 0.90, 0.95, 0.97, 0.98, 0.99]).round(4)

    merged = out.merge(
        context[["solution_id", "pair_outcome"]],
        on="solution_id", how="left", validate="one_to_one",
    )
    summary = merged.groupby("pair_outcome", dropna=False)["line_diff_ratio"].agg(
        ["count", "mean", "median"]
    ).round(4)

    report_lines = [
        "# Submission-level code-diff features",
        "",
        f"- cleaned sessions compared={len(out):,}",
        f"- missing code (skipped diff)={missing:,}",
        f"- primary signal = line-level diff (line_diff_ratio, changed_lines)",
        f"- secondary signal = char-level diff (char_diff_ratio)",
        "",
        "## line_similarity distribution (anchor for no-change threshold)",
        "",
        "| pct | line_similarity |",
        "|---|---|",
    ]
    for pct, val in quantiles.items():
        report_lines.append(f"| {int(pct * 100)} | {val} |")
    report_lines += [
        "",
        "## line_diff_ratio by objective pair outcome",
        "",
        summary.to_string(),
        "",
        "- line_diff_ratio: 0 = identical to previous submission, 1 = completely rewritten.",
        "- net_growth: current code length minus previous code length (characters).",
        "- line_diff_ratio / net_growth are post-hoc for this session; use "
        "prev_submit_line_diff / prev_submit_net_growth as causal features.",
    ]
    args.report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"cleaned_sessions_compared={len(out):,} missing={missing:,}")
    print("line_similarity quantiles:")
    print(quantiles.to_string())
    print(summary.to_string())
    print(f"output={args.out}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
