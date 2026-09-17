"""Audit offline rules against only the user's exported labels.

This intentionally excludes AI-completed labels so reported performance is
not circular. It also reports per-session label consistency, since labeling an
entire problem with one value can make window-level metrics misleading.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
USER = Path(r"C:\Users\10950\Downloads\prototype_labels.csv")
OUT = DATA / "prototype_human_label_audit.csv"
SESSION_OUT = DATA / "prototype_human_label_session_consistency.csv"
REPORT = DATA / "prototype_human_label_audit.md"


def score(y: pd.Series, pred: pd.Series) -> dict[str, float | int]:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "trigger": int(pred.sum()), "tp": int(tp), "fp": int(fp), "fn": int(fn),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
    }


def main() -> None:
    windows = pd.read_csv(WINDOWS)
    labels = pd.read_csv(USER)
    d = windows.merge(labels[["window_id", "solution_id", "label"]], on=["window_id", "solution_id"], validate="one_to_one")
    d = d[d.label.isin([0, 1])].copy()
    y = d.label.astype(int)
    rules = {
        "frontend_10_40": d.current_idle_s.between(10, 40) & (d.text_keys_30s <= 3) &
                           (d.text_keys_60s >= 3) & (d.clipboard_ops_30s == 0),
        "frontend_10_45": d.current_idle_s.between(10, 45) & (d.text_keys_30s <= 3) &
                           (d.text_keys_60s > 0) & (d.clipboard_ops_30s == 0),
        "idle_30_no_text": (d.current_idle_s >= 30) & (d.text_keys_30s == 0),
        "keys30_lt5": d.keys_30s < 5,
    }
    rows = []
    for name, pred in rules.items():
        row = {"rule": name}
        row.update(score(y, pred.astype(int)))
        rows.append(row)
    audit = pd.DataFrame(rows)
    audit.to_csv(OUT, index=False, encoding="utf-8-sig")

    consistency = d.groupby("solution_id", as_index=False).agg(
        labeled_windows=("window_id", "size"),
        unique_labels=("label", "nunique"),
        positive_windows=("label", "sum"),
    )
    consistency["all_same_label"] = consistency.unique_labels.eq(1)
    consistency.to_csv(SESSION_OUT, index=False, encoding="utf-8-sig")

    report = [
        "# 人工标签独立审计",
        "",
        f"- 用户导出标签总数：{len(labels)}",
        f"- 可用于二分类评估的人工标签：{len(d)}（排除 -1：{int((labels.label == -1).sum())} 条）",
        f"- 人工正例：{int(y.sum())}，负例：{int((y == 0).sum())}",
        f"- 涉及 session：{d.solution_id.nunique()}",
        "",
        audit.to_markdown(index=False),
        "",
        f"- session 中所有窗口同标签：{int(consistency.all_same_label.sum())}/{len(consistency)}（{consistency.all_same_label.mean():.1%}）。",
        "- 这说明部分标注可能是按整道题批量赋值，窗口级指标会受到 session 内相关性影响。",
        "- 因此此前基于 AI 补全标签的指标只能作为探索性结果；本报告的人工标签结果更适合作为当前离线基线。",
        "",
        "## 优化建议",
        "",
        "1. 优先补标边界样本，而不是继续整道题统一标注。",
        "2. 按 solution_id 分组留出验证，报告 session 级误弹率。",
        "3. 线上先做候选提示和冷却，不直接强制弹窗。",
        "4. 记录真实响应后，再用真实行为更新标签和模型。",
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(audit.to_string(index=False))
    print("human_rows", len(d), "sessions", d.solution_id.nunique())
    print("report", REPORT)


if __name__ == "__main__":
    main()
