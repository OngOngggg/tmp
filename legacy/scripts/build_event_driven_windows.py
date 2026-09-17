"""Build event-driven causal candidates from the prototype sessions.

This is an offline analysis artifact. Trigger features use only events before
trigger_time. Columns prefixed with ``outcome_`` are post-trigger outcomes and
must never be used by an online trigger.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
EXPORT = ROOT.parent / "data" / "export"
WINDOWS = DATA / "prototype_windows.csv"
OUT = DATA / "event_driven_candidates.csv"
REPORT = DATA / "event_driven_candidates.md"

MODIFIERS = {"Control", "Shift", "Alt", "Meta", "CapsLock", "Escape", "Tab", "Insert", "Delete"}
NAVIGATION = {"ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"}
NON_TEXT = MODIFIERS | NAVIGATION | {"Dead", "Process", "Unidentified"}


def parse_time(value: object) -> pd.Timestamp | None:
    text = re.sub(r":(\d+)$", r".\1", str(value))
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%m/%d/%Y, %I:%M:%S %p.%f",
                "%Y-%m-%d %I:%M:%S %p.%f", "%d/%m/%Y, %H:%M:%S.%f"):
        try:
            return pd.to_datetime(text, format=fmt)
        except (TypeError, ValueError):
            pass
    return None


def index_exports() -> dict[int, Path]:
    result: dict[int, Path] = {}
    for path in sorted(EXPORT.glob("key_action_batch_*.csv")):
        try:
            ids = pd.read_csv(path, usecols=["solution_id"])["solution_id"]
        except Exception:
            continue
        for sid in ids.dropna().astype(int):
            result.setdefault(int(sid), path)
    return result


def load_events(path: Path, sid: int) -> list[dict]:
    frame = pd.read_csv(path)
    match = frame[frame.solution_id.astype(int) == sid]
    if match.empty:
        return []
    try:
        actions = json.loads(match.iloc[0].action)
    except (TypeError, json.JSONDecodeError):
        return []
    events = []
    for action in actions:
        if not isinstance(action, dict) or str(action.get("type", "")).lower() != "down":
            continue
        ts = parse_time(action.get("time"))
        if ts is None:
            continue
        events.append({"key": str(action.get("key", "?")), "time": ts,
                       "row": int(action.get("row", 0) or 0),
                       "column": int(action.get("column", 0) or 0)})
    events.sort(key=lambda x: x["time"])
    for i, event in enumerate(events):
        event["event_index"] = i
    return events


def clipboard_ops(events: list[dict]) -> int:
    count = 0
    for i, event in enumerate(events):
        if event["key"].lower() not in {"c", "v"}:
            continue
        if any(x["key"] in {"Control", "Meta"} and
               (event["time"] - x["time"]).total_seconds() <= 2 for x in events[max(0, i - 40):i]):
            count += 1
    return count


def causal_features(events: list[dict], trigger: pd.Timestamp) -> dict:
    before = [e for e in events if e["time"] < trigger]
    row = {"events_before": len(before),
           "event_index": before[-1]["event_index"] if before else -1,
           "current_idle_s": round((trigger - before[-1]["time"]).total_seconds(), 3) if before else None}
    for seconds in (5, 10, 30, 60, 120):
        start = trigger - pd.Timedelta(seconds=seconds)
        part = [e for e in before if start <= e["time"] < trigger]
        keys = [e["key"] for e in part]
        intervals = [(b["time"] - a["time"]).total_seconds() for a, b in zip(part, part[1:])]
        row[f"keys_{seconds}s"] = len(part)
        row[f"text_keys_{seconds}s"] = sum(k not in NON_TEXT for k in keys)
        row[f"modifier_keys_{seconds}s"] = sum(k in MODIFIERS for k in keys)
        row[f"clipboard_ops_{seconds}s"] = clipboard_ops(part)
        row[f"pause_count_{seconds}s"] = sum(x >= 2 for x in intervals)
        row[f"pause_total_{seconds}s"] = round(sum(x for x in intervals if x >= 2), 3)
        row[f"pause_p90_{seconds}s"] = round(float(np.percentile(intervals, 90)), 3) if intervals else 0.0
        row[f"backspace_{seconds}s"] = keys.count("Backspace")
        row[f"enter_{seconds}s"] = keys.count("Enter")
        row[f"control_{seconds}s"] = keys.count("Control")
        row[f"row_changes_{seconds}s"] = sum(a["row"] != b["row"] for a, b in zip(part, part[1:]))
        row[f"column_changes_{seconds}s"] = sum(a["column"] != b["column"] for a, b in zip(part, part[1:]))
    return row


def outcomes(events: list[dict], trigger: pd.Timestamp) -> dict:
    future = [e for e in events if e["time"] >= trigger]
    row = {}
    for seconds in (30, 60, 120):
        part = [e for e in future if e["time"] < trigger + pd.Timedelta(seconds=seconds)]
        keys = [e["key"] for e in part]
        row[f"outcome_keys_{seconds}s"] = len(part)
        row[f"outcome_text_keys_{seconds}s"] = sum(k not in NON_TEXT for k in keys)
        row[f"outcome_backspace_{seconds}s"] = keys.count("Backspace")
        row[f"outcome_enter_{seconds}s"] = keys.count("Enter")
    row["outcome_continued_input_120s"] = int(bool(future))
    row["outcome_next_event_s"] = round((future[0]["time"] - trigger).total_seconds(), 3) if future else None
    return row


def main() -> None:
    prototype = pd.read_csv(WINDOWS)
    selected = set(prototype.solution_id.astype(int).unique())
    meta = prototype.drop_duplicates("solution_id").set_index("solution_id").to_dict("index")
    index = index_exports()
    rows = []
    for sid in sorted(selected):
        path = index.get(sid)
        if path is None:
            continue
        events = load_events(path, sid)
        if len(events) < 10:
            continue
        for i, (a, b) in enumerate(zip(events, events[1:])):
            gap = (b["time"] - a["time"]).total_seconds()
            if gap >= 30:
                trigger = a["time"] + pd.Timedelta(seconds=30)
                row = {"candidate_id": f"{sid}-idle-{i:04d}", "solution_id": sid,
                       "candidate_type": "idle_30s", "trigger_time": trigger.isoformat(),
                       "problem_id": meta[sid]["problem_id"], "judge": meta[sid]["judge"]}
                row.update(causal_features(events, trigger)); row.update(outcomes(events, trigger)); rows.append(row)
            if a["key"] == "Backspace" and gap >= 2:
                trigger = a["time"] + pd.Timedelta(seconds=2)
                row = {"candidate_id": f"{sid}-debug-{i:04d}", "solution_id": sid,
                       "candidate_type": "backspace_pause_2s", "trigger_time": trigger.isoformat(),
                       "problem_id": meta[sid]["problem_id"], "judge": meta[sid]["judge"]}
                row.update(causal_features(events, trigger)); row.update(outcomes(events, trigger)); rows.append(row)
    result = pd.DataFrame(rows).drop_duplicates("candidate_id")
    result.to_csv(OUT, index=False, encoding="utf-8-sig")
    counts = result.candidate_type.value_counts().to_dict() if len(result) else {}
    report = ["# Event-driven causal candidates", "", f"- sessions={len(selected)}", f"- candidates={len(result)}", f"- types={counts}", "- causal features use only events before trigger_time.", "- outcome_* columns are post-trigger analysis fields and must not be used by an online trigger.", "- one idle gap produces one idle_30s candidate; 60/120 second extensions are not duplicate trigger rows."]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("sessions", len(selected), "candidates", len(result), "types", counts)
    print("output", OUT)
    print("report", REPORT)


if __name__ == "__main__":
    main()
