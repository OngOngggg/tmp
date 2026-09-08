"""重建无未来信息泄漏的时刻级窗口数据。

这是离线实验的修正版：IDLE 的触发时刻定义为停顿开始后 30 秒，
而不是恢复输入的第一颗按键。每一行都有唯一 window_id，保留原标签
以便比较修正前后的结果。
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
OUT = DATA / "causal_windows.csv"


def parse_time(value: object) -> pd.Timestamp | None:
    text = re.sub(r":(\d+)$", r".\1", str(value))
    for fmt in (
        "%Y/%m/%d %H:%M:%S.%f",
        "%m/%d/%Y, %I:%M:%S %p.%f",
        "%Y-%m-%d %I:%M:%S %p.%f",
        "%d/%m/%Y, %H:%M:%S.%f",
    ):
        try:
            return pd.to_datetime(text, format=fmt)
        except (TypeError, ValueError):
            continue
    return None


def build_index() -> dict[int, Path]:
    index: dict[int, Path] = {}
    for path in sorted(EXPORT.glob("key_action_batch_*.csv")):
        try:
            ids = pd.read_csv(path, usecols=["solution_id"])["solution_id"]
        except Exception:
            continue
        for sid in ids.dropna().astype(int):
            index.setdefault(int(sid), path)
    return index


def load_downs(path: Path, sid: int) -> tuple[np.ndarray, np.ndarray] | None:
    frame = pd.read_csv(path)
    matched = frame[frame["solution_id"].astype(int) == sid]
    if matched.empty:
        return None
    try:
        actions = json.loads(matched.iloc[0]["action"])
    except (TypeError, json.JSONDecodeError):
        return None
    pairs = []
    for action in actions:
        if not isinstance(action, dict) or str(action.get("type", "")).lower() != "down":
            continue
        ts = parse_time(action.get("time"))
        if ts is not None:
            pairs.append((str(action.get("key", "?")), ts))
    if len(pairs) < 10:
        return None
    return np.array([p[0] for p in pairs], dtype=object), np.array([p[1] for p in pairs], dtype="datetime64[ns]")


def trigger(keys: np.ndarray, times: np.ndarray, kind: str) -> tuple[pd.Timestamp, int | None, pd.Timestamp | None, str]:
    """返回 trigger_ts、相关事件索引、pause_start、定义说明。"""
    if kind == "IDLE":
        gaps = np.diff(times).astype("timedelta64[ms]").astype(float) / 1000
        for i, gap in enumerate(gaps):
            if gap > 30:
                start = pd.Timestamp(times[i])
                return start + pd.Timedelta(seconds=30), i, start, "pause_start+30s"
    if kind == "DEBUG":
        for i in range(len(keys) - 1):
            if keys[i] == "Backspace":
                gap = float((times[i + 1] - times[i]).astype("timedelta64[ms]").astype(float) / 1000)
                if gap > 2:
                    start = pd.Timestamp(times[i])
                    return start + pd.Timedelta(seconds=2), i, start, "backspace+2s"
    # NORMAL 或无法找到候选时，使用 session 中部；仅用于保留原标注，不能当作规则效果证明。
    i = len(times) // 2
    return pd.Timestamp(times[i]), i, None, "session_midpoint"


def features(keys: np.ndarray, times: np.ndarray, ts: pd.Timestamp) -> dict[str, float | int]:
    t = times.astype("datetime64[ns]")
    out: dict[str, float | int] = {}
    for w in (5, 10, 30, 60, 120):
        mask = (t >= np.datetime64(ts - pd.Timedelta(seconds=w))) & (t < np.datetime64(ts))
        wk = keys[mask]
        out[f"keys_{w}s"] = int(mask.sum())
        out[f"backspace_{w}s"] = int((wk == "Backspace").sum())
        out[f"navigation_{w}s"] = int(np.isin(wk, ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End"]).sum())
        out[f"enter_{w}s"] = int((wk == "Enter").sum())
    before = t[t < np.datetime64(ts)]
    out["events_before"] = int(len(before))
    out["current_idle_s"] = float((np.datetime64(ts) - before[-1]).astype("timedelta64[ms]").astype(float) / 1000) if len(before) else np.nan
    return out


def main() -> None:
    labels = pd.read_csv(DATA / "labels.csv")
    index = build_index()
    cache: dict[Path, pd.DataFrame] = {}
    rows = []
    skipped = 0
    for label_row, record in labels.iterrows():
        sid = int(record["solution_id"])
        path = index.get(sid)
        if path is None:
            skipped += 1
            continue
        if path not in cache:
            cache[path] = pd.read_csv(path)
        loaded = load_downs(path, sid)
        if loaded is None:
            skipped += 1
            continue
        keys, times = loaded
        ts, event_index, pause_start, definition = trigger(keys, times, str(record["type"]))
        row = {
            "window_id": f"{sid}:{label_row:04d}",
            "label_row": label_row,
            "solution_id": sid,
            "type": str(record["type"]),
            "label": int(record["label"]),
            "event_index": event_index if event_index is not None else -1,
            "pause_start_ts": pause_start.isoformat() if pause_start is not None else "",
            "trigger_ts": ts.isoformat(),
            "trigger_definition": definition,
            "session_start_ts": pd.Timestamp(times[0]).isoformat(),
            "session_end_ts": pd.Timestamp(times[-1]).isoformat(),
        }
        row.update(features(keys, times, ts))
        rows.append(row)
    result = pd.DataFrame(rows)
    result.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"labels={len(labels)}, rebuilt={len(result)}, skipped={skipped}")
    print(f"unique window_id={result['window_id'].nunique() if len(result) else 0}")
    if len(result):
        print(result.groupby(["type", "trigger_definition"]).size().to_string())
        print("label counts:")
        print(result.groupby("type")["label"].agg(["count", "sum"]).to_string())
        print(f"output={OUT}")


if __name__ == "__main__":
    main()
