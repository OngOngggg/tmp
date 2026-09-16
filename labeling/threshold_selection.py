"""Data-driven selection of intervention parameters.

This script treats thresholds as policy parameters, not as ground-truth
definitions of a student's mental state.  Labels with ``-1`` are unknown and
are excluded from scoring.  Selection happens on a session-grouped development
split; the held-out split is used only once for reporting.

The first experiment varies the idle trigger while keeping the existing
30-second activity context (keys and clipboard) fixed.  This makes 27/30/33s
comparisons exact on the current feature table.  A separate scan varies the
keys threshold.  The script also reports empirical quantiles and candidate
rates so an operational budget can be stated explicitly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "labeling" / "data"
WINDOWS = DATA / "prototype_windows.csv"
LABEL_FILES = {
    "recall_candidates": DATA / "prototype_labels_recall_candidates.csv",
    "human_reviewed": DATA / "prototype_labels_human_reviewed.csv",
    "human_complete": DATA / "prototype_labels_human_complete.csv",
}

IDLE_GRID = (5, 10, 15, 20, 25, 27, 30, 33, 35, 45, 60, 90, 120)
KEY_GRID = (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 30)
CONTEXT_GRID = (10, 30, 60, 120)
COOLDOWN_GRID = (0, 60, 300, 600, 900, 1200)


def score(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    tp = int(((y == 1) & (pred == 1)).sum())
    fp = int(((y == 0) & (pred == 1)).sum())
    fn = int(((y == 1) & (pred == 0)).sum())
    tn = int(((y == 0) & (pred == 0)).sum())
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "n": int(len(y)),
        "positive_rate": float(y.mean()) if len(y) else 0.0,
        "predicted_rate": float(pred.mean()) if len(pred) else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_prompts": fp,
        "false_prompt_rate": fp / max(1, (y == 0).sum()),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def group_bootstrap_f1(frame: pd.DataFrame, y: np.ndarray, pred: np.ndarray, mask: pd.Series,
                       seed: int = 123, reps: int = 500) -> tuple[float, float]:
    """Session bootstrap interval; windows within a solution are not iid."""
    selected = mask.to_numpy()
    groups = frame.loc[mask, "solution_id"].to_numpy()
    unique = np.unique(groups)
    if len(unique) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    values = []
    local_y, local_pred = y[selected], pred[selected]
    for _ in range(reps):
        sampled = rng.choice(unique, size=len(unique), replace=True)
        keep = np.isin(groups, sampled)
        values.append(score(local_y[keep], local_pred[keep])["f1"])
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def split_by_group(frame: pd.DataFrame, seed: int = 42, test_fraction: float = 0.25) -> tuple[pd.Series, pd.Series]:
    groups = pd.Series(frame["solution_id"].drop_duplicates().to_numpy())
    rng = np.random.default_rng(seed)
    shuffled = groups.to_numpy().copy()
    rng.shuffle(shuffled)
    n_test = max(1, int(round(len(shuffled) * test_fraction)))
    test_groups = set(shuffled[:n_test])
    test = frame["solution_id"].isin(test_groups)
    return ~test, test


def prediction(frame: pd.DataFrame, idle_s: float, keys_limit: int, context_s: int = 30,
               clipboard_free: bool = True) -> np.ndarray:
    pred = frame["current_idle_s"].to_numpy(dtype=float) >= idle_s
    pred &= frame[f"keys_{context_s}s"].to_numpy(dtype=float) < keys_limit
    if clipboard_free:
        pred &= frame[f"clipboard_ops_{context_s}s"].to_numpy(dtype=float) == 0
    return pred.astype(int)


def choose_utility(rows: pd.DataFrame, max_prompt_rate: float | None = None) -> pd.Series:
    """Choose a parameter set without silently optimizing only F1.

    The default utility weights recall and false-prompt burden equally after
    normalizing both to rates.  ``max_prompt_rate`` can impose an operational
    budget; among feasible rows, highest F1 is used as a secondary criterion.
    """
    feasible = rows
    if max_prompt_rate is not None:
        budgeted = rows[rows["predicted_rate"] <= max_prompt_rate]
        if len(budgeted):
            feasible = budgeted
    utility = feasible["recall"] - feasible["false_prompt_rate"]
    # Break utility ties by F1, then by lower prompt rate.  This prevents an
    # empty policy from winning merely because recall and false-prompt rate
    # are both zero.
    ranked = feasible.assign(_utility=utility, _prompt=feasible["predicted_rate"])
    best_idx = ranked.sort_values(["_utility", "f1", "_prompt"], ascending=[False, False, True]).index[0]
    best = feasible.loc[best_idx].copy()
    best["utility_recall_minus_fp"] = float(utility.loc[best_idx])
    best["selection_feasible_count"] = int(len(feasible))
    return best


def threshold_sweep(frame: pd.DataFrame, label_name: str, dev: pd.Series, test: pd.Series, budget: float | None) -> tuple[pd.DataFrame, dict]:
    rows: list[dict] = []
    y = frame["label"].to_numpy(dtype=int)
    for idle in IDLE_GRID:
        pred = prediction(frame, idle, 8)
        for split_name, mask in (("dev", dev), ("test", test)):
            metrics = score(y[mask.to_numpy()], pred[mask.to_numpy()])
            if split_name == "test":
                metrics["f1_ci_low"], metrics["f1_ci_high"] = group_bootstrap_f1(frame, y, pred, mask)
            metrics.update({"label": label_name, "parameter": "idle_s", "idle_s": idle, "keys_limit": 8, "split": split_name})
            rows.append(metrics)
    for keys in KEY_GRID:
        pred = prediction(frame, 30, keys, context_s=30)
        for split_name, mask in (("dev", dev), ("test", test)):
            metrics = score(y[mask.to_numpy()], pred[mask.to_numpy()])
            if split_name == "test":
                metrics["f1_ci_low"], metrics["f1_ci_high"] = group_bootstrap_f1(frame, y, pred, mask)
            metrics.update({"label": label_name, "parameter": "keys_30s_limit", "idle_s": 30, "keys_limit": keys, "split": split_name})
            rows.append(metrics)
    for context_s in CONTEXT_GRID:
        pred = prediction(frame, 30, 8, context_s=context_s)
        for split_name, mask in (("dev", dev), ("test", test)):
            metrics = score(y[mask.to_numpy()], pred[mask.to_numpy()])
            if split_name == "test":
                metrics["f1_ci_low"], metrics["f1_ci_high"] = group_bootstrap_f1(frame, y, pred, mask)
            metrics.update({"label": label_name, "parameter": "context_s", "idle_s": 30, "keys_limit": 8, "context_s": context_s, "split": split_name})
            rows.append(metrics)
    sweep = pd.DataFrame(rows)
    dev_idle = sweep[(sweep.split == "dev") & (sweep.parameter == "idle_s")].copy()
    chosen_idle = choose_utility(dev_idle, budget)
    dev_keys = sweep[(sweep.split == "dev") & (sweep.parameter == "keys_30s_limit")].copy()
    chosen_keys = choose_utility(dev_keys, budget)
    dev_context = sweep[(sweep.split == "dev") & (sweep.parameter == "context_s")].copy()
    chosen_context = choose_utility(dev_context, budget)
    def heldout_for(chosen: pd.Series, parameter: str) -> dict:
        idle = float(chosen["idle_s"])
        keys = int(chosen["keys_limit"])
        pred = prediction(frame, idle, keys, context_s=30)
        return score(y[test.to_numpy()], pred[test.to_numpy()])

    selected = {
        "label": label_name,
        "idle_choice": {k: (v.item() if hasattr(v, "item") else v) for k, v in chosen_idle.to_dict().items()},
        "keys_choice": {k: (v.item() if hasattr(v, "item") else v) for k, v in chosen_keys.to_dict().items()},
    }
    selected["idle_choice_test"] = heldout_for(chosen_idle, "idle_s")
    selected["keys_choice_test"] = heldout_for(chosen_keys, "keys_30s_limit")
    context_pred = prediction(frame, 30, 8, context_s=int(chosen_context["context_s"]))
    selected["context_choice"] = {k: (v.item() if hasattr(v, "item") else v) for k, v in chosen_context.to_dict().items()}
    selected["context_choice_test"] = score(y[test.to_numpy()], context_pred[test.to_numpy()])
    return sweep, selected


def cooldown_audit(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    frame["trigger_time"] = pd.to_datetime(frame["trigger_time"], errors="coerce")
    frame = frame.dropna(subset=["trigger_time"]).sort_values(["solution_id", "trigger_time"])
    rows = []
    for cooldown in COOLDOWN_GRID:
        kept = 0
        per_session: list[int] = []
        for _, group in frame.groupby("solution_id", sort=False):
            last = None
            count = 0
            for timestamp in group["trigger_time"]:
                if last is None or (timestamp - last).total_seconds() >= cooldown:
                    kept += 1
                    count += 1
                    last = timestamp
            per_session.append(count)
        rows.append({
            "cooldown_s": cooldown,
            "candidate_count": kept,
            "sessions": int(frame["solution_id"].nunique()),
            "mean_candidates_per_session": kept / max(1, frame["solution_id"].nunique()),
            "p95_candidates_per_session": float(np.percentile(per_session, 95)) if per_session else 0.0,
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DATA / "offline_research")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-prompt-rate", type=float, default=None,
                        help="Optional development-set budget, e.g. 0.20")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    windows = pd.read_csv(WINDOWS)
    windows["solution_id"] = pd.to_numeric(windows["solution_id"], errors="coerce")
    for col in ("current_idle_s", "keys_30s", "clipboard_ops_30s"):
        windows[col] = pd.to_numeric(windows[col], errors="coerce").fillna(0)

    all_sweeps = []
    selections = []
    label_summary = {}
    for label_name, path in LABEL_FILES.items():
        labels = pd.read_csv(path, usecols=["window_id", "label"])
        frame = windows.merge(labels, on="window_id", how="inner", validate="one_to_one")
        frame = frame[frame["label"].isin([0, 1])].copy()
        dev, test = split_by_group(frame, args.seed)
        sweep, selected = threshold_sweep(frame, label_name, dev, test, args.max_prompt_rate)
        all_sweeps.append(sweep)
        selections.append(selected)
        label_summary[label_name] = {
            "rows": int(len(frame)),
            "sessions": int(frame["solution_id"].nunique()),
            "unknown_excluded": int((labels["label"] == -1).sum()),
            "idle_quantiles_s": {str(q): float(frame["current_idle_s"].quantile(q)) for q in (.1, .25, .5, .75, .9, .95)},
            "dev_sessions": int(frame.loc[dev, "solution_id"].nunique()),
            "test_sessions": int(frame.loc[test, "solution_id"].nunique()),
        }

    sweep_frame = pd.concat(all_sweeps, ignore_index=True)
    sweep_frame.to_csv(args.out_dir / "threshold_sweep.csv", index=False, encoding="utf-8-sig")
    (args.out_dir / "threshold_selection.json").write_text(json.dumps({
        "seed": args.seed,
        "max_prompt_rate": args.max_prompt_rate,
        "label_summary": label_summary,
        "selected_on_dev": selections,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    cooldown = cooldown_audit(ROOT / "data" / "clean_oj" / "full_causal_candidates.csv")
    if len(cooldown):
        cooldown.to_csv(args.out_dir / "cooldown_sweep.csv", index=False, encoding="utf-8-sig")

    lines = [
        "# Data-driven threshold selection",
        "",
        "阈值被视为策略参数，而不是学生状态的真值。标签 `-1` 表示未知，未参与评分；参数只在按 `solution_id` 分组的开发集上选择，测试集仅用于留出报告。",
        "",
        "## 参数边界",
        "",
        "- idle trigger：" + ", ".join(f"{x}s" for x in IDLE_GRID),
        "- `keys_30s` 上限：" + ", ".join(str(x) for x in KEY_GRID),
        "- activity context window：" + ", ".join(f"{x}s" for x in CONTEXT_GRID),
        "- clipboard：固定要求 30 秒内无剪贴板操作；这是当前可复现规则的组成部分，不是假设为普适真理。",
        "",
        "## 如何解释 30 秒",
        "",
        "如果 27/30/33 秒在留出集上的指标和置信区间高度重叠，则不能声称存在精确的 30 秒最优点；应报告一个稳定区间，或根据提示预算选择运营上最合适的点。若 30 秒落在开发集选择结果之外，也不能继续把它写成预注册阈值。",
        "",
        "## 本次留出结果摘要",
        "",
        "| 标签 | 开发集选择的 idle | 测试集 F1 | 测试集 Recall | 测试集误提示率 |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in selections:
        chosen = item["idle_choice"]
        heldout = item["idle_choice_test"]
        lines.append(f"| {item['label']} | {chosen['idle_s']:.0f}s | {heldout['f1']:.3f} | {heldout['recall']:.3f} | {heldout['false_prompt_rate']:.3f} |")
    lines += [
        "",
        "该表只说明在给定标签口径、提示率上限和一次固定分组切分下，哪个参数在开发集被选中以及它在留出集的表现；它不证明不同标签共用同一个阈值，也不证明提示有效。",
        "",
        "| 标签 | 开发集选择的 activity context | 测试集 F1 | 测试集候选率 |",
        "|---|---:|---:|---:|",
    ]
    for item in selections:
        context = item["context_choice"]
        heldout = item["context_choice_test"]
        lines.append(f"| {item['label']} | {context['context_s']:.0f}s | {heldout['f1']:.3f} | {heldout['predicted_rate']:.3f} |")
    lines += [
        "",
        "### 27/30/33 秒邻近阈值",
        "",
        "| 标签 | idle | 测试集 F1 | session bootstrap 95% CI | 测试集候选率 |",
        "|---|---:|---:|---:|---:|",
    ]
    neighbors = sweep_frame[(sweep_frame["parameter"] == "idle_s") & (sweep_frame["split"] == "test") & (sweep_frame["idle_s"].isin([27, 30, 33]))]
    for _, row in neighbors.iterrows():
        ci = f"{row['f1_ci_low']:.3f}--{row['f1_ci_high']:.3f}"
        lines.append(f"| {row['label']} | {row['idle_s']:.0f}s | {row['f1']:.3f} | {ci} | {row['predicted_rate']:.3f} |")
    lines += [
        "",
        "## 输出文件",
        "",
        "- `threshold_sweep.csv`：每套标签、每个参数和 dev/test 的 Precision、Recall、F1、误提示率及候选率。",
        "- `threshold_selection.json`：数据分位数、分组切分和开发集选择结果。",
        "- `cooldown_sweep.csv`：冷却时长对真实候选负载的影响。",
        "",
        "## 限制",
        "",
        "本实验仍然评估与人工操作性标签的一致程度，不证明提示有效；不同标签口径、候选集外漏报和未观测的判题可见时间仍需单独验证。",
    ]
    (args.out_dir / "threshold_selection_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"threshold_sweep={args.out_dir / 'threshold_sweep.csv'}")
    print(f"selection={args.out_dir / 'threshold_selection.json'}")
    if len(cooldown):
        print(f"cooldown_sweep={args.out_dir / 'cooldown_sweep.csv'}")


if __name__ == "__main__":
    main()
