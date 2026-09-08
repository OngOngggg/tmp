"""方案2+3评估：阈值PR曲线 + keys_60s过滤阈值扫描 + 两级规则对比。

方案2：阈值降级为理论设定，报告 PR 曲线（30-120s）。
方案3：两级规则 G(K) = (pause>30s) AND (keys_60s < K)，扫描 K。
"""
import os, json, re
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
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


def build_index():
    idx = {}
    for b in range(1, 200):
        fp = os.path.join(EXPORT, f"key_action_batch_{b:03d}.csv")
        if not os.path.exists(fp):
            break
        df = pd.read_csv(fp, usecols=["solution_id"])
        for sid in df["solution_id"]:
            idx[int(sid)] = b
    return idx


def load_session(sid, batch):
    fp = os.path.join(EXPORT, f"key_action_batch_{batch:03d}.csv")
    df = pd.read_csv(fp)
    m = df[df["solution_id"] == sid]
    if len(m) == 0:
        return None
    try:
        actions = json.loads(m.iloc[0]["action"])
    except Exception:
        return None
    downs = []
    for a in actions:
        if not isinstance(a, dict) or a.get("type") != "down":
            continue
        ts = parse_time(a.get("time", ""))
        if ts is None:
            continue
        downs.append((a["key"], ts))
    if len(downs) < 10:
        return None
    keys = np.array([k for k, t in downs])
    times = np.array([t for k, t in downs], dtype="datetime64[ns]")
    return {"keys": keys, "times": times}


def find_trigger_moment(session, ttype):
    keys, times = session["keys"], session["times"]
    n = len(times)
    if ttype == "IDLE":
        intervals = np.diff(times).astype("timedelta64[ms]").astype(float) / 1000.0
        for idx in range(1, n):
            if intervals[idx - 1] > 30:
                return idx
        return n // 2
    elif ttype == "DEBUG":
        is_bs = keys == "Backspace"
        for i in range(n - 1):
            if is_bs[i]:
                gap = (times[i + 1] - times[i]).astype("timedelta64[ms]").astype(float) / 1000.0
                if gap > 2:
                    return i
        return n // 2
    else:
        return n // 2


def prf(hit_mask, label):
    hit = int(hit_mask.sum())
    tp = int((hit_mask & (label == 1)).sum())
    fp = hit - tp
    fn = int((label == 1).sum()) - tp
    prec = tp / hit if hit > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    return hit, tp, fp, fn, prec, rec, f1


def main():
    labels = pd.read_csv(os.path.join(DATA, "labels.csv"))
    print(f"标注样本: {len(labels)} (label=1: {labels['label'].sum()})")
    print("建立 session 索引...")
    sid_batch = build_index()
    print(f"索引: {len(sid_batch)} sessions")

    rows = []
    for _, r in labels.iterrows():
        sid = int(r["solution_id"])
        batch = sid_batch.get(sid)
        if batch is None:
            continue
        session = load_session(sid, batch)
        if session is None:
            continue
        trig = find_trigger_moment(session, r["type"])
        trig_ts = session["times"][trig]
        keys, times = session["keys"], session["times"]
        n = len(times)
        pause_sec = (trig_ts - times[trig - 1]).astype("timedelta64[ms]").astype(float) / 1000.0 if trig > 0 else 0

        # keys_60s：触发前60s窗口按键数
        m60 = (times >= trig_ts - np.timedelta64(60, "s")) & (times < trig_ts)
        keys60 = int(m60.sum())

        rows.append({
            "solution_id": sid, "label": int(r["label"]), "type": r["type"],
            "pause_sec": round(pause_sec, 1), "keys60": keys60,
        })

    res = pd.DataFrame(rows)
    print(f"评估样本: {len(res)} (label=1: {res['label'].sum()})")
    print(f"  IDLE: {(res['type']=='IDLE').sum()}, DEBUG: {(res['type']=='DEBUG').sum()}, NORMAL: {(res['type']=='NORMAL').sum()}")

    # ===== 方案2: 阈值 PR 曲线（仅 IDLE 子集） =====
    idle = res[res["type"] == "IDLE"].copy()
    print(f"\n===== 方案2: IDLE 子集阈值 PR 曲线 (n={len(idle)}, label=1: {idle['label'].sum()}) =====")
    print(f"{'阈值':>6s} {'Hit':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
    print("-" * 55)
    for t in [20, 25, 30, 35, 40, 45, 50, 60, 75, 90, 120]:
        hit, tp, fp, fn, prec, rec, f1 = prf(idle["pause_sec"] > t, idle["label"])
        print(f"{t:>5d}s {hit:>5d} {tp:>4d} {fp:>4d} {fn:>4d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%}")

    # ===== 方案3: keys_60s 阈值扫描（两级规则，全集） =====
    print(f"\n===== 方案3: 两级规则 (pause>30s AND keys_60s<K) 全集 (n={len(res)}) =====")
    print(f"{'K':>5s} {'Hit':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
    print("-" * 55)
    base = res["pause_sec"] > 30
    for k in [5, 10, 15, 20, 25, 30, 40, 50]:
        hit, tp, fp, fn, prec, rec, f1 = prf(base & (res["keys60"] < k), res["label"])
        print(f"{k:>4d}  {hit:>5d} {tp:>4d} {fp:>4d} {fn:>4d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%}")

    # ===== 方案3: IDLE 子集上的两级规则 =====
    print(f"\n===== 方案3: 两级规则 IDLE 子集 (n={len(idle)}) =====")
    print(f"{'K':>5s} {'Hit':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
    print("-" * 55)
    for k in [5, 10, 15, 20, 25, 30, 40, 50]:
        hit, tp, fp, fn, prec, rec, f1 = prf((idle["pause_sec"] > 30) & (idle["keys60"] < k), idle["label"])
        print(f"{k:>4d}  {hit:>5d} {tp:>4d} {fp:>4d} {fn:>4d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%}")

    # ===== 方案3: 对比 =====
    print(f"\n===== 单级 vs 两级对比（全集） =====")
    print(f"{'规则':<28s} {'Hit':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
    print("-" * 60)
    rules = {
        "T1 (pause>30s)": res["pause_sec"] > 30,
        "keys_60s<20 单独": res["keys60"] < 20,
        "两级 (pause>30s & k60<20)": base & (res["keys60"] < 20),
        "两级 (pause>30s & k60<25)": base & (res["keys60"] < 25),
    }
    for name, mask in rules.items():
        hit, tp, fp, fn, prec, rec, f1 = prf(mask, res["label"])
        print(f"{name:<28s} {hit:>5d} {tp:>4d} {fp:>4d} {fn:>4d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%}")

    # ===== NORMAL 误报 =====
    norm = res[res["type"] == "NORMAL"]
    print(f"\n===== NORMAL 正常编码误报 (n={len(norm)}) =====")
    print(f"{'规则':<28s} {'误触发':>6s}")
    print("-" * 40)
    for name, mask in rules.items():
        fp = int(mask[norm.index].sum())
        print(f"{name:<28s} {fp:>6d}")


if __name__ == "__main__":
    main()
