"""
导出 key_action（全量，筛选 problem_id>0 且有 solution 记录）。
先查 csuoj_db.solution 获取有效 solution_id 集合，再只导出匹配的 rows。
"""
import pymysql
import pandas as pd
import os

HOST = "122.207.108.6"
PORT_KEY = 19106   # experiment_data
PORT_SOL = 53306   # csuoj_db
USER = "root"
PASSWORD = os.environ.get("OJ_DB_PASSWORD", "")

BATCH_SIZE = 1000
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "export")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def main():
    # Step 1: get all valid solution_ids from csuoj_db.solution
    print("Step 1: fetching valid solution_ids from csuoj_db ...")
    conn_sol = pymysql.connect(host=HOST, port=PORT_SOL, user=USER,
                               password=PASSWORD, database="csuoj_db",
                               charset="utf8mb4", connect_timeout=10, read_timeout=120)

    # Get distinct solution_ids from key_action, then check which exist in solution
    conn_key = pymysql.connect(host=HOST, port=PORT_KEY, user=USER,
                               password=PASSWORD, database="experiment_data",
                               charset="utf8mb4", connect_timeout=10, read_timeout=120)
    cur_key = conn_key.cursor()

    # Count total
    cur_key.execute("SELECT COUNT(*) FROM key_action WHERE problem_id > 0")
    total = cur_key.fetchone()[0]
    print(f"  key_action rows with problem_id>0: {total:,}")

    # Get all distinct solution_ids
    cur_key.execute("SELECT DISTINCT solution_id FROM key_action WHERE problem_id > 0")
    all_sids = [r[0] for r in cur_key.fetchall()]
    print(f"  distinct solution_ids: {len(all_sids):,}")

    # Check which exist in solution
    cur_sol = conn_sol.cursor()
    valid_sids = set()
    for i in range(0, len(all_sids), 5000):
        chunk = all_sids[i:i+5000]
        ph = ",".join(["%s"] * len(chunk))
        cur_sol.execute(f"SELECT id FROM solution WHERE id IN ({ph})", chunk)
        for r in cur_sol.fetchall():
            valid_sids.add(r[0])
    print(f"  valid (exist in solution): {len(valid_sids):,}")
    conn_sol.close()

    # Step 2: export key_action rows with valid solution_ids
    print(f"\nStep 2: exporting key_action rows with valid solution_ids ...")
    cur_key.execute(
        "SELECT id, action, solution_id, start_time, problem_id, created_by, created_time "
        "FROM key_action WHERE problem_id > 0 ORDER BY id"
    )

    batch_num = 0
    total_exported = 0
    while True:
        rows = cur_key.fetchmany(BATCH_SIZE)
        if not rows: break

        batch_num += 1
        df = pd.DataFrame(rows, columns=["id", "action", "solution_id", "start_time",
                                          "problem_id", "created_by", "created_time"])
        # Filter to valid sids
        df = df[df["solution_id"].isin(valid_sids)]

        if len(df) == 0: continue

        filepath = os.path.join(OUTPUT_DIR, f"key_action_batch_{batch_num:03d}.csv")
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        total_exported += len(df)

        if batch_num % 10 == 0:
            print(f"  batch {batch_num}: {total_exported:,} rows exported so far")

    conn_key.close()

    # Clean up old batch files with invalid sids
    files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".csv")])
    total_size = sum(os.path.getsize(os.path.join(OUTPUT_DIR, f)) for f in files)
    print(f"\nDone: {len(files)} files, {total_exported:,} rows, {total_size/(1024**3):.1f} GB")


if __name__ == "__main__":
    main()
