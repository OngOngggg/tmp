"""
RF 分类器：从 candidates CSV 的按键序列字符串直接提取特征，十折交叉验证。
"""
import re, os, sys
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_predict, StratifiedKFold
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
LABELS = os.path.join(DATA_DIR, "labels.csv")
CANDIDATES = os.path.join(DATA_DIR, "candidates_200.csv")


def parse_key_seq(seq_str):
    """从压缩按键字符串提取统计信息"""
    if not seq_str or pd.isna(seq_str):
        return {"bs": 0, "enter": 0, "ctrl": 0, "total": 0}
    # Parse "Backspacex4 → 1 → 2 → Enter → Shiftx3"
    bs = enter = ctrl = total = 0
    parts = re.split(r'\s*→\s*', str(seq_str))
    for p in parts:
        p = p.strip()
        if not p: continue
        m = re.match(r'(.+?)x(\d+)$', p)
        key = m.group(1) if m else p
        count = int(m.group(2)) if m else 1
        total += count
        if key == "Backspace": bs += count
        elif key == "Enter": enter += count
        elif key == "Control": ctrl += count
    return {"bs": bs, "enter": enter, "ctrl": ctrl, "total": total}


def main():
    labels = pd.read_csv(LABELS)
    cand = pd.read_csv(CANDIDATES)

    # Merge
    cand["detail"] = cand["detail"].astype(str)
    labels["detail"] = labels["detail"].astype(str)
    cand_clean = cand.drop(columns=["label"], errors="ignore").drop_duplicates(subset=["solution_id", "detail"])
    df = labels.merge(cand_clean, on=["solution_id", "type", "detail"], how="inner", suffixes=("", "_cand"))

    # Build feature matrix
    rows = []
    for _, r in df.iterrows():
        # Parse 30s before/after key sequences
        before = parse_key_seq(str(r.get("keys_30s_before", "")))
        after = parse_key_seq(str(r.get("keys_30s_after", "")))
        before10 = parse_key_seq(str(r.get("keys_10s_before", "")))
        after10 = parse_key_seq(str(r.get("keys_10s_after", "")))

        code = str(r.get("code_at_trigger", ""))
        dur = float(r.get("duration_s", 1))
        keys = int(r.get("total_keys", 10))

        feats = {
            # Behavior features
            "bs_30s_before": before["bs"],
            "bs_30s_after": after["bs"],
            "enter_30s_before": before["enter"],
            "enter_30s_after": after["enter"],
            "ctrl_30s_before": before["ctrl"],
            "ctrl_30s_after": after["ctrl"],
            "keys_30s_before": before["total"],
            "keys_30s_after": after["total"],
            "keys_10s_before": before10["total"],
            "keys_10s_after": after10["total"],
            # Session features
            "session_kpm": keys / max(dur, 1) * 60,
            "code_length": len(code),
            "code_lines": code.count("\n") + 1 if code.strip() else 0,
        }
        feats["bs_ratio_30s"] = before["bs"] / max(before["total"], 1)
        feats["label"] = int(r["label"])
        rows.append(feats)

    df2 = pd.DataFrame(rows)
    print(f"Samples: {len(df2)}")
    print(f"YES: {df2['label'].sum()} ({df2['label'].mean()*100:.0f}%)")

    # RF
    feat_cols = [c for c in df2.columns if c != "label"]
    X = df2[feat_cols].fillna(0).values
    y = df2["label"].values

    cv = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
    rf = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, class_weight="balanced")
    y_pred = cross_val_predict(rf, X, y, cv=cv)

    acc = accuracy_score(y, y_pred)
    prec = precision_score(y, y_pred, zero_division=0)
    rec = recall_score(y, y_pred)
    f1 = f1_score(y, y_pred)

    print(f"\n=== RF (10-fold CV, {len(feat_cols)} features) ===")
    print(f"Accuracy:  {acc*100:.1f}%")
    print(f"Precision: {prec*100:.1f}%")
    print(f"Recall:    {rec*100:.1f}%")
    print(f"F1:        {f1*100:.1f}%")

    # Importance
    rf.fit(X, y)
    imps = list(zip(feat_cols, rf.feature_importances_))
    imps.sort(key=lambda x: -x[1])
    print(f"\n=== Feature Importance ===")
    for name, imp in imps:
        print(f"  {name:<25s} {imp:.3f} {'#'*int(imp*100)}")

    # Judge split
    print(f"\n=== By Judge ===")
    for j in sorted(df["judge"].unique()):
        mask = df["judge"] == j
        sub = df[mask]
        if len(sub) < 5: continue
        idx_list = sub.index.tolist()
        acc_j = (y_pred[idx_list] == y[idx_list]).mean()
        print(f"  {j}: {len(sub)} samples, RF acc={acc_j*100:.0f}%")

    # Comparison
    print(f"\n=== Method Comparison ===")
    print(f"  Rules:        78%")
    print(f"  LLM (0-shot): 67%")
    print(f"  RF:           {acc*100:.0f}%")


if __name__ == "__main__":
    main()
