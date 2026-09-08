"""Evaluate rules on the complete user-labeled prototype dataset.

This script uses the merged, value-preserving human labels and writes new
reports. It does not modify labels or overwrite earlier evaluation artifacts.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
LABELS = DATA / "prototype_labels_human_complete.csv"
OUT = DATA / "prototype_complete_human_rule_metrics.csv"
SESSION_OUT = DATA / "prototype_complete_human_session_metrics.csv"
ERROR_OUT = DATA / "prototype_complete_human_error_cases.csv"
REPORT = DATA / "prototype_complete_human_eval.md"


def metrics(y: pd.Series, pred: pd.Series) -> dict[str, float | int]:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "n": len(y), "positive": int(y.sum()), "trigger": int(pred.sum()),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
    }


def main() -> None:
    windows = pd.read_csv(WINDOWS)
    labels = pd.read_csv(LABELS)
    d = windows.merge(labels[["window_id", "solution_id", "label", "source_batch"]],
                      on=["window_id", "solution_id"], validate="one_to_one")
    d = d[d.label.isin([0, 1])].copy()
    d["label"] = d.label.astype(int)

    rule_defs = {
        "keys_30s_lt5": d.keys_30s < 5,
        "idle_ge30_and_keys_30s_lt5": (d.current_idle_s >= 30) & (d.keys_30s < 5),
        "idle_ge30_no_text_30s": (d.current_idle_s >= 30) & (d.text_keys_30s == 0),
        "idle_ge20_and_keys_30s_lt8": (d.current_idle_s >= 20) & (d.keys_30s < 8),
        "idle_ge20_keys30_lt8_no_clipboard": (
            (d.current_idle_s >= 20) & (d.keys_30s < 8) & (d.clipboard_ops_30s == 0)
        ),
    }
    rows = []
    for name, pred in rule_defs.items():
        row = {"rule": name}
        row.update(metrics(d.label, pred.astype(int)))
        rows.append(row)
    result = pd.DataFrame(rows)
    result.to_csv(OUT, index=False, encoding="utf-8-sig")

    chosen = rule_defs["idle_ge20_keys30_lt8_no_clipboard"].astype(int)
    session = d.assign(
        predicted=chosen,
        tp=((chosen == 1) & (d.label == 1)).astype(int),
        fp=((chosen == 1) & (d.label == 0)).astype(int),
        fn=((chosen == 0) & (d.label == 1)).astype(int),
    ).groupby("solution_id", as_index=False).agg(
        windows=("window_id", "size"),
        positives=("label", "sum"),
        triggers=("predicted", "sum"),
        tp=("tp", "sum"), fp=("fp", "sum"), fn=("fn", "sum"),
    )
    session["false_pop_rate"] = session.fp / session.windows.clip(lower=1)
    session["has_positive"] = session.positives > 0
    session.to_csv(SESSION_OUT, index=False, encoding="utf-8-sig")

    errors = d.loc[chosen.ne(d.label), [
        "window_id", "solution_id", "event_index", "window_end_time", "label",
        "source_batch", "current_idle_s", "keys_30s", "text_keys_30s",
        "clipboard_ops_30s", "backspace_30s", "enter_30s", "control_30s",
        "keys_60s", "text_keys_60s", "judge", "key_summary",
    ]].copy()
    errors.insert(5, "prediction", chosen.loc[errors.index].astype(int))
    errors.insert(6, "error_type", np.where(errors.prediction.eq(1), "false_positive", "false_negative"))
    errors.to_csv(ERROR_OUT, index=False, encoding="utf-8-sig")

    consistency = d.groupby("solution_id").label.nunique()
    mixed_ids = consistency[consistency > 1].index
    mixed = d[d.solution_id.isin(mixed_ids)]
    mixed_pred = rule_defs["idle_ge20_keys30_lt8_no_clipboard"].loc[mixed.index]
    mixed_m = metrics(mixed.label, mixed_pred.astype(int))

    by_batch = []
    for batch, part in d.groupby("source_batch"):
        pred = rule_defs["idle_ge20_keys30_lt8_no_clipboard"].loc[part.index]
        row = {"source_batch": batch}
        row.update(metrics(part.label, pred.astype(int)))
        by_batch.append(row)
    batch_df = pd.DataFrame(by_batch)

    report = [
        "# 全量人工标签规则评估",
        "",
        "## 数据范围",
        "",
        f"- 全部窗口：{len(windows)}。",
        f"- 确定二分类标签：{len(d)}。",
        f"- 正例：{int(d.label.sum())}；负例：{int((d.label == 0).sum())}。",
        f"- session：{d.solution_id.nunique()}。",
        f"- 整题同标签session：{int(consistency.eq(1).sum())}/{len(consistency)}。",
        "- 标签值来自两个用户导出文件，合并时未为改善指标而调整。",
        "",
        "## 规则结果",
        "",
        result.to_markdown(index=False),
        "",
        "## 主规则的分批结果",
        "",
        "主规则：`idle >= 20 && keys_30s < 8 && clipboard_ops_30s == 0`。",
        "",
        batch_df.to_markdown(index=False),
        "",
        "## 混合标签session",
        "",
        f"仅保留session内同时出现0和1的窗口：n={mixed_m['n']}，"
        f"Precision={mixed_m['precision']:.1%}，Recall={mixed_m['recall']:.1%}，F1={mixed_m['f1']:.1%}。",
        "",
        "## 主规则错误",
        "",
        f"- 误报：{int((errors.error_type == 'false_positive').sum())}条。",
        f"- 漏报：{int((errors.error_type == 'false_negative').sum())}条。",
        f"- 明细：`{ERROR_OUT.name}`。",
        "",
        "## 解释",
        "",
        "完整数据的指标低于早期235条子集并不表示数据被改坏，而是后续标注覆盖了更多边界状态，且标签分布发生变化。正式论文应报告全量结果，并将早期子集结果作为阶段性分析。",
        "",
        "这些指标表示规则与人工判断的一致性，不表示主动提示已经改善学习成绩或AC率。",
        "",
        f"产物：`{LABELS.name}`、`{OUT.name}`、`{SESSION_OUT.name}`、`{ERROR_OUT.name}`。",
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(result.to_string(index=False))
    print("mixed", mixed_m)
    print("report", REPORT)


if __name__ == "__main__":
    main()
