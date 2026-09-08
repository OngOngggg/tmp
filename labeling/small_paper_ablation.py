"""Human-label-only ablation and error analysis for the small paper.

This script deliberately excludes AI-completed labels.  It writes new
artifacts and does not overwrite the original labels or earlier reports.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
ABLATION_OUT = DATA / "small_paper_ablation.csv"
ERROR_OUT = DATA / "small_paper_error_cases.csv"
REPORT_OUT = DATA / "small_paper_offline_summary.md"


def score(y: pd.Series, pred: pd.Series) -> dict[str, float | int]:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "n": int(len(y)),
        "positive": int(y.sum()),
        "trigger": int(pred.sum()),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path(r"C:\Users\10950\Downloads\prototype_labels.csv"),
    )
    args = parser.parse_args()

    windows = pd.read_csv(WINDOWS)
    labels = pd.read_csv(args.labels)
    d = windows.merge(
        labels[["window_id", "solution_id", "label"]],
        on=["window_id", "solution_id"],
        validate="one_to_one",
    )
    d = d[d.label.isin([0, 1])].copy()
    d["label"] = d.label.astype(int)
    y = d.label

    rules = {
        "idle_ge30": d.current_idle_s >= 30,
        "keys30_lt5": d.keys_30s < 5,
        "idle_ge30_and_keys30_lt5": (d.current_idle_s >= 30) & (d.keys_30s < 5),
        "plus_no_clipboard": (
            (d.current_idle_s >= 30)
            & (d.keys_30s < 5)
            & (d.clipboard_ops_30s == 0)
        ),
        "idle_ge20_and_keys30_lt8_no_clipboard": (
            (d.current_idle_s >= 20)
            & (d.keys_30s < 8)
            & (d.clipboard_ops_30s == 0)
        ),
    }

    rows = []
    for name, pred in rules.items():
        row = {"rule": name}
        row.update(score(y, pred.astype(int)))
        rows.append(row)
    result = pd.DataFrame(rows)
    result.to_csv(ABLATION_OUT, index=False, encoding="utf-8-sig")

    chosen = rules["plus_no_clipboard"].astype(int)
    errors = d.loc[chosen.ne(y), [
        "window_id", "solution_id", "event_index", "window_end_time", "label",
        "current_idle_s", "keys_30s", "text_keys_30s", "clipboard_ops_30s",
        "backspace_30s", "enter_30s", "control_30s", "keys_60s",
        "text_keys_60s", "judge", "key_summary",
    ]].copy()
    errors.insert(5, "prediction", chosen.loc[errors.index].astype(int))
    errors.insert(6, "error_type", errors.apply(
        lambda r: "false_positive" if r.prediction == 1 else "false_negative", axis=1
    ))
    errors.to_csv(ERROR_OUT, index=False, encoding="utf-8-sig")

    same = d.groupby("solution_id").label.nunique().eq(1)
    mixed_ids = same[~same].index
    mixed = d[d.solution_id.isin(mixed_ids)]
    mixed_pred = chosen.loc[mixed.index]
    mixed_metrics = score(mixed.label, mixed_pred)

    report = [
        "# 小论文离线消融与错误分析",
        "",
        f"- 用户标注：{len(labels)}条；确定二分类标签：{len(d)}条。",
        f"- 正例：{int(y.sum())}；负例：{int((y == 0).sum())}；session：{d.solution_id.nunique()}。",
        f"- 全部窗口同标签的session：{int(same.sum())}/{len(same)}。",
        "- 本报告只使用用户标签，不使用AI补全标签。",
        "",
        "## 消融结果",
        "",
        result.to_markdown(index=False),
        "",
        "## 主规则错误",
        "",
        f"- 误报：{int((errors.error_type == 'false_positive').sum())}条。",
        f"- 漏报：{int((errors.error_type == 'false_negative').sum())}条。",
        f"- 错误样本已保存到 `{ERROR_OUT.name}`，用于论文中的案例分析。",
        "",
        "## 混合标签session审计",
        "",
        f"- n={mixed_metrics['n']}，Precision={mixed_metrics['precision']:.1%}，"
        f"Recall={mixed_metrics['recall']:.1%}，F1={mixed_metrics['f1']:.1%}。",
        "",
        "## 解释边界",
        "",
        "这些指标衡量规则和单个标注者判断的一致性，不衡量提示对AC率、学习成绩或恢复输入的因果效果。",
    ]
    REPORT_OUT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(result.to_string(index=False))
    print("errors", len(errors), "report", REPORT_OUT)


if __name__ == "__main__":
    main()
