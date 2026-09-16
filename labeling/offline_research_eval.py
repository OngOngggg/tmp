"""Reproducible offline audit for the causal OJ candidate task.

This script intentionally evaluates several historical label versions and
feature sets.  It is an audit of what the current data can support, not a
claim that the labels are direct observations of student need.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
LABEL_FILES = {
    "recall_candidates": DATA / "prototype_labels_recall_candidates.csv",
    "human_reviewed": DATA / "prototype_labels_human_reviewed.csv",
    "human_complete": DATA / "prototype_labels_human_complete.csv",
}


def numeric_features(frame: pd.DataFrame, variant: str) -> list[str]:
    excluded = {
        "solution_id", "problem_id", "event_index", "duration_s", "total_keys",
        "label", "judge", "window_end_time", "window_id", "submitted_code",
    }
    columns = [c for c in frame.columns if c not in excluded and pd.api.types.is_numeric_dtype(frame[c])]
    if variant == "no_idle_pause":
        columns = [c for c in columns if c != "current_idle_s" and not c.startswith("pause_")]
    elif variant == "minimal":
        columns = [c for c in ("current_idle_s", "keys_30s", "clipboard_ops_30s") if c in frame]
    return columns


def rule_prediction(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["current_idle_s"].fillna(-1).ge(20)
        & frame["keys_30s"].fillna(999).lt(8)
        & frame["clipboard_ops_30s"].fillna(999).eq(0)
    )


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if mask.any():
            total += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(total)


def score_binary(y: np.ndarray, pred: np.ndarray, prob: np.ndarray | None = None) -> dict:
    out = {
        "n": int(len(y)),
        "positive": int(y.sum()),
        "trigger": int(pred.sum()),
        "tp": int(((pred == 1) & (y == 1)).sum()),
        "fp": int(((pred == 1) & (y == 0)).sum()),
        "fn": int(((pred == 0) & (y == 1)).sum()),
        "precision": float(((pred == 1) & (y == 1)).sum() / max(1, (pred == 1).sum())),
        "recall": float(((pred == 1) & (y == 1)).sum() / max(1, (y == 1).sum())),
    }
    out["f1"] = float(2 * out["precision"] * out["recall"] / max(1e-12, out["precision"] + out["recall"]))
    if prob is not None and len(np.unique(y)) > 1:
        out.update({
            "roc_auc": auc_rank(y, prob),
            "pr_auc": average_precision(y, prob),
            "brier": float(np.mean((prob - y) ** 2)),
            "ece": ece(y, prob),
        })
    return out


def auc_rank(y: np.ndarray, p: np.ndarray) -> float:
    pos = p[y == 1]
    neg = p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    # Mid-rank ties are sufficient for this small audit dataset.
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


def average_precision(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(-p, kind="mergesort")
    ys = y[order]
    hits = np.cumsum(ys)
    rank = np.arange(1, len(y) + 1)
    return float(np.sum((hits / rank) * ys) / max(1, ys.sum()))


def fit_logistic(x: np.ndarray, y: np.ndarray, steps: int = 1200, lr: float = 0.08) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    med = np.nanmedian(x, axis=0)
    x = np.where(np.isnan(x), med, x)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    z = (x - mean) / scale
    z = np.c_[np.ones(len(z)), z]
    w = np.where(y == 1, len(y) / max(1, 2 * y.sum()), len(y) / max(1, 2 * (len(y) - y.sum())))
    beta = np.zeros(z.shape[1])
    for _ in range(steps):
        p = 1 / (1 + np.exp(-np.clip(z @ beta, -30, 30)))
        grad = (z.T @ ((p - y) * w)) / len(y)
        grad[1:] += 0.01 * beta[1:]
        beta -= lr * grad
    return beta, med, mean, scale


def predict_logistic(x: np.ndarray, fitted: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    beta, med, mean, scale = fitted
    x = np.where(np.isnan(x), med, x)
    z = (x - mean) / scale
    z = np.c_[np.ones(len(z)), z]
    return 1 / (1 + np.exp(-np.clip(z @ beta, -30, 30)))


def candidate_operational_audit(path: Path, out_dir: Path) -> dict:
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    frame["solution_id"] = pd.to_numeric(frame["solution_id"], errors="coerce")
    parsed = pd.to_datetime(frame["trigger_time"], errors="coerce")
    summary = []
    for cooldown in (0, 300, 600, 900):
        kept = []
        for _, group in frame.sort_values("trigger_time").groupby("solution_id"):
            times = pd.to_datetime(group["trigger_time"], errors="coerce").astype("int64")
            # pandas 2/3 may store datetime64 at seconds or nanoseconds.
            if times.abs().median() > 1e14:
                times = times / 1e6  # datetime64[us]
            elif times.abs().median() > 1e12:
                times = times / 1e9  # datetime64[ns]
            last = -np.inf
            for idx, timestamp in zip(group.index, times):
                if timestamp - last >= cooldown:
                    kept.append(idx)
                    last = timestamp
        selected = frame.loc[kept] if kept else frame.iloc[0:0]
        summary.append({
            "cooldown_s": cooldown,
            "candidates": int(len(selected)),
            "sessions": int(selected["solution_id"].nunique()),
            "mean_per_session": float(len(selected) / max(1, selected["solution_id"].nunique())),
            "max_per_session": int(selected.groupby("solution_id").size().max()) if len(selected) else 0,
        })
    operational = pd.DataFrame(summary)
    operational.to_csv(out_dir / "candidate_cooldown.csv", index=False, encoding="utf-8-sig")
    event_stats = {
        "rows": int(len(frame)),
        "invalid_trigger_time": int(parsed.isna().sum()),
        "valid_trigger_time_rate": float(parsed.notna().mean()),
        "sessions": int(frame["solution_id"].nunique()),
        "no_future_event_rate": float(frame["outcome_continued_input_120s"].eq(0).mean()),
        "recovered_30s_rate": float(frame["outcome_text_keys_30s"].fillna(0).ge(3).mean()),
        "recovered_60s_rate": float(frame["outcome_text_keys_60s"].fillna(0).ge(3).mean()),
        "recovered_120s_rate": float(frame["outcome_text_keys_120s"].fillna(0).ge(3).mean()),
    }
    (out_dir / "candidate_outcome_audit.json").write_text(json.dumps(event_stats, indent=2), encoding="utf-8")
    return {"cooldown": summary, "outcomes": event_stats}


def grouped_oof(frame: pd.DataFrame, features: list[str], y: np.ndarray, model_name: str) -> np.ndarray:
    groups = frame["solution_id"].to_numpy()
    oof = np.full(len(frame), np.nan, dtype=float)
    unique = np.unique(groups)
    folds = [unique[i::5] for i in range(5)]
    x_all = frame[features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if SKLEARN_AVAILABLE:
        splitter = GroupKFold(n_splits=min(5, len(unique)))
        fold_indices = splitter.split(frame, y, groups)
    else:
        if model_name != "logistic":
            raise RuntimeError("random_forest requires scikit-learn; unavailable in bundled runtime")
        fold_indices = ((np.flatnonzero(~np.isin(groups, test_groups)), np.flatnonzero(np.isin(groups, test_groups))) for test_groups in folds)
    for train_idx, test_idx in fold_indices:
        if SKLEARN_AVAILABLE:
            if model_name == "logistic":
                model = make_pipeline(
                    SimpleImputer(strategy="median"), StandardScaler(),
                    LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000, random_state=42),
                )
            elif model_name == "random_forest":
                model = make_pipeline(
                    SimpleImputer(strategy="median"),
                    RandomForestClassifier(
                        n_estimators=500, max_depth=4, min_samples_leaf=5,
                        max_features="sqrt", class_weight="balanced_subsample",
                        # Single-process mode is deterministic and works in
                        # restricted Windows environments where joblib cannot
                        # create multiprocessing pipes.
                        random_state=42, n_jobs=1,
                    ),
                )
            else:
                raise ValueError(f"unknown model: {model_name}")
            model.fit(frame.iloc[train_idx][features], y[train_idx])
            oof[test_idx] = model.predict_proba(frame.iloc[test_idx][features])[:, 1]
        else:
            fitted = fit_logistic(x_all[train_idx], y[train_idx])
            oof[test_idx] = predict_logistic(x_all[test_idx], fitted)
    return oof


def bootstrap_session_metrics(frame: pd.DataFrame, pred: np.ndarray, y: np.ndarray, seed: int = 42, reps: int = 1000) -> dict:
    rng = np.random.default_rng(seed)
    groups = frame["solution_id"].to_numpy()
    unique = np.unique(groups)
    values = []
    for _ in range(reps):
        sample = rng.choice(unique, size=len(unique), replace=True)
        mask = np.isin(groups, sample)
        values.append(score_binary(y[mask], pred[mask])["f1"])
    lo, hi = np.percentile(values, [2.5, 97.5])
    return {"f1_mean": float(np.mean(values)), "f1_ci_low": float(lo), "f1_ci_high": float(hi)}


def label_audit(frame: pd.DataFrame, y: pd.Series) -> dict:
    grouped = pd.DataFrame({"solution_id": frame.solution_id, "label": y}).groupby("solution_id")["label"]
    sizes = grouped.size()
    homogeneous = grouped.nunique().eq(1)
    return {
        "sessions": int(grouped.ngroups),
        "homogeneous_sessions": int(homogeneous.sum()),
        "homogeneous_session_rate": float(homogeneous.mean()),
        "median_windows_per_session": float(sizes.median()),
        "max_windows_per_session": int(sizes.max()),
    }


def selective_table(y: np.ndarray, prob: np.ndarray) -> list[dict]:
    rows = []
    for confidence in (0.50, 0.60, 0.70, 0.80, 0.90):
        keep = (prob >= confidence) | (prob <= 1 - confidence)
        if keep.any():
            pred = (prob[keep] >= 0.5).astype(int)
            rows.append({
                "confidence": confidence,
                "coverage": float(keep.mean()),
                "abstain_rate": float(1 - keep.mean()),
                "retained_accuracy": float((pred == y[keep]).mean()),
                "positive_recall_all": float(((prob >= confidence) & (y == 1)).sum() / max(1, (y == 1).sum())),
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DATA / "offline_research")
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    windows = pd.read_csv(WINDOWS)
    candidate_audit = candidate_operational_audit(ROOT.parent / "data" / "clean_oj" / "full_causal_candidates.csv", args.out_dir)
    all_results: list[dict] = []
    all_selective: list[dict] = []
    audits: dict = {}
    for label_name, label_path in LABEL_FILES.items():
        labels = pd.read_csv(label_path, usecols=["window_id", "label"])
        frame = windows.merge(labels, on="window_id", how="inner", validate="one_to_one")
        frame = frame[frame.label.isin([0, 1])].copy()
        y = frame.label.astype(int).to_numpy()
        audits[label_name] = label_audit(frame, frame.label.astype(int))
        majority = np.zeros(len(frame), dtype=int)
        majority_score = score_binary(y, majority, np.full(len(frame), y.mean(), dtype=float))
        majority_score.update({"labels": label_name, "features": "none", "model": "majority"})
        majority_score.update(bootstrap_session_metrics(frame, majority, y, reps=args.bootstrap))
        all_results.append(majority_score)
        for variant in ("full", "no_idle_pause", "minimal"):
            features = numeric_features(frame, variant)
            rule = rule_prediction(frame).to_numpy().astype(int)
            rule_score = score_binary(y, rule)
            rule_score.update({"labels": label_name, "features": variant, "model": "rule"})
            rule_score.update(bootstrap_session_metrics(frame, rule, y, reps=args.bootstrap))
            all_results.append(rule_score)
            model_names = ("logistic", "random_forest") if SKLEARN_AVAILABLE else ("logistic",)
            for model_name in model_names:
                prob = grouped_oof(frame, features, y, model_name)
                pred = (prob >= 0.5).astype(int)
                score = score_binary(y, pred, prob)
                score.update({"labels": label_name, "features": variant, "model": model_name})
                score.update(bootstrap_session_metrics(frame, pred, y, reps=args.bootstrap))
                all_results.append(score)
                if label_name == "recall_candidates" and variant == "no_idle_pause" and model_name == "logistic":
                    for row in selective_table(y, prob):
                        row.update({"labels": label_name, "features": variant, "model": model_name})
                        all_selective.append(row)

    result_frame = pd.DataFrame(all_results)
    result_frame.to_csv(args.out_dir / "model_comparison.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_selective).to_csv(args.out_dir / "selective_prediction.csv", index=False, encoding="utf-8-sig")
    (args.out_dir / "label_audit.json").write_text(json.dumps(audits, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Offline research audit",
        "",
        "本报告统一重算三套标签版本，避免旧报告与最终标签口径混用。所有模型使用按 solution_id 分组的 5 折 OOF；模型特征只取窗口前可见的数值行为特征。",
        "",
        "## 标签与 session 审计",
        "",
        "| label version | sessions | homogeneous sessions | homogeneous rate | median windows/session |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, audit in audits.items():
        lines.append(f"| {name} | {audit['sessions']} | {audit['homogeneous_sessions']} | {audit['homogeneous_session_rate']:.1%} | {audit['median_windows_per_session']:.1f} |")
    lines += [
        "",
        "## 解释",
        "",
        "- `full` 包含当前多尺度行为特征；`no_idle_pause` 去除 `current_idle_s` 和所有 `pause_*`，用于检查标签与停顿信号的循环；`minimal` 只保留当前基线所需的三个特征。",
        "- `rule` 是 `idle>=20 && keys_30s<8 && clipboard_ops_30s==0`，只作为可解释基线。",
        "- `f1_ci_low/high` 是按 session 重采样的 95% 区间；它反映 session 聚类不确定性，不是独立窗口置信区间。",
        "- 模型分数表示与当前人工操作性标签的一致程度，不表示识别了学生真实心理状态，也不表示提示有效。",
        "",
        "## 主要结果",
        "",
        "完整数值见 `model_comparison.csv`。重点查看：同一 label version 下 `full` 与 `no_idle_pause` 的差异，以及三套 label version 间结果是否稳定。若去除 idle/pause 后性能大幅下降，说明当前标签强依赖停顿定义，不能把高分解释成独立状态识别。",
        "",
        "## 选择性预测",
        "",
        "`selective_prediction.csv` 给出逻辑回归在不同置信度下的覆盖率、拒答率和正例召回。在线系统应允许低置信度样本 abstain，而不是强制二分类。",
        "",
        "## 使用边界",
        "",
        "1. 不能用这些离线结果声称主动提示改善 AC、学习成绩或挫败感。",
        "2. `human_complete`、`human_reviewed` 和 `recall_candidates` 是不同操作性标签，不能挑选分数最高的一套作为唯一真值。",
        "3. 候选外漏报仍未被人工充分标注；下一步应按 session 抽样标注正常输入、等待判题、失焦/离开和候选未命中窗口。",
    ]
    if candidate_audit:
        o = candidate_audit["outcomes"]
        lines += [
            "",
            "## 全量事件驱动候选审计",
            "",
            f"全量候选 {o['rows']:,} 条，覆盖 {o['sessions']:,} 个 session；其中 {o['invalid_trigger_time']:,} 条的 `trigger_time` 无法解析，冷却统计只使用可解析时间。按‘触发后 120 秒内至少 3 个非修饰/非导航事件’定义的自然活动恢复率为 30 秒 {o['recovered_30s_rate']:.1%}、60 秒 {o['recovered_60s_rate']:.1%}、120 秒 {o['recovered_120s_rate']:.1%}。其中 {o['no_future_event_rate']:.1%} 的候选在 120 秒内无后续事件，属于删失/离开混合情形，不能简单当作失败。",
            "",
            "冷却结果见 `candidate_cooldown.csv`。这些结果只描述真实候选负载和自然后果，不代表展示提示后的因果效果。",
        ]
    (args.out_dir / "offline_research_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"windows={len(windows):,}")
    print(f"results={args.out_dir / 'model_comparison.csv'}")
    print(f"report={args.out_dir / 'offline_research_report.md'}")


if __name__ == "__main__":
    main()
