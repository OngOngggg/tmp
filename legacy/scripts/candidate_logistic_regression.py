"""Group-aware logistic regression for the 69/297/134 Candidate labels."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
LABELS = DATA / "prototype_labels_recall_candidates.csv"
METRICS_OUT = DATA / "candidate_logistic_regression.csv"
COEF_OUT = DATA / "candidate_logistic_regression_coefficients.csv"
REPORT_OUT = DATA / "candidate_logistic_regression.md"


def feature_names(df: pd.DataFrame) -> list[str]:
    names = ["current_idle_s"]
    for width in (5, 10, 30, 60, 120):
        names += [
            f"keys_{width}s", f"text_keys_{width}s", f"modifier_keys_{width}s",
            f"clipboard_ops_{width}s", f"pause_count_{width}s",
            f"pause_total_{width}s", f"pause_p90_{width}s",
            f"backspace_{width}s", f"enter_{width}s", f"control_{width}s",
            f"row_changes_{width}s", f"column_changes_{width}s",
        ]
    return [name for name in names if name in df.columns]


def evaluate(y: pd.Series, pred: np.ndarray, proba: np.ndarray) -> dict:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "n": len(y), "positive": int(y.sum()), "predicted_positive": int(pred.sum()),
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "roc_auc": roc_auc_score(y, proba),
        "pr_auc": average_precision_score(y, proba),
    }


def main() -> None:
    windows = pd.read_csv(WINDOWS)
    labels = pd.read_csv(LABELS)
    df = windows.merge(labels[["window_id", "solution_id", "label"]],
                       on=["window_id", "solution_id"], validate="one_to_one")
    known = df[df.label.isin([0, 1])].copy().reset_index(drop=True)
    known["label"] = known.label.astype(int)
    y = known.label
    features = feature_names(known)
    x = known[features].apply(pd.to_numeric, errors="coerce")
    groups = known.solution_id.astype(str)

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(
            C=0.5, class_weight="balanced", max_iter=5000,
            solver="liblinear", random_state=42,
        )),
    ])
    cv = GroupKFold(n_splits=5)
    proba = cross_val_predict(model, x, y, cv=cv, groups=groups,
                              method="predict_proba")[:, 1]

    rows = []
    for threshold in (0.30, 0.40, 0.50, 0.60):
        row = {"model": "logistic_regression", "threshold": threshold}
        row.update(evaluate(y, (proba >= threshold).astype(int), proba))
        rows.append(row)
    result = pd.DataFrame(rows)
    result.to_csv(METRICS_OUT, index=False, encoding="utf-8-sig")

    model.fit(x, y)
    coef = model.named_steps["classifier"].coef_[0]
    coef_df = pd.DataFrame({
        "feature": features, "coefficient": coef, "abs_coefficient": np.abs(coef)
    }).sort_values("abs_coefficient", ascending=False)
    coef_df.to_csv(COEF_OUT, index=False, encoding="utf-8-sig")

    shown = result.copy()
    for col in ("precision", "recall", "f1", "roc_auc", "pr_auc"):
        shown[col] = shown[col].map(lambda value: f"{value:.1%}")
    report = [
        "# Candidate 标签口径下的逻辑回归", "",
        "- 统一标签：`prototype_labels_recall_candidates.csv`（1=69、0=297、-1=134）。",
        "- 监督训练和评价排除 -1，共 366 条；预测目标是是否进入 Candidate，不是是否立即弹窗。",
        f"- 输入 {len(features)} 个严格因果数值特征：current_idle_s 及 5/10/30/60/120 秒行为特征。",
        "- 排除 event_index、total_keys、duration_s、submitted_code、最终 judge 和未来事件。",
        "- 使用中位数填补、标准化、class_weight=balanced 的 L2 逻辑回归。",
        "- 使用按 solution_id 分组的 5 折 GroupKFold，避免同一 session 泄漏。", "",
        "## 分组交叉验证结果", "", shown.to_markdown(index=False), "",
        "0.30/0.40 阈值用于观察高召回候选方案；0.50 是默认分类阈值。阈值必须在独立验证集或嵌套交叉验证中确定，不能在同一批结果上挑最高分后宣称泛化性能。", "",
        "完整数据拟合后的系数仅作特征方向解释，不作为独立测试证据。",
    ]
    REPORT_OUT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(result.to_string(index=False))
    print("written", METRICS_OUT, COEF_OUT, REPORT_OUT)


if __name__ == "__main__":
    main()
