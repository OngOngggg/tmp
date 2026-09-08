"""Merge the two user-exported label batches without changing label values.

Outputs new canonical/provenance files. Original Downloads exports are kept
untouched. This is a data-integrity step, not a metric-optimization step.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
FIRST = Path(r"C:\Users\10950\Downloads\prototype_labels.csv")
REMAINING = Path(r"C:\Users\10950\Downloads\prototype_labels_remaining.csv")
OUT = DATA / "prototype_labels_human_complete.csv"
QC = DATA / "prototype_labels_human_qc.md"


def load(path: Path, source: str) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"window_id": "string", "solution_id": "Int64"})
    frame["label"] = pd.to_numeric(frame["label"], errors="coerce")
    frame["source_batch"] = source
    return frame


def main() -> None:
    first = load(FIRST, "first_235")
    remaining = load(REMAINING, "remaining_265")
    labels = pd.concat([first, remaining], ignore_index=True)
    windows = pd.read_csv(WINDOWS, dtype={"window_id": "string", "solution_id": "Int64"})

    overlap = set(first.window_id) & set(remaining.window_id)
    duplicate_ids = labels[labels.window_id.duplicated(False)].window_id.dropna().unique().tolist()
    missing_from_windows = sorted(set(labels.window_id.dropna()) - set(windows.window_id.dropna()))
    unlabeled_windows = sorted(set(windows.window_id.dropna()) - set(labels.window_id.dropna()))
    invalid = labels[~labels.label.isin([-1, 0, 1]) | labels.label.isna()]
    solution_mismatch = labels.merge(
        windows[["window_id", "solution_id"]], on="window_id", suffixes=("_label", "_window")
    )
    solution_mismatch = solution_mismatch[
        solution_mismatch.solution_id_label.ne(solution_mismatch.solution_id_window)
    ]

    labels = labels.sort_values(["solution_id", "event_index", "window_id"]).reset_index(drop=True)
    labels.to_csv(OUT, index=False, encoding="utf-8-sig")

    counts = labels.label.value_counts().to_dict()
    known = labels[labels.label.isin([0, 1])]
    sessions = known.solution_id.nunique()
    report = [
        "# 完整人工标签数据质量报告",
        "",
        "## 数据来源",
        "",
        f"- 第一批：{FIRST}，{len(first)}条。",
        f"- 第二批：{REMAINING}，{len(remaining)}条。",
        f"- 合并后输出：`{OUT.name}`。",
        "- 原始下载文件未修改，标签值未为改善指标而调整。",
        "",
        "## 完整性检查",
        "",
        f"- 合并总行数：{len(labels)}。",
        f"- 唯一window_id：{labels.window_id.nunique()}。",
        f"- 两批重复window_id：{len(overlap)}。",
        f"- 标签无法匹配窗口：{len(missing_from_windows)}。",
        f"- 尚未标注窗口：{len(unlabeled_windows)}。",
        f"- 非法或缺失标签：{len(invalid)}。",
        f"- solution_id不一致：{len(solution_mismatch)}。",
        "",
        "## 标签分布",
        "",
        "|label|含义|数量|",
        "|---:|---|---:|",
        f"|1|该提示|{counts.get(1, 0)}|",
        f"|0|不该提示|{counts.get(0, 0)}|",
        f"|-1|不确定/跳过|{counts.get(-1, 0)}|",
        "",
        f"确定二分类标签：{len(known)}条；涉及session：{sessions}个。",
        "",
        "## 说明",
        "",
        "这份文件用于正式离线评估。若后续需要复核某条标签，应在单独的审计文件中记录old_label、new_label、reason和reviewer，不直接覆盖本文件。",
    ]
    QC.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"merged={len(labels)} unique_window_id={labels.window_id.nunique()}")
    print(f"counts={counts}")
    print(f"overlap={len(overlap)} missing={len(missing_from_windows)} unlabeled={len(unlabeled_windows)} invalid={len(invalid)}")
    print(f"out={OUT}")
    print(f"qc={QC}")


if __name__ == "__main__":
    main()
