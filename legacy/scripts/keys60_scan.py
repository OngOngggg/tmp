"""keys_60s 单独规则的细扫：K 从 5 到 60 逐点，分类型看命中，检查误报。"""
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
        m60 = (times >= trig_ts - np.timedelta64(60, "s")) & (times < trig_ts)
        keys60 = int(m60.sum())
        rows.append({
            "solution_id": sid, "label": int(r["label"]), "type": r["type"],
            "keys60": keys60,
        })
    res = pd.DataFrame(rows)
    print(f"评估样本: {len(res)}")

    # keys_60s 阈值细扫（全集）
    print(f"\n===== keys_60s 单独规则（全集 n={len(res)}） =====")
    print(f"{'K':>4s} {'Hit':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
    print("-" * 55)
    best = None
    for k in range(5, 61, 5):
        hit, tp, fp, fn, prec, rec, f1 = prf(res["keys60"] < k, res["label"])
        print(f"{k:>4d} {hit:>5d} {tp:>4d} {fp:>4d} {fn:>4d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%}")
        if best is None or f1 > best[1]:
            best = (k, f1)
    print(f"\nF1 最优: K={best[0]}, F1={best[1]:.1%}")

    # 分类型命中率
    print(f"\n===== 各类型下 keys_60s 分布 =====")
    for t in ["IDLE", "DEBUG", "NORMAL"]:
        sub = res[res["type"] == t]
        if len(sub) == 0:
            continue
        print(f"{t}: n={len(sub)}, label=1: {sub['label'].sum()}, keys60 中位数={sub['keys60'].median():.0f}, "
              f"keys60<=20: {(sub['keys60']<=20).sum()}, keys60<=30: {(sub['keys60']<=30).sum()}")

    # 关键对比：keys_60s<=20 单独 vs T1 vs 两级
    print(f"\n===== 核心对比 =====")
    print(f"{'规则':<32s} {'Hit':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
    print("-" * 64)
    rules = {
        "T1 (pause>30s)": None,  # 需要 pause，从 two_stage 结果引用
        "keys60<15": res["keys60"] < 15,
        "keys60<20": res["keys60"] < 20,
        "keys60<25": res["keys60"] < 25,
        "keys60<30": res["keys60"] < 30,
    }
    # T1 需要 pause_sec，这里重新算
    print("(T1 结果见 two_stage_eval.py: Prec 74.5% Rec 65.3% F1 69.6%)")
    for name, mask in rules.items():
        if mask is None:
            continue
        hit, tp, fp, fn, prec, rec, f1 = prf(mask, res["label"])
        print(f"{name:<32s} {hit:>5d} {tp:>4d} {fp:>4d} {fn:>4d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%}")

    # 误报明细
    norm = res[res["type"] == "NORMAL"]
    print(f"\n===== NORMAL 误报检查 =====")
    for k in [15, 20, 25, 30]:
        miss = norm[norm["keys60"] < k]
        fp = int((miss["label"] == 0).sum())
        print(f"K<{k}: 命中 {len(miss)} 条, 其中误报(应该0却<{k}) {fp} 条")
    # 显示误报的具体样本
    miss20 = norm[norm["keys60"] < 20]
    if len(miss20) > 0:
        print("\nkeys60<20 命中的 NORMAL 样本:")
        print(miss20.to_string())


if __name__ == "__main__":
    main()
