"""Offline evaluation for the 500-window prototype labels.

The labels are heuristic/AI-reviewed prototype labels, so this is an
exploratory offline study rather than evidence of online causal impact.
Outputs are new artifacts and do not overwrite previous reports or labels.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
LABELS = DATA / "prototype_labels_ai_full.csv"
RULES_OUT = DATA / "prototype_offline_rule_metrics.csv"
OOF_OUT = DATA / "prototype_offline_oof_predictions.csv"
SESSION_OUT = DATA / "prototype_offline_session_metrics.csv"
IMPORTANCE_OUT = DATA / "prototype_offline_feature_importance.csv"
REPORT_OUT = DATA / "prototype_offline_report.md"


def metrics(y: pd.Series, pred: np.ndarray) -> dict[str, float | int]:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "n": int(len(y)), "positive": int(y.sum()), "predicted_positive": int(pred.sum()),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "accuracy": float(accuracy_score(y, pred)),
    }


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    features = ["current_idle_s"]
    for w in (5, 10, 30, 60, 120):
        features += [
            f"keys_{w}s", f"text_keys_{w}s", f"modifier_keys_{w}s",
            f"clipboard_ops_{w}s", f"pause_count_{w}s", f"pause_total_{w}s",
            f"pause_p90_{w}s", f"backspace_{w}s", f"enter_{w}s", f"control_{w}s",
            f"row_changes_{w}s", f"column_changes_{w}s",
        ]
    x = df[features].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    x["progress_ratio"] = (df["event_index"] + 1) / df["total_keys"].clip(lower=1)
    x["progress_ratio"] = x["progress_ratio"].clip(0, 1.5)
    features.append("progress_ratio")
    return x, features


def rule_frame(df: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    progress = (df.event_index + 1) / df.total_keys.clip(lower=1)
    rules = {
        "keys_30s_lt_5": df.keys_30s < 5,
        "keys_60s_lt_20": df.keys_60s < 20,
        "idle_ge_30_and_no_text": (df.current_idle_s >= 30) & (df.text_keys_30s == 0),
        "low_speed_mid_task": (df.current_idle_s.between(10, 45)) & (df.text_keys_30s <= 3) &
                               (df.text_keys_60s > 0) & (progress < 0.72),
        "conservative_stuck_candidate": (df.current_idle_s.between(10, 30)) &
                                         (df.text_keys_30s <= 2) & (df.text_keys_60s <= 15) &
                                         (progress < 0.60) & (df.pause_total_30s >= 8),
        "exclude_clipboard_then_low_speed": (df.current_idle_s.between(10, 45)) &
                                             (df.text_keys_30s <= 3) & (df.text_keys_60s > 0) &
                                             (progress < 0.72) & (df.clipboard_ops_30s == 0),
    }
    rows = []
    for name, pred in rules.items():
        row = {"rule": name}
        row.update(metrics(y, pred.astype(int).to_numpy()))
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    windows = pd.read_csv(WINDOWS)
    labels = pd.read_csv(LABELS)
    df = windows.merge(labels[["window_id", "label"]], on="window_id", validate="one_to_one")
    known = df[df.label.isin([0, 1])].copy().reset_index(drop=True)
    y = known.label.astype(int)

    rules = rule_frame(known, y)
    rules.to_csv(RULES_OUT, index=False, encoding="utf-8-sig")

    x, feature_names = build_features(known)
    groups = known.solution_id.astype(str)
    n_splits = min(5, groups.nunique())
    cv = GroupKFold(n_splits=n_splits)
    models = {
        "logistic_regression": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=3000, class_weight="balanced", random_state=42)
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=3, class_weight="balanced", random_state=42, n_jobs=-1
        ),
    }
    oof = known[["window_id", "solution_id", "label"]].copy()
    all_pred = {}
    model_rows = []
    for name, model in models.items():
        pred = cross_val_predict(model, x, y, cv=cv, groups=groups, method="predict")
        proba = cross_val_predict(model, x, y, cv=cv, groups=groups, method="predict_proba")[:, 1]
        all_pred[f"{name}_pred"] = pred
        all_pred[f"{name}_prob"] = proba
        row = {"model": name}
        row.update(metrics(y, pred))
        model_rows.append(row)
    model_metrics = pd.DataFrame(model_rows)
    for key, value in all_pred.items():
        oof[key] = value

    # Session-level operational view: how many interventions would be shown?
    chosen = all_pred["logistic_regression_pred"]
    oof["recommended_pop"] = chosen
    session = oof.assign(
        user_positive=oof.label.eq(1).astype(int),
        false_positive=((oof.recommended_pop == 1) & (oof.label == 0)).astype(int),
        true_positive=((oof.recommended_pop == 1) & (oof.label == 1)).astype(int),
    ).groupby("solution_id", as_index=False).agg(
        windows=("window_id", "count"),
        positives=("user_positive", "sum"),
        recommended_popups=("recommended_pop", "sum"),
        true_positive=("true_positive", "sum"),
        false_positive=("false_positive", "sum"),
    )
    session["false_pop_rate"] = session.false_positive / session.windows.clip(lower=1)
    session.to_csv(SESSION_OUT, index=False, encoding="utf-8-sig")
    oof.to_csv(OOF_OUT, index=False, encoding="utf-8-sig")

    # Fit RF on all known labels for descriptive feature importance only.
    rf = models["random_forest"].fit(x, y)
    importance = pd.DataFrame({"feature": feature_names, "gini_importance": rf.feature_importances_})
    perm = permutation_importance(rf, x, y, n_repeats=5, random_state=42, scoring="f1", n_jobs=-1)
    importance["permutation_mean"] = perm.importances_mean
    importance.sort_values("permutation_mean", ascending=False).to_csv(IMPORTANCE_OUT, index=False, encoding="utf-8-sig")

    rule_best = rules.sort_values(["f1", "precision"], ascending=False).iloc[0]
    log_row = model_metrics[model_metrics.model.eq("logistic_regression")].iloc[0]
    rf_row = model_metrics[model_metrics.model.eq("random_forest")].iloc[0]
    top_features = importance.head(10)[["feature", "permutation_mean"]].to_dict("records")
    report = [
        "# Prototype 离线规则与模型评估",
        "",
        f"- 窗口总数：{len(df)}",
        f"- 已知标签（排除 -1）：{len(known)}",
        f"- 正样本：{int(y.sum())}，负样本：{int((y == 0).sum())}",
        f"- session 数：{known.solution_id.nunique()}",
        "- 验证方式：按 solution_id 分组的 5 折 GroupKFold，避免同一 session 的窗口同时出现在训练和测试中。",
        "",
        "## 最佳候选规则",
        "",
        f"`{rule_best.rule}`：Precision={rule_best.precision:.1%}，Recall={rule_best.recall:.1%}，F1={rule_best.f1:.1%}，触发={int(rule_best.predicted_positive)} 条。",
        "",
        "## 分组留出模型",
        "",
        f"Logistic Regression：Precision={log_row.precision:.1%}，Recall={log_row.recall:.1%}，F1={log_row.f1:.1%}，预测弹窗={int(log_row.predicted_positive)} 条。",
        f"Random Forest：Precision={rf_row.precision:.1%}，Recall={rf_row.recall:.1%}，F1={rf_row.f1:.1%}，预测弹窗={int(rf_row.predicted_positive)} 条。",
        "",
        "## 运营侧解释",
        "",
        f"Logistic Regression 的 OOF 预测中，每个 session 平均弹窗数为 {session.recommended_popups.mean():.2f}，平均误弹数为 {session.false_positive.mean():.2f}。",
        f"预测弹窗数为 0 的 session：{int((session.recommended_popups == 0).sum())}/{len(session)}。",
        "",
        "## 重要特征（描述性）",
        "",
        "、".join(f"{x['feature']} ({x['permutation_mean']:.4f})" for x in top_features),
        "",
        "## 限制",
        "",
        "这些标签是保守的人工/AI 原型标签，不是线上干预结果；模型指标只能说明对当前标注标准的拟合能力，不能证明弹窗改善了学习效果。下一步若上线，应先做小规模灰度/A-B，并把误弹率和每 session 弹窗次数设为硬约束。",
        "",
        "产物：`prototype_offline_rule_metrics.csv`、`prototype_offline_oof_predictions.csv`、`prototype_offline_session_metrics.csv`、`prototype_offline_feature_importance.csv`。",
    ]
    REPORT_OUT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("known_labels", len(known), "positives", int(y.sum()), "sessions", known.solution_id.nunique())
    print(rules.to_string(index=False))
    print(model_metrics.to_string(index=False))
    print("report", REPORT_OUT)


if __name__ == "__main__":
    main()
