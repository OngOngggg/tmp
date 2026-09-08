"""过滤阈值灵敏度分析：验证 30键/1min 不是魔术数字。
看 Ctrl 占比随按键数/时长阈值的变化，找操作构成发生质变的区间。
"""
import os, json, re
import numpy as np
import pandas as pd

EXPORT = r"D:\02_code\project\python\oj_demo\data\export"


def parse_time(s):
    s = re.sub(r":(\d+)$", r".\1", str(s))
    for f in ["%Y/%m/%d %H:%M:%S.%f", "%m/%d/%Y, %I:%M:%S %p.%f",
              "%Y-%m-%d %I:%M:%S %p.%f", "%d/%m/%Y, %H:%M:%S.%f"]:
        try:
            return pd.to_datetime(s, format=f)
        except Exception:
            pass
    return None


rows = []
for b in range(1, 30):
    fp = os.path.join(EXPORT, f"key_action_batch_{b:03d}.csv")
    if not os.path.exists(fp):
        break
    df = pd.read_csv(fp)
    for _, row in df.iterrows():
        try:
            actions = json.loads(row["action"])
        except Exception:
            continue
        downs = [a for a in actions if isinstance(a, dict) and a.get("type") == "down"]
        keys = [a.get("key", "") for a in downs]
        nk = len(keys)
        if nk == 0:
            continue
        times = []
        for a in downs:
            ts = parse_time(a.get("time", ""))
            if ts is not None:
                times.append(ts)
        dur = (times[-1] - times[0]).total_seconds() if len(times) > 1 else 0
        ctrl = sum(1 for k in keys if k in ("Control", "Meta"))
        rows.append({"nk": nk, "dur": dur, "ctrl_ratio": ctrl / nk})

d = pd.DataFrame(rows)
print(f"总session: {len(d)}")

print()
print("=== 按键数阈值灵敏度 ===")
print(f"{'阈值':>8s} {'过滤掉的':>10s} {'保留Ctrl占比':>12s} {'过滤部分Ctrl占比':>16s}")
print("-" * 55)
for t in [15, 20, 25, 30, 35, 40, 50]:
    kept = d[d["nk"] >= t]
    filt = d[d["nk"] < t]
    if len(filt) == 0:
        continue
    print(f"nk>={t:<4d} {len(filt):>10,} {kept['ctrl_ratio'].mean()*100:>11.1f}% {filt['ctrl_ratio'].mean()*100:>15.1f}%")

print()
print("=== 时长分桶 x Ctrl占比 ===")
bins = [0, 60, 120, 300, 600, 1800, 99999]
labels = ["0-1min", "1-2min", "2-5min", "5-10min", "10-30min", ">30min"]
d["dur_bin"] = pd.cut(d["dur"], bins=bins, labels=labels)
g = d.groupby("dur_bin", observed=True)["ctrl_ratio"].agg(["count", "mean"])
g["mean_pct"] = g["mean"] * 100
print(g[["count", "mean_pct"]].to_string())

print()
print("=== 时长阈值灵敏度 ===")
print(f"{'阈值':>8s} {'过滤掉的':>10s} {'保留Ctrl占比':>12s} {'过滤部分Ctrl占比':>16s}")
print("-" * 55)
for t in [30, 45, 60, 75, 90, 120]:
    kept = d[d["dur"] >= t]
    filt = d[d["dur"] < t]
    if len(filt) == 0:
        continue
    print(f"dur>={t:<4d}s {len(filt):>10,} {kept['ctrl_ratio'].mean()*100:>11.1f}% {filt['ctrl_ratio'].mean()*100:>15.1f}%")
