"""T1-T5 候选规则对比评估（在 183 条标注集上）.

规则定义：
  T1: idle > 35s（基线）
  T2: T1 且 5 分钟内有提交（尤其 WA/TLE/RE）— 失败边界+暂停
  T3: T1 且近 30s 退格爆发(>=2段)且无粘贴(ctrl<=1)
  T4: T1 且近 60s 代码长度无变化
  T5: T2 OR T3（联合规则）
"""
import os, json, re
import numpy as np
import pandas as pd
import pymysql

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
    """sid -> (batch_no, problem_id, judge)"""
    idx = {}
    for b in range(1, 200):
        fp = os.path.join(EXPORT, f"key_action_batch_{b:03d}.csv")
        if not os.path.exists(fp):
            break
        df = pd.read_csv(fp, usecols=["solution_id", "problem_id"])
        for sid, pid in zip(df["solution_id"], df["problem_id"]):
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
        downs.append((a["key"], ts, a.get("row", 0)))
    if len(downs) < 10:
        return None
    keys = np.array([k for k, t, r in downs])
    times = np.array([t for k, t, r in downs], dtype="datetime64[ns]")
    rows = np.array([r for k, t, r in downs])
    return {"keys": keys, "times": times, "rows": rows,
            "start": times[0], "end": times[-1]}


def replay_code(keys, start, end):
    """回放 [start,end) 区间的按键序列，尽力重建代码文本。"""
    ignore = {"Control", "Shift", "Alt", "Meta", "CapsLock", "Escape", "Tab",
              "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End",
              "PageUp", "PageDown", "Insert", "Delete", "Dead", "Process",
              "NumLock", "ScrollLock", "Pause"}
    code = ""
    for k in keys[start:end]:
        if k in ignore:
            continue
        if k == "Backspace":
            code = code[:-1] if code else ""
        elif k == "Enter":
            code += "\n"
        elif k == " " or k == "Space":
            code += " "
        elif len(k) == 1:
            code += k
    return code


def find_trigger_moment(session, ttype, detail):
    """找触发时刻索引。IDLE: 第一个 >30s 停顿；DEBUG: 删后停顿点；NORMAL: session 中部。"""
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
    else:  # NORMAL
        return n // 2


def eval_rules():
    labels = pd.read_csv(os.path.join(DATA, "labels.csv"))
    cand = pd.read_csv(os.path.join(DATA, "candidates_200.csv"))
    # 合并候选特征（keys_30s_before 等）
    cand = cand.drop(columns=["label"], errors="ignore")
    # candidates 可能含重复触发行，去重避免 merge 膨胀
    cand = cand.drop_duplicates(subset=["solution_id", "type", "detail"], keep="first")
    cand["detail"] = cand["detail"].astype(str)
    labels["detail"] = labels["detail"].astype(str)
    df = labels.merge(cand, on=["solution_id", "type", "detail"], how="left",
                      suffixes=("", "_cand"))
    print(f"标注样本: {len(df)} (label=1: {df['label'].sum()})")

    print("建立 session 索引...")
    sid_batch = build_index()
    print(f"索引: {len(sid_batch)} sessions")

    # 查提交时间（一次性）
    sids = df["solution_id"].unique().tolist()
    submit_time = {}
    verdict = {}
    try:
        conn = pymysql.connect(host="122.207.108.6", port=53306,
                               user="root", password=os.environ.get("OJ_DB_PASSWORD", ""),
                               database="csuoj_db", charset="utf8mb4",
                               connect_timeout=10, read_timeout=120)
        cur = conn.cursor()
        for i in range(0, len(sids), 500):
            chunk = sids[i:i + 500]
            ph = ",".join(["%s"] * len(chunk))
            cur.execute(f"SELECT id, created_time, result FROM solution WHERE id IN ({ph})", chunk)
            for r in cur.fetchall():
                submit_time[r[0]] = pd.to_datetime(str(r[1]))
                verdict[r[0]] = r[2]
        conn.close()
    except Exception as e:
        print(f"数据库不可用，跳过 T2/T5 的提交时间条件: {e}")
    print(f"提交时间: {len(submit_time)} 条")

    # 逐条评估
    rows = []
    for _, r in df.iterrows():
        sid = int(r["solution_id"])
        batch = sid_batch.get(sid)
        if batch is None:
            continue
        session = load_session(sid, batch)
        if session is None:
            continue
        trig = find_trigger_moment(session, r["type"], str(r["detail"]))
        trig_ts = session["times"][trig]
        keys, times, rows_arr = session["keys"], session["times"], session["rows"]
        n = len(times)

        # 停顿时长
        pause_sec = (trig_ts - times[trig - 1]).astype("timedelta64[ms]").astype(float) / 1000.0 if trig > 0 else 0

        # 30s 窗口统计
        m30 = (times >= trig_ts - np.timedelta64(30, "s")) & (times < trig_ts)
        wk30 = keys[m30]
        bs30 = int((wk30 == "Backspace").sum())
        ctrl30 = int((wk30 == "Control").sum())
        # 退格爆发段数
        bursts = 0
        in_b = False
        for k in wk30:
            if k == "Backspace":
                if not in_b:
                    bursts += 1
                    in_b = True
            else:
                in_b = False

        # 60s 窗口按键数与代码长度变化
        m60 = (times >= trig_ts - np.timedelta64(60, "s")) & (times < trig_ts)
        keys60 = int(m60.sum())
        # 代码回放：trig-60s 与 trig 两个快照（仅当 60s 内有事件时）
        if keys60 > 0:
            t60_ts = trig_ts - np.timedelta64(60, "s")
            start_idx = int(np.searchsorted(times, t60_ts, side="right"))
            code_before = replay_code(keys, start_idx, trig)
            code_at = replay_code(keys, trig, n)
            code_len_delta = abs(len(code_at) - len(code_before))
        else:
            code_len_delta = 0

        # 提交间隔
        st = submit_time.get(sid)
        time_since_sub = None
        if st is not None:
            time_since_sub = (trig_ts - np.datetime64(st)).astype("timedelta64[ms]").astype(float) / 1000.0
        last_verdict = verdict.get(sid)
        recent_fail = (time_since_sub is not None and time_since_sub <= 300
                       and last_verdict in (6, 7, 8, 13)) if last_verdict is not None else False

        # T1-T5 命中
        t1 = pause_sec > 35
        t2 = t1 and recent_fail
        t3 = t1 and bursts >= 2 and ctrl30 <= 1
        t4 = t1 and code_len_delta == 0
        t5 = t2 or t3

        rows.append({
            "solution_id": sid, "label": int(r["label"]), "type": r["type"],
            "pause_sec": round(pause_sec, 1), "keys60": keys60,
            "bs30": bs30, "ctrl30": ctrl30, "bursts30": bursts,
            "code_len_delta60": code_len_delta,
            "time_since_sub": round(time_since_sub, 0) if time_since_sub is not None else None,
            "T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5,
        })

    res = pd.DataFrame(rows)
    print(f"评估样本: {len(res)} (label=1: {res['label'].sum()})")

    # 补充：如果数据库不可用，T2/T5 退化为 T1 的近似，给个标记
    if not submit_time:
        print("警告: 提交时间未获取，T2/T5 实际等价于 T1/近退格条件，结果仅供结构参考")

    # P/R/F1
    print(f"\n{'Rule':<6s} {'Hit':>5s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'Prec':>7s} {'Rec':>7s} {'F1':>7s}")
    print("-" * 60)
    for rule in ["T1", "T2", "T3", "T4", "T5"]:
        hit = res[rule].sum()
        tp = ((res[rule]) & (res["label"] == 1)).sum()
        fp = hit - tp
        fn = (res["label"] == 1).sum() - tp
        prec = tp / hit if hit > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        print(f"{rule:<6s} {hit:>5d} {tp:>4d} {fp:>4d} {fn:>4d} {prec:>6.1%} {rec:>6.1%} {f1:>6.1%}")

    # NORMAL 样本误报
    norm = res[res["type"] == "NORMAL"]
    print(f"\nNORMAL(正常编码)样本误报: {len(norm)} 条中")
    for rule in ["T1", "T2", "T3", "T4", "T5"]:
        fp = norm[rule].sum()
        print(f"  {rule}: {fp} 条误触发 ({fp/len(norm)*100:.0f}%)")


if __name__ == "__main__":
    eval_rules()
