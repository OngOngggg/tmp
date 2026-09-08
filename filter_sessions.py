"""
过滤数据集：30分钟内完成 + 有提交代码 + 有判题结果。
输出 labeling/data/clean_sessions.csv
"""
import os, json, re, time
import pandas as pd
import numpy as np
import pymysql

OUT_DIR = os.path.join(os.path.dirname(__file__), "labeling", "data")
os.makedirs(OUT_DIR, exist_ok=True)

MAX_DURATION = 1800  # 30 min
MIN_KEYS = 10
BATCH_ROWS = 5000

RESULT_MAP = {4: "AC", 5: "PE", 6: "WA", 7: "TLE", 8: "MLE",
              9: "OLE", 10: "NoData", 11: "CE", 13: "RE"}


def parse_time(s):
    s = re.sub(r':(\d+)$', r'.\1', str(s))
    for f in ['%Y/%m/%d %H:%M:%S.%f', '%m/%d/%Y, %I:%M:%S %p.%f',
              '%Y-%m-%d %I:%M:%S %p.%f', '%d/%m/%Y, %H:%M:%S.%f']:
        try: return pd.to_datetime(s, format=f)
        except: pass
    return None


def main():
    # Step 1: Scan key_action, compute duration, filter
    print("Step 1: Scanning key_action for valid sessions...")
    conn = pymysql.connect(host="122.207.108.6", port=19106,
                           user="root", password=os.environ.get("OJ_DB_PASSWORD", ""),
                           database="experiment_data", charset="utf8mb4",
                           connect_timeout=10, read_timeout=300)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM key_action WHERE problem_id > 0")
    total = cur.fetchone()[0]
    cur.execute("SELECT solution_id, action FROM key_action WHERE problem_id > 0 ORDER BY id")

    valid_sessions = []  # (sid, duration, key_count)
    done = 0; t0 = time.time()
    while True:
        rows = cur.fetchmany(BATCH_ROWS)
        if not rows: break
        for sid, action_json in rows:
            try: actions = json.loads(action_json)
            except: continue
            first_ts = None; last_ts = None; nk = 0
            for a in actions:
                if not isinstance(a, dict) or a.get("type") != "down": continue
                ts = parse_time(a.get("time", ""))
                if ts is None: continue
                if first_ts is None: first_ts = ts
                last_ts = ts; nk += 1
            if first_ts is None or last_ts is None or nk < MIN_KEYS: continue
            dur = (last_ts - first_ts).total_seconds()
            if dur <= 0 or dur > MAX_DURATION: continue
            valid_sessions.append((sid, dur, nk))
        done += len(rows)
        elapsed = time.time() - t0
        eta = (elapsed / done * (total - done)) if done > 0 else 0
        pct = done / total
        bar = "█" * int(pct * 30) + "░" * (30 - int(pct * 30))
        print(f"\r  [{bar}] {pct*100:.0f}% | {done:,}/{total:,} | valid={len(valid_sessions):,} | {eta/60:.0f}min left   ", end="", flush=True)
    print()  # newline after done
    conn.close()
    print(f"  Valid sessions: {len(valid_sessions):,}")

    # Step 2: Fetch judge results
    print("\nStep 2: Fetching judge results...")
    sids = [s[0] for s in valid_sessions]
    conn2 = pymysql.connect(host="122.207.108.6", port=53306,
                            user="root", password=os.environ.get("OJ_DB_PASSWORD", ""),
                            database="csuoj_db", charset="utf8mb4",
                            connect_timeout=10, read_timeout=120)
    cur2 = conn2.cursor()
    judge_map = {}; pid_map = {}
    for i in range(0, len(sids), 1000):
        chunk = sids[i:i+1000]
        ph = ",".join(["%s"] * len(chunk))
        cur2.execute(f"SELECT id, result, problem_id FROM solution WHERE id IN ({ph})", chunk)
        for r in cur2.fetchall():
            judge_map[r[0]] = RESULT_MAP.get(r[1], "?")
            pid_map[r[0]] = r[2]
        if i % 10000 == 0: print(f"  {i:,}/{len(sids):,}")
    conn2.close()
    print(f"  Judges matched: {len(judge_map):,}")

    # Step 3: Fetch submitted codes
    print("\nStep 3: Fetching submitted codes...")
    conn3 = pymysql.connect(host="122.207.108.6", port=53306,
                            user="root", password=os.environ.get("OJ_DB_PASSWORD", ""),
                            database="csuoj_db", charset="utf8mb4",
                            connect_timeout=10, read_timeout=120)
    cur3 = conn3.cursor()
    code_map = {}
    for i in range(0, len(sids), 1000):
        chunk = sids[i:i+1000]
        ph = ",".join(["%s"] * len(chunk))
        cur3.execute(f"SELECT solution_id, code FROM source_code WHERE solution_id IN ({ph})", chunk)
        for r in cur3.fetchall():
            code_map[r[0]] = r[1] or ""
        if i % 10000 == 0: print(f"  {i:,}/{len(sids):,}")
    conn3.close()
    print(f"  Codes matched: {len(code_map):,}")

    # Step 4: Assemble
    print("\nStep 4: Assembling final CSV...")
    rows = []
    for sid, dur, keys in valid_sessions:
        rows.append({
            "solution_id": sid,
            "problem_id": pid_map.get(sid, 0),
            "judge": judge_map.get(sid, "?"),
            "has_code": sid in code_map and len(code_map[sid]) > 10,
            "duration_s": round(dur, 1),
            "total_keys": keys,
        })
    df = pd.DataFrame(rows)
    out = os.path.join(OUT_DIR, "clean_sessions.csv")
    df.to_csv(out, index=False)

    both = ((df["judge"] != "?") & df["has_code"]).sum()
    print(f"\nTotal: {len(df):,}")
    print(f"  with judge: {(df['judge']!='?').sum():,}")
    print(f"  with code:  {df['has_code'].sum():,}")
    print(f"  BOTH:       {both:,}")
    print(f"\nJudge dist:")
    for j, c in df["judge"].value_counts().items():
        print(f"  {j}: {c:,}")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
