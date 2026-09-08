"""Evaluate the same offline rules against the independently reviewed labels."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
LABELS = DATA / "prototype_labels_human_reviewed.csv"
OUT = DATA / "prototype_reviewed_rule_metrics.csv"
ERRORS = DATA / "prototype_reviewed_error_cases.csv"
REPORT = DATA / "prototype_reviewed_eval.md"

def metric(y, p):
    tn, fp, fn, tp = confusion_matrix(y, p, labels=[0, 1]).ravel()
    return {"n": len(y), "positive": int(y.sum()), "trigger": int(p.sum()),
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "precision": precision_score(y, p, zero_division=0),
            "recall": recall_score(y, p, zero_division=0),
            "f1": f1_score(y, p, zero_division=0)}

def main():
    w = pd.read_csv(WINDOWS)
    l = pd.read_csv(LABELS)
    d = w.merge(l[["window_id", "solution_id", "label"]], on=["window_id", "solution_id"], validate="one_to_one")
    d = d[d.label.isin([0, 1])].copy()
    d.label = d.label.astype(int)
    rules = {
        "keys_30s_lt5": d.keys_30s < 5,
        "idle_ge30_and_keys_30s_lt5": (d.current_idle_s >= 30) & (d.keys_30s < 5),
        "idle_ge30_no_text_30s": (d.current_idle_s >= 30) & (d.text_keys_30s == 0),
        "idle_ge20_and_keys_30s_lt8": (d.current_idle_s >= 20) & (d.keys_30s < 8),
        "idle_ge20_keys30_lt8_no_clipboard": (d.current_idle_s >= 20) & (d.keys_30s < 8) & (d.clipboard_ops_30s == 0),
    }
    rows = []
    for name, p in rules.items():
        x = {"rule": name}; x.update(metric(d.label, p.astype(int))); rows.append(x)
    result = pd.DataFrame(rows)
    result.to_csv(OUT, index=False, encoding="utf-8-sig")
    chosen = rules["idle_ge20_keys30_lt8_no_clipboard"].astype(int)
    err = d.loc[chosen.ne(d.label), ["window_id", "solution_id", "event_index", "window_end_time", "label", "judge", "current_idle_s", "keys_30s", "text_keys_30s", "clipboard_ops_30s", "key_summary"]].copy()
    err.insert(5, "prediction", chosen.loc[err.index].astype(int))
    err.insert(6, "error_type", np.where(err.prediction.eq(1), "false_positive", "false_negative"))
    err.to_csv(ERRORS, index=False, encoding="utf-8-sig")
    m = metric(d.label, chosen)
    report = "# 复核后人工标签规则评估\n\n"
    report += f"- 确定二分类窗口：{len(d)}；正例：{int(d.label.sum())}；负例：{int((d.label == 0).sum())}。\n"
    report += "- 主规则：`idle >= 20 && keys_30s < 8 && clipboard_ops_30s == 0`。\n"
    report += f"- 主规则触发：{m['trigger']}；误报：{m['fp']}；漏报：{m['fn']}。\n"
    report += f"- Precision：{m['precision']:.1%}；Recall：{m['recall']:.1%}；F1：{m['f1']:.1%}。\n\n"
    report += result.to_markdown(index=False) + "\n\n"
    report += "该结果仅用于复核后的敏感性分析；正式结论仍应同时报告原始人工标签结果。\n"
    REPORT.write_text(report, encoding="utf-8")
    print(result.to_string(index=False))
    print(f"errors={len(err)} report={REPORT}")

if __name__ == "__main__":
    main()
