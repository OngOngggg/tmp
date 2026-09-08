"""Stability analysis for the real user-labeled prototype windows.

Reports session-bootstrap intervals, a mixed-session-only audit, and threshold
sensitivity. This is intentionally separate from the AI-completed evaluation.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
USER = Path(r"C:\Users\10950\Downloads\prototype_labels.csv")
OUT = DATA / "prototype_rule_stability.csv"
REPORT = DATA / "prototype_rule_stability.md"


def score(df: pd.DataFrame, pred: pd.Series) -> dict[str, float | int]:
    y = df.label.astype(int)
    return {
        "n": len(df), "positive": int(y.sum()), "trigger": int(pred.sum()),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
    }


def main() -> None:
    windows = pd.read_csv(WINDOWS)
    labels = pd.read_csv(USER)
    d = windows.merge(labels[["window_id", "solution_id", "label"]], on=["window_id", "solution_id"], validate="one_to_one")
    d = d[d.label.isin([0, 1])].copy()
    d["pred"] = (d.current_idle_s >= 30) & (d.keys_30s < 5) & (d.clipboard_ops_30s == 0)

    rng = np.random.default_rng(42)
    sessions = d.solution_id.unique()
    samples = []
    for _ in range(2000):
        chosen = rng.choice(sessions, size=len(sessions), replace=True)
        sample = pd.concat([d[d.solution_id == sid] for sid in chosen], ignore_index=True)
        samples.append(score(sample, sample.pred))
    boot = pd.DataFrame(samples)
    base = score(d, d.pred)

    session_labels = d.groupby("solution_id").label.nunique()
    mixed_ids = session_labels[session_labels > 1].index
    mixed = d[d.solution_id.isin(mixed_ids)].copy()
    mixed_score = score(mixed, mixed.pred)

    rows = []
    for idle in [20, 25, 30, 35, 40, 45, 60]:
        for keys in [2, 3, 4, 5, 6, 8, 10]:
            pred = (d.current_idle_s >= idle) & (d.keys_30s < keys) & (d.clipboard_ops_30s == 0)
            row = {"idle_min": idle, "keys30_max_exclusive": keys}
            row.update(score(d, pred))
            rows.append(row)
    sensitivity = pd.DataFrame(rows).sort_values(["f1", "precision"], ascending=False)
    sensitivity.to_csv(OUT, index=False, encoding="utf-8-sig")

    def ci(col: str) -> tuple[float, float]:
        return float(boot[col].quantile(.025)), float(boot[col].quantile(.975))

    report = [
        "# Prototype 规则稳定性分析",
        "",
        "规则：`current_idle_s >= 30 && keys_30s < 5 && clipboard_ops_30s == 0`。",
        "",
        f"- 全部人工确定标签：n={base['n']}，session={len(sessions)}，Precision={base['precision']:.1%}，Recall={base['recall']:.1%}，F1={base['f1']:.1%}。",
        f"- 按 session bootstrap 2000 次：Precision 95% CI [{ci('precision')[0]:.1%}, {ci('precision')[1]:.1%}]；Recall 95% CI [{ci('recall')[0]:.1%}, {ci('recall')[1]:.1%}]；F1 95% CI [{ci('f1')[0]:.1%}, {ci('f1')[1]:.1%}]。",
        f"- 仅保留 session 内同时出现 0/1 的混合子集：n={mixed_score['n']}，session={len(mixed_ids)}，Precision={mixed_score['precision']:.1%}，Recall={mixed_score['recall']:.1%}，F1={mixed_score['f1']:.1%}。",
        "",
        "## 阈值敏感性前10",
        "",
        sensitivity.head(10).to_markdown(index=False),
        "",
        "## 解释",
        "",
        "置信区间较宽或混合 session 子集性能明显变化，说明当前样本量和标注方式不足以支持精确阈值。下一步应补标跨状态边界窗口，并以 session 为单位做留出验证。",
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("base", base)
    print("mixed", mixed_score, "sessions", len(mixed_ids))
    print("precision_ci", ci("precision"), "recall_ci", ci("recall"), "f1_ci", ci("f1"))
    print("report", REPORT)


if __name__ == "__main__":
    main()
