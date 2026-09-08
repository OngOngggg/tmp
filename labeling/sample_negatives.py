"""
补充负样本：从已标注的 session 中随机截取正常编码窗口。
输出: data/negatives_30.csv （可追加到 candidates_200.csv 一起标注）
"""
import os, json, re, random
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
EXPORT_DIR = os.path.join(os.path.dirname(ROOT), "data", "export")
LABELS = os.path.join(DATA_DIR, "labels.csv")
OUT = os.path.join(DATA_DIR, "negatives_30.csv")
os.makedirs(DATA_DIR, exist_ok=True)

random.seed(123)
WINDOW_SIZE = 30  # 30s 窗口
N_SAMPLES = 30    # 补 30 条
MIN_KEYS_IN_WINDOW = 8  # 窗口内至少 8 键（有在编码）


def parse_time(s):
    s = re.sub(r':(\d+)$', r'.\1', str(s))
    for f in ['%Y/%m/%d %H:%M:%S.%f','%m/%d/%Y, %I:%M:%S %p.%f',
              '%Y-%m-%d %I:%M:%S %p.%f','%d/%m/%Y, %H:%M:%S.%f']:
        try: return pd.to_datetime(s, format=f)
        except: pass
    return None


def compress_keys(keys, max_len=40):
    parts = []; prev = None; cnt = 0
    for k in keys[:200]:
        if k == prev: cnt += 1
        else:
            if cnt > 0: parts.append(f"{prev}" if cnt == 1 else f"{prev}x{cnt}")
            prev = k; cnt = 1
    if cnt > 0: parts.append(f"{prev}" if cnt == 1 else f"{prev}x{cnt}")
    return " -> ".join(parts[:max_len])


def main():
    labels = pd.read_csv(LABELS)
    labeled_sids = list(set(int(s) for s in labels["solution_id"]))
    print(f"Labeled sessions: {len(labeled_sids)}")

    # Build sid -> batch index (fast lookup)
    sid_to_batch = {}
    for b in range(1, 200):
        fp = os.path.join(EXPORT_DIR, f"key_action_batch_{b:03d}.csv")
        if not os.path.exists(fp): break
        df = pd.read_csv(fp)
        for sid in df["solution_id"]:
            sid_to_batch[int(sid)] = b
    print(f"Index: {len(sid_to_batch)} sessions")

    negatives = []
    for sid in labeled_sids:
        if len(negatives) >= N_SAMPLES: break
        batch = sid_to_batch.get(sid)
        if batch is None: continue
        fp = os.path.join(EXPORT_DIR, f"key_action_batch_{batch:03d}.csv")
        df = pd.read_csv(fp)
        row = df[df["solution_id"] == sid]
        if len(row) == 0: continue
        try: actions = json.loads(row.iloc[0]["action"])
        except: continue

        downs = []
        for a in actions:
            if not isinstance(a, dict) or a.get("type") != "down": continue
            ts = parse_time(a.get("time", ""))
            if ts is None: continue
            downs.append((a.get("key", "?"), ts))
        if len(downs) < MIN_KEYS_IN_WINDOW * 3: continue

        keys = np.array([k for k, t in downs])
        times = np.array([t for k, t in downs], dtype="datetime64[ns]")
        n = len(times)
        dur = (times[-1] - times[0]).astype("timedelta64[ms]").astype(float) / 1000.0

        # Find IDLE trigger times
        intervals = np.diff(times).astype("timedelta64[ms]").astype(float) / 1000.0
        trigger_times = set()
        for idx in range(1, n):
            if intervals[idx - 1] > 30:
                trigger_times.add(times[idx])

        # Try random positions, pick one with enough activity and far from triggers
        for attempt in range(5):
            rand_idx = random.randint(MIN_KEYS_IN_WINDOW, n - MIN_KEYS_IN_WINDOW - 1)
            rand_ts = times[rand_idx]

            # Check: far from any trigger?
            too_close = False
            for tt in trigger_times:
                if abs((rand_ts - tt).astype("timedelta64[ms]").astype(float) / 1000.0) < WINDOW_SIZE:
                    too_close = True; break
            if too_close: continue

            # Check: enough keys in the 30s before?
            start = rand_ts - np.timedelta64(WINDOW_SIZE, "s")
            mask = (times >= start) & (times < rand_ts)
            if mask.sum() < MIN_KEYS_IN_WINDOW: continue

            # Build candidate - get keys before AND after the random point
            # Before
            mask_before = (times >= rand_ts - np.timedelta64(30, "s")) & (times < rand_ts)
            mask_before_10 = (times >= rand_ts - np.timedelta64(10, "s")) & (times < rand_ts)
            # After
            mask_after = (times >= rand_ts) & (times < rand_ts + np.timedelta64(30, "s"))
            mask_after_10 = (times >= rand_ts) & (times < rand_ts + np.timedelta64(10, "s"))

            # Code replay up to this point
            IGNORE = {"Control","Shift","Alt","Meta","CapsLock","Escape","Tab",
                      "ArrowUp","ArrowDown","ArrowLeft","ArrowRight","Home","End",
                      "PageUp","PageDown","Insert","Delete","Dead","Process","NumLock"}
            code = ""
            for k in keys[:rand_idx+1]:
                if k in IGNORE: continue
                if k == "Backspace": code = code[:-1] if code else ""
                elif k == "Enter": code += "\n"
                elif k == " " or k == "Space": code += " "
                elif len(k) == 1: code += k

            negatives.append({
                "solution_id": sid,
                "problem_id": int(row.iloc[0].get("problem_id", 0)),
                "judge": labels[labels["solution_id"] == sid]["judge"].iloc[0],
                "type": "NORMAL",
                "detail": f"random_{WINDOW_SIZE}s_window",
                "duration_s": round(dur, 1),
                "total_keys": n,
                "keys_10s_before": compress_keys(keys[mask_before_10]),
                "keys_30s_before": compress_keys(keys[mask_before]),
                "keys_10s_after": compress_keys(keys[mask_after_10]),
                "keys_30s_after": compress_keys(keys[mask_after]),
                "code_at_trigger": code[-600:],
                "label": "",
            })
            print(f"  SID={sid}: {mask_before.sum()} keys in window")
            break

    print(f"\nGenerated {len(negatives)} negative samples")
    ndf = pd.DataFrame(negatives)
    ndf.to_csv(OUT, index=False)
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
