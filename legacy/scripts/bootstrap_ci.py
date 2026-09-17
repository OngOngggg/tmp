"""bootstrap 置信区间：keys_30s<5 规则的 P/R/F1 稳定性。

对 183 条标注有放回抽样 2000 次，每次算 P/R/F1，报告 95% CI。
"""
import os, json, re
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
EXPORT = r"D:\02_code\project\python\oj_demo\data\export"
RNG = np.random.default_rng(42)


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


def prf(hit, tp, total_pos):
    fp = hit - tp
    fn = total_pos - tp
    prec = tp / hit if hit > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    return prec, rec, f1


def main():
    labels = pd.read_csv(os.path.join(DATA, "labels.csv"))
    sid_batch = build_index()

    # 提取 keys_30s
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
        m30 = (times >= trig_ts - np.timedelta64(30, "s")) & (times < trig_ts)
        rows.append({"label": int(r["label"]), "keys30": int(m30.sum())})
    res = pd.DataFrame(rows)
    print(f"样本: {len(res)}, 正样本: {res['label'].sum()}")

    labels_arr = res["label"].values
    keys30_arr = res["keys30"].values
    total_pos = int(labels_arr.sum())

    # 原始值
    hit0 = int((keys30_arr < 5).sum())
    tp0 = int(((keys30_arr < 5) & (labels_arr == 1)).sum())
    p0, r0, f0 = prf(hit0, tp0, total_pos)
    print(f"\n原始 keys_30s<5: Prec={p0:.1%}, Rec={r0:.1%}, F1={f0:.1%}")

    # bootstrap
    n = len(res)
    B = 2000
    precs, recs, f1s = [], [], []
    for _ in range(B):
        idx = RNG.integers(0, n, n)
        lab = labels_arr[idx]
        k30 = keys30_arr[idx]
        hit = int((k30 < 5).sum())
        tp = int(((k30 < 5) & (lab == 1)).sum())
        pos = int(lab.sum())
        p, r, f = prf(hit, tp, pos)
        precs.append(p); recs.append(r); f1s.append(f)

    for name, arr, orig in [("Precision", precs, p0), ("Recall", recs, r0), ("F1", f1s, f0)]:
        lo, hi = np.percentile(arr, [2.5, 97.5])
        print(f"{name:>10s}: {orig:.1%}  (95% CI [{lo:.1%}, {hi:.1%}])")

    # 分类型 bootstrap（IDLE / DEBUG / NORMAL 各自）
    print("\n===== 分类型（原始值 + CI） =====")
    for t in ["IDLE", "DEBUG", "NORMAL"]:
        sub = res[res["type"] == t] if "type" in res.columns else None
    # 需要 type 字段，重新提取
    rows2 = []
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
        m30 = (times >= trig_ts - np.timedelta64(30, "s")) & (times < trig_ts)
        rows2.append({"label": int(r["label"]), "type": r["type"], "keys30": int(m30.sum())})
    res2 = pd.DataFrame(rows2)
    for t in ["IDLE", "DEBUG", "NORMAL"]:
        sub = res2[res2["type"] == t]
        if len(sub) == 0:
            continue
        lab = sub["label"].values
        k30 = sub["keys30"].values
        hit0 = int((k30 < 5).sum())
        tp0 = int(((k30 < 5) & (lab == 1)).sum())
        p0, r0, f0 = prf(hit0, tp0, int(lab.sum()))
        precs, recs = [], []
        nn = len(sub)
        for _ in range(1000):
            idx = RNG.integers(0, nn, nn)
            l2 = lab[idx]; k2 = k30[idx]
            h = int((k2 < 5).sum()); t2 = int(((k2 < 5) & (l2 == 1)).sum())
            p, r, _ = prf(h, t2, int(l2.sum()))
            precs.append(p); recs.append(r)
        plo, phi = np.percentile(precs, [2.5, 97.5])
        rlo, rhi = np.percentile(recs, [2.5, 97.5])
        print(f"{t}: n={len(sub)}, pos={int(lab.sum())}, "
              f"Prec={p0:.1%} [{plo:.1%},{phi:.1%}], Rec={r0:.1%} [{rlo:.1%},{rhi:.1%}]")


if __name__ == "__main__":
    main()
