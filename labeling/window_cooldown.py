"""窗口大小扫描 + 冷却时间估计。

1) 窗口大小：keys_30s/45s/60s/90s/120s 各自在 183 条标注上的区分度与 P/R/F1。
2) 冷却估计：从原始按键流统计两次触发点之间的间隔分布，给冷却提供依据。
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
    print(f"标注样本: {len(labels)}")
    sid_batch = build_index()

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
        times = session["times"]
        feat = {"solution_id": sid, "label": int(r["label"]), "type": r["type"]}
        for w in [30, 45, 60, 90, 120, 180]:
            m = (times >= trig_ts - np.timedelta64(w, "s")) & (times < trig_ts)
            feat[f"keys_{w}s"] = int(m.sum())
        rows.append(feat)
    res = pd.DataFrame(rows)
    print(f"评估样本: {len(res)}")

    # 1) 窗口大小扫描：每个窗口取 F1 最优的 K，对比
    print(f"\n===== 窗口大小 vs 最优 P/R/F1（全集 n={len(res)}） =====")
    print(f"{'窗口':>6s} {'K':>4s} {'Hit':>5s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s} {'NORMAL误报':>10s}")
    print("-" * 62)
    for w in [30, 45, 60, 90, 120, 180]:
        col = f"keys_{w}s"
        best = None
        for k in range(5, max(41, w), 5):
            hit, tp, fp, fn, prec, rec, f1 = prf(res[col] < k, res["label"])
            if best is None or f1 > best[1]:
                best = (k, hit, prec, rec, f1)
        # NORMAL 误报 at best K
        norm = res[res["type"] == "NORMAL"]
        nfp = int((norm[col] < best[0]).sum())
        k, hit, prec, rec, f1 = best
        print(f"{w:>5d}s {k:>4d} {hit:>5d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%} {nfp:>8d}/30")

    # 2) keys_60s 精确 K 扫描（1-40 逐点）
    print(f"\n===== keys_60s 逐点 K 扫描 =====")
    print(f"{'K':>4s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
    print("-" * 30)
    for k in range(1, 41):
        hit, tp, fp, fn, prec, rec, f1 = prf(res["keys_60s"] < k, res["label"])
        if k in [1, 5, 10, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 30, 35, 40]:
            print(f"{k:>4d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%}")

    # 3) 冷却估计：统计标注 session 中"连续困境窗口"的间隔
    print(f"\n===== 冷却估计：触发点前后 5 分钟内活动分布 =====")
    # 对每个触发点，看触发后多久按键恢复到活跃（>1键/10s）
    rec_times = []
    for _, r in res.iterrows():
        sid = int(r["solution_id"])
        batch = sid_batch.get(sid)
        if batch is None:
            continue
        session = load_session(sid, batch)
        if session is None:
            continue
        trig = find_trigger_moment(session, r["type"])
        trig_ts = session["times"][trig]
        times = session["times"]
        after = times[times >= trig_ts]
        if len(after) < 2:
            continue
        # 触发后第一个按键
        first_after = (after[1] - trig_ts).astype("timedelta64[ms]").astype(float) / 1000.0
        # 触发后恢复到"60s内>=20键"需要多久
        recover = None
        for i in range(1, len(after)):
            win = (times >= after[i] - np.timedelta64(60, "s")) & (times < after[i])
            if win.sum() >= 20:
                recover = (after[i] - trig_ts).astype("timedelta64[ms]").astype(float) / 1000.0
                break
        rec_times.append({"sid": sid, "first_after": first_after,
                          "recover": recover if recover is not None else np.nan})

    rec = pd.DataFrame(rec_times)
    print(f"样本: {len(rec)}")
    print(f"触发后第一个按键: 中位数={rec['first_after'].median():.0f}s, "
          f"P75={rec['first_after'].quantile(0.75):.0f}s, P90={rec['first_after'].quantile(0.90):.0f}s")
    rec_ok = rec.dropna(subset=["recover"])
    print(f"恢复到活跃(60s>=20键): n={len(rec_ok)}, 中位数={rec_ok['recover'].median():.0f}s, "
          f"P75={rec_ok['recover'].quantile(0.75):.0f}s, P90={rec_ok['recover'].quantile(0.90):.0f}s")
    print(f"未恢复(可能结束/放弃): {rec['recover'].isna().sum()} 条")


if __name__ == "__main__":
    main()
