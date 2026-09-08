"""标注工具 v3：代码快照 + 多窗口序列 + 完整提交代码"""
import os, pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CANDIDATES = os.path.join(DATA_DIR, "candidates_200.csv")
LABELS = os.path.join(DATA_DIR, "labels.csv")


def show(row, idx, total):
    sid = int(row["solution_id"]); pid = int(row["problem_id"])
    judge = row["judge"]; ttype = row["type"]; detail = row["detail"]
    dur = float(row.get("duration_s", 0)); keys = int(row.get("total_keys", 0))

    print(f"\n{'='*70}")
    print(f"  #{idx}/{total}  SID={sid}  PID={pid}  Judge={judge}")
    print(f"  {ttype}: {detail}  |  {keys}keys  {dur:.0f}s  ~{keys/max(dur,1)*60:.0f}kpm")
    print("-"*70)

    # Keys at 10s/20s/30s (may be missing for negatives)
    for w in [10, 20, 30]:
        b = str(row.get(f"keys_{w}s_before", ""))
        a = str(row.get(f"keys_{w}s_after", ""))
        if b in ('nan','None',''): b = ''
        if a in ('nan','None',''): a = ''
        if b: print(f"  前{w}s: {b[:300]}")
        if a: print(f"  后{w}s: {a[:300]}")

    # Code at trigger (replay)
    code_at = str(row.get("code_at_trigger", ""))
    if code_at.strip():
        lines = code_at.strip().split("\n")
        real = [l for l in lines if len(l) > 1]
        if real:
            print(f"\n  [Trigger Time Code Replay] ({len(real)} lines):")
            for line in real[-15:]:
                print(f"    | {line[:100]}")

    # Submitted code (full)
    sub = str(row.get("submitted_code", ""))
    if sub.strip():
        lines = sub.strip().split("\n")
        print(f"\n  [Submitted Code] ({len(lines)} lines):")
        for line in lines[:20]:
            print(f"    | {line[:100]}")
        if len(lines) > 20:
            print(f"    ... ({len(lines)-20} more lines)")
    else:
        print(f"\n  [Submitted Code]: (none)")

    print("-"*70)


def main():
    df = pd.read_csv(CANDIDATES)
    # 追加负样本
    neg_path = os.path.join(DATA_DIR, "negatives_30.csv")
    if os.path.exists(neg_path):
        neg = pd.read_csv(neg_path)
        df = pd.concat([df, neg], ignore_index=True)
    if "label" not in df.columns: df["label"] = ""

    existing = pd.read_csv(LABELS) if os.path.exists(LABELS) else None
    done = set()
    labels_list = []
    if existing is not None:
        labels_list = existing.to_dict("records")
        for _, r in existing.iterrows():
            done.add((int(r["solution_id"]), str(r.get("detail", ""))))
        print(f"Loaded {len(labels_list)} existing, skipping done.\n")

    total = len(df)
    for idx, (_, row) in enumerate(df.iterrows()):
        key = (int(row["solution_id"]), str(row.get("detail", "")))
        if key in done: continue

        show(row, idx + 1, total)
        while True:
            ans = input("  Label (1=YES 0=NO s=skip q=quit): ").strip().lower()
            if ans in ["1", "0", "s", "q"]: break
        if ans == "q": break
        if ans == "s": continue

        labels_list.append({
            "solution_id": int(row["solution_id"]),
            "problem_id": int(row["problem_id"]),
            "judge": row["judge"],
            "type": row["type"],
            "detail": str(row.get("detail", "")),
            "label": int(ans),
        })
        if len(labels_list) % 10 == 0:
            pd.DataFrame(labels_list).to_csv(LABELS, index=False)
            print(f"  [Saved {len(labels_list)}]")

    if labels_list:
        pd.DataFrame(labels_list).to_csv(LABELS, index=False)
    df2 = pd.DataFrame(labels_list)
    if len(df2) > 0:
        n1 = int(df2["label"].sum())
        print(f"\nDone: {len(df2)}, YES={n1} ({n1/len(df2)*100:.0f}%)")


if __name__ == "__main__":
    print("1=YES 0=NO s=skip q=quit\n")
    main()
