"""Build event-driven causal candidates for every cleaned session.

The input event stream is normalized by ``extract_clean_dataset.py``. Feature
columns are computed strictly from events before ``trigger_time``. Columns
prefixed with ``outcome_`` and ``pair_`` are post-trigger/evaluation fields;
they must not be used by an online trigger.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "clean_oj"
WINDOWS = (5, 10, 30, 60, 120)
MODIFIERS = {"Control", "Shift", "Alt", "Meta", "CapsLock", "Escape", "Tab", "Insert", "Delete"}
NAVIGATION = {"ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"}
NON_TEXT = MODIFIERS | NAVIGATION | {"Dead", "Process", "Unidentified"}


def dt(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def key_features(events: list[dict], times: list[datetime], trigger: datetime) -> dict:
    before_end = bisect_left(times, trigger)
    before = events[:before_end]
    out = {
        "events_before": before_end,
        "event_index": before_end - 1,
        "current_idle_s": round((trigger - times[before_end - 1]).total_seconds(), 3) if before_end else "",
    }
    for seconds in WINDOWS:
        start = trigger - timedelta(seconds=seconds)
        left = bisect_left(times, start, 0, before_end)
        part = events[left:before_end]
        keys = [item["key"] for item in part]
        intervals = [
            (times[i] - times[i - 1]).total_seconds()
            for i in range(left + 1, before_end)
            if (times[i] - times[i - 1]).total_seconds() > 0
        ]
        text = [key for key in keys if key not in NON_TEXT]
        pauses = [gap for gap in intervals if gap >= 2]
        sorted_intervals = sorted(intervals)
        p90 = sorted_intervals[int(0.9 * (len(sorted_intervals) - 1))] if sorted_intervals else 0.0
        out[f"keys_{seconds}s"] = len(part)
        out[f"text_keys_{seconds}s"] = len(text)
        out[f"modifier_keys_{seconds}s"] = sum(key in MODIFIERS for key in keys)
        out[f"clipboard_ops_{seconds}s"] = clipboard_ops(part, times[left:before_end])
        out[f"pause_count_{seconds}s"] = len(pauses)
        out[f"pause_total_{seconds}s"] = round(sum(pauses), 3)
        out[f"pause_p90_{seconds}s"] = round(p90, 3)
        out[f"backspace_{seconds}s"] = keys.count("Backspace")
        out[f"enter_{seconds}s"] = keys.count("Enter")
        out[f"control_{seconds}s"] = keys.count("Control")
        out[f"row_changes_{seconds}s"] = sum(
            part[i]["row"] != part[i - 1]["row"] for i in range(1, len(part))
        )
        out[f"column_changes_{seconds}s"] = sum(
            part[i]["column"] != part[i - 1]["column"] for i in range(1, len(part))
        )
    return out


def clipboard_ops(events: list[dict], times: list[datetime]) -> int:
    count = 0
    for i, event in enumerate(events):
        if event["key"].lower() not in {"c", "v"}:
            continue
        start = max(0, i - 40)
        if any(
            prior["key"] in {"Control", "Meta"}
            and (times[i] - times[j]).total_seconds() <= 2
            for j, prior in enumerate(events[start:i], start)
        ):
            count += 1
    return count


def future_outcomes(events: list[dict], times: list[datetime], trigger: datetime) -> dict:
    left = bisect_left(times, trigger)
    out = {}
    for seconds in (30, 60, 120):
        right = bisect_left(times, trigger + timedelta(seconds=seconds), left)
        part = events[left:right]
        keys = [item["key"] for item in part]
        out[f"outcome_keys_{seconds}s"] = len(part)
        out[f"outcome_text_keys_{seconds}s"] = sum(key not in NON_TEXT for key in keys)
        out[f"outcome_backspace_{seconds}s"] = keys.count("Backspace")
        out[f"outcome_enter_{seconds}s"] = keys.count("Enter")
    out["outcome_continued_input_120s"] = int(left < len(events))
    out["outcome_next_event_s"] = round((times[left] - trigger).total_seconds(), 3) if left < len(events) else ""
    return out


def main() -> None:
    csv.field_size_limit(sys.maxsize)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_DATA / "events" / "key_action_clean.csv")
    parser.add_argument("--context", type=Path, default=DEFAULT_DATA / "session_submission_context.csv")
    parser.add_argument("--out", type=Path, default=DEFAULT_DATA / "full_causal_candidates.csv")
    parser.add_argument("--report", type=Path, default=DEFAULT_DATA / "full_causal_candidates.md")
    args = parser.parse_args()

    context = {}
    with args.context.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            context[int(row["solution_id"])] = row

    rows_written = 0
    session_count = 0
    type_counts = {"idle_30s": 0, "backspace_pause_2s": 0}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as output:
        writer = None
        with args.events.open(encoding="utf-8-sig", newline="") as handle:
            for source in csv.DictReader(handle):
                sid = int(source["solution_id"])
                meta = context.get(sid)
                if meta is None:
                    continue
                events = json.loads(source["action"])
                events = [event for event in events if event.get("type") == "down"]
                times = [dt(event["time"]) for event in events]
                if len(events) < 2:
                    continue
                session_count += 1
                candidates = []
                for index, (current, following) in enumerate(zip(events, events[1:])):
                    gap = (times[index + 1] - times[index]).total_seconds()
                    if gap >= 30:
                        candidates.append(("idle_30s", times[index] + timedelta(seconds=30), index))
                    if current["key"] == "Backspace" and gap >= 2:
                        candidates.append(("backspace_pause_2s", times[index] + timedelta(seconds=2), index))
                for ordinal, (candidate_type, trigger, pause_index) in enumerate(candidates):
                    features = key_features(events, times, trigger)
                    features.update(future_outcomes(events, times, trigger))
                    row = {
                        "candidate_id": f"{sid}-{candidate_type}-{ordinal:04d}",
                        "solution_id": sid,
                        "created_by": meta.get("created_by", ""),
                        "problem_id": meta.get("problem_id", ""),
                        "candidate_type": candidate_type,
                        "trigger_time": trigger.isoformat(sep=" "),
                        "pause_event_index": pause_index,
                        "last_known_judge_before": meta.get("last_known_judge_before", ""),
                        "last_known_judge_name": meta.get("last_known_judge_name", ""),
                        "prior_submit_count": meta.get("prior_submit_count", ""),
                        "time_since_prior_s": meta.get("time_since_prior_s", ""),
                        "own_result": meta.get("own_result", ""),
                        "own_result_name": meta.get("own_result_name", ""),
                        "pair_outcome": meta.get("pair_outcome", ""),
                        "pair_submission_count": meta.get("pair_submission_count", ""),
                        "pair_has_ac": meta.get("pair_has_ac", ""),
                    }
                    row.update(features)
                    if writer is None:
                        writer = csv.DictWriter(output, fieldnames=list(row))
                        writer.writeheader()
                    writer.writerow(row)
                    rows_written += 1
                    type_counts[candidate_type] += 1

    report = [
        "# Full causal candidates",
        "",
        f"- sessions_with_events={session_count:,}",
        f"- candidates={rows_written:,}",
        f"- candidate_types={type_counts}",
        "- causal features use only events with event_time < trigger_time.",
        "- outcome_* columns are post-trigger behavior for evaluation only.",
        "- own_result, pair_outcome, and pair_* columns are evaluation-only labels/context.",
        "- last_known_judge_before is the latest submission result known before this solution.",
    ]
    args.report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"sessions_with_events={session_count:,}")
    print(f"candidates={rows_written:,}")
    print(f"candidate_types={type_counts}")
    print(f"output={args.out}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
