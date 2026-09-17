"""Unified rule ablation on the current independently labelled subset.

This is a new script and does not overwrite older scripts or result files.
All predictors are available at the window end; submitted_code and final judge
are deliberately excluded to avoid future-information leakage.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
def score(y: pd.Series, pred: pd.Series) -> dict[str, float | int]:
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "n": int(len(y)), "positive": int(y.sum()), "trigger": int(pred.sum()),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path,
                        default=Path(r"C:\Users\10950\Downloads\prototype_labels.csv"))
    parser.add_argument("--output-stem", default="small_paper_extended_ablation")
    args = parser.parse_args()
    out_csv = DATA / f"{args.output_stem}.csv"
    out_md = DATA / f"{args.output_stem}.md"

    windows = pd.read_csv(WINDOWS)
    labels = pd.read_csv(args.labels)
    d = windows.merge(labels[["window_id", "solution_id", "label"]],
                       on=["window_id", "solution_id"], validate="one_to_one")
    d = d[d.label.isin([0, 1])].copy()
    d["label"] = d.label.astype(int)
    y = d.label

    no_clip = d.clipboard_ops_30s == 0
    low_activity = d.keys_30s < 8
    rules = {
        "idle_ge30": d.current_idle_s >= 30,
        "keys30_lt5": d.keys_30s < 5,
        "keys60_lt20": d.keys_60s < 20,
        "idle20_keys30_lt8": (d.current_idle_s >= 20) & low_activity,
        "idle20_keys30_lt8_no_clip": (d.current_idle_s >= 20) & low_activity & no_clip,
        "idle20_multiscale": ((d.current_idle_s >= 20) & (d.keys_10s <= 1)
                              & low_activity & (d.keys_60s < 20)),
        "multiscale_no_clip": low_activity & (d.keys_60s < 20) & no_clip,
        "idle20_low_text_row": ((d.current_idle_s >= 20) & (d.text_keys_30s < 5)
                                & (d.row_changes_30s <= 1)),
        "idle10_backspace2_no_clip": ((d.current_idle_s >= 10)
                                       & (d.backspace_30s >= 2) & no_clip),
        "idle10_pause_lowkeys_no_clip": ((d.current_idle_s >= 10)
                                          & (d.pause_count_30s >= 1)
                                          & (d.keys_30s < 12) & no_clip),
        "idle20_no_clip_low_control": ((d.current_idle_s >= 20) & low_activity
                                        & no_clip & (d.control_30s < 3)),
        "union_low_activity_or_edit_struggle": (
            ((d.current_idle_s >= 20) & low_activity & no_clip)
            | ((d.current_idle_s >= 10) & (d.backspace_30s >= 2) & no_clip)
        ),
    }

    rows = []
    for name, pred in rules.items():
        row = {"rule": name}
        row.update(score(y, pred.astype(int)))
        rows.append(row)
    result = pd.DataFrame(rows)
    result.to_csv(out_csv, index=False, encoding="utf-8-sig")

    display = result.copy()
    for col in ("precision", "recall", "f1"):
        display[col] = display[col].map(lambda x: f"{x:.1%}")
    report = [
        "# 扩展规则消融（统一口径）", "",
        f"- 数据：`prototype_windows.csv` 与 `{args.labels}` 合并。",
        f"- 确定二分类窗口：{len(d)} 条；正例 {int(y.sum())}，负例 {int((y == 0).sum())}；session {d.solution_id.nunique()} 个。",
        "- 只使用窗口结束前可知的特征；`submitted_code`、最终 `judge` 和结束后的事件不作为预测变量。",
        "- 指标表示规则与当前单人确定标签的一致程度，不等同于线上干预效果。", "",
        "## 结果", "", display.to_markdown(index=False), "",
        "## 如何解读", "",
        "- idle、按键数规则是低活动基线；多尺度规则检验短期与较长上下文的组合。",
        "- 退格/停顿规则是局部编辑困难候选，可能改善漏报，也可能增加误报。",
        "- 剪贴板、Control、运行、提交、失焦和冷却属于在线保护/状态过滤，不能写成已经完成的监督消融。",
        "- 正式论文应按 solution/session 分组交叉验证，并报告 session 级结果或置信区间。", "",
        "## 口径边界", "",
        "本表用于比较候选规则是否值得继续研究，不代表在线提示已经改善学习效果。",
    ]
    out_md.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(result.to_string(index=False))
    print(f"written: {out_csv}")
    print(f"written: {out_md}")


if __name__ == "__main__":
    main()
