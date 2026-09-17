"""
检测 + 标注数据生成：每条候选带代码快照 + 多窗口按键序列 + 提交代码
"""
import os, json, re, random
import pandas as pd
import numpy as np
import pymysql

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
EXPORT_DIR = os.path.join(os.path.dirname(ROOT), "data", "export")
os.makedirs(DATA_DIR, exist_ok=True)
CLEAN = os.path.join(DATA_DIR, "clean_sessions.csv")
random.seed(42)

IDLE_THRESHOLD = 30
BS_PAUSE_MIN = 2
WINDOW_SEC = 10
BS_COUNT_MIN = 2
KEYS_MIN = 10

IGNORE = {"Control","Shift","Alt","Meta","CapsLock","Escape","Tab",
          "ArrowUp","ArrowDown","ArrowLeft","ArrowRight","Home","End",
          "PageUp","PageDown","Insert","Delete","Dead","Process","NumLock"}
DELETE = {"Backspace"}


def parse_time(s):
    s = re.sub(r':(\d+)$', r'.\1', str(s))
    for f in ['%Y/%m/%d %H:%M:%S.%f','%m/%d/%Y, %I:%M:%S %p.%f','%Y-%m-%d %I:%M:%S %p.%f','%d/%m/%Y, %H:%M:%S.%f']:
        try: return pd.to_datetime(s, format=f)
        except: pass
    return None


def replay_code(keys):
    code = ""
    for k in keys:
        if k in IGNORE: continue
        if k in DELETE: code = code[:-1] if code else ""
        elif k == "Enter": code += "\n"
        elif k == " " or k == "Space": code += " "
        elif len(k) == 1: code += k
    return code


def key_seq(keys, max_len=50):
    """压缩按键序列"""
    parts = []; prev = None; cnt = 0
    for k in keys[:200]:
        if k == prev: cnt += 1
        else:
            if cnt > 0: parts.append(f"{prev}" if cnt == 1 else f"{prev}x{cnt}")
            prev = k; cnt = 1
    if cnt > 0: parts.append(f"{prev}" if cnt == 1 else f"{prev}x{cnt}")
    return " → ".join(parts[:max_len])


def main():
    clean = pd.read_csv(CLEAN)
    valid_sids = set(int(s) for s in clean["solution_id"])
    print(f"Clean SIDs: {len(valid_sids):,}")

    # Fetch all submitted codes upfront
    print("Fetching submitted codes...")
    conn = pymysql.connect(host="122.207.108.6", port=53306,
                           user="root", password=os.environ.get("OJ_DB_PASSWORD", ""),
                           database="csuoj_db", charset="utf8mb4",
                           connect_timeout=10, read_timeout=300)
    cur = conn.cursor()
    code_map = {}
    sids_list = list(valid_sids)
    for i in range(0, len(sids_list), 2000):
        chunk = sids_list[i:i+2000]
        ph = ",".join(["%s"] * len(chunk))
        cur.execute(f"SELECT solution_id, code FROM source_code WHERE solution_id IN ({ph})", chunk)
        for r in cur.fetchall():
            code_map[r[0]] = r[1] or ""
        if i % 20000 == 0: print(f"  {i}/{len(sids_list)}")
    conn.close()
    print(f"  Codes: {len(code_map)}")

    # Scan sessions, run detection, extract context
    print("Scanning sessions...")
    rows = []
    n_sessions = 0
    for batch in range(1, 200):
        fp = os.path.join(EXPORT_DIR, f"key_action_batch_{batch:03d}.csv")
        if not os.path.exists(fp): break
        df = pd.read_csv(fp)
        for _, row in df.iterrows():
            sid = int(row["solution_id"])
            if sid not in valid_sids: continue
            try: actions = json.loads(row["action"])
            except: continue

            downs = []
            for a in actions:
                if not isinstance(a, dict) or a.get("type") != "down": continue
                ts = parse_time(a.get("time", ""))
                if ts is None: continue
                downs.append((a.get("key", "?"), ts))
            if len(downs) < KEYS_MIN: continue

            keys_arr = np.array([k for k, t in downs])
            times_arr = np.array([t for k, t in downs], dtype="datetime64[ns]")
            is_bs = (keys_arr == "Backspace")
            n = len(times_arr)
            n_sessions += 1

            # Precompute full code
            full_code = replay_code([k for k, t in downs])
            info = clean[clean["solution_id"] == sid].iloc[0]
            pid = int(info["problem_id"])
            judge = info["judge"]
            dur = float(info["duration_s"])
            tkeys = int(info["total_keys"])
            sub_code = code_map.get(sid, "")

            def add_candidate(trig_ts, ttype, detail):
                # Code at trigger
                code_at = replay_code([k for k, t in downs if t < trig_ts])

                # Window key sequences
                seqs = {}
                for w in [10, 20, 30]:
                    for label, delta in [("before", -w), ("after", w)]:
                        if delta < 0: start, end = trig_ts + np.timedelta64(delta, "s"), trig_ts
                        else: start, end = trig_ts, trig_ts + np.timedelta64(delta, "s")
                        mask = (times_arr >= start) & (times_arr < end)
                        seqs[f"keys_{w}s_{label}"] = key_seq(keys_arr[mask])

                rows.append({
                    "solution_id": sid, "problem_id": pid, "judge": judge,
                    "type": ttype, "detail": detail,
                    "duration_s": dur, "total_keys": tkeys,
                    "code_at_trigger": code_at[-600:],
                    "submitted_code": sub_code,
                    **seqs,
                })

            # IDLE
            intervals = np.diff(times_arr).astype("timedelta64[ms]").astype(float) / 1000.0
            for idx in range(1, n):
                pause = intervals[idx - 1]
                if pause > IDLE_THRESHOLD:
                    trig_ts = times_arr[idx]
                    recent = ((times_arr >= trig_ts - np.timedelta64(300, "s")) & (times_arr < trig_ts)).sum()
                    if recent < 50: continue
                    add_candidate(trig_ts, "IDLE", f"pause_{pause:.0f}s")

            # DEBUG
            bs_pauses = []
            for k in range(n - 1):
                if is_bs[k]:
                    gap = (times_arr[k + 1] - times_arr[k]).astype("timedelta64[ms]").astype(float) / 1000.0
                    if gap > BS_PAUSE_MIN:
                        bs_pauses.append((k, times_arr[k]))
            last_ts = None
            for bp_idx, bp_ts in bs_pauses:
                count = sum(1 for bi, bt in bs_pauses
                            if abs((bt - bp_ts).astype("timedelta64[ms]").astype(float) / 1000.0) <= WINDOW_SEC)
                if count < BS_COUNT_MIN: continue
                if last_ts is not None and abs((bp_ts - last_ts).astype("timedelta64[ms]").astype(float) / 1000.0) < WINDOW_SEC / 2: continue
                recent = ((times_arr >= bp_ts - np.timedelta64(300, "s")) & (times_arr < bp_ts)).sum()
                if recent < 50: continue
                add_candidate(bp_ts, "DEBUG", f"bs_pause_{count}x")
                last_ts = bp_ts

        if batch % 20 == 0:
            print(f"  batch {batch}, sessions={n_sessions}, candidates={len(rows)}")

    print(f"\nSessions: {n_sessions}, Candidates: {len(rows)}")

    # Sample
    rdf = pd.DataFrame(rows)
    sampled = []
    for t in ["IDLE", "DEBUG"]:
        sub = rdf[rdf["type"] == t]
        if len(sub) == 0: continue
        n_per = max(1, 100 // max(1, sub["judge"].nunique()))
        for j, g in sub.groupby("judge"):
            s = g.sample(n=min(n_per, len(g)), random_state=42)
            sampled.append(s)
    result = pd.concat(sampled).sample(frac=1, random_state=42).head(200).reset_index(drop=True)
    result["label"] = ""

    out = os.path.join(DATA_DIR, "candidates_200.csv")
    result.to_csv(out, index=False)
    ni = (result["type"] == "IDLE").sum()
    nd = (result["type"] == "DEBUG").sum()
    print(f"Sampled: {len(result)} ({ni} IDLE + {nd} DEBUG)")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
