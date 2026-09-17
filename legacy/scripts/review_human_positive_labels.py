"""Conservative second-pass review of the original positive labels.

The original merged labels are preserved.  This review only reclassifies the
90 windows whose original label is 1 and writes a separate change log.
Rules use only features available at the window end.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LABELS = DATA / "prototype_labels_human_complete.csv"
WINDOWS = DATA / "prototype_windows.csv"
REVIEW_INPUT = DATA / "human_positive_review_input.csv"
REVIEWED = DATA / "prototype_labels_human_reviewed.csv"
CHANGES = DATA / "prototype_label_review_changes.csv"
REPORT = DATA / "prototype_review_report.md"


def classify(row: pd.Series) -> tuple[int, str, str]:
    """Return reviewed label, reason code, and Chinese explanation."""
    idle = float(row.current_idle_s)
    keys30 = int(row.keys_30s)
    text30 = int(row.text_keys_30s)
    keys60 = int(row.keys_60s)
    control30 = int(row.control_30s)
    clipboard30 = int(row.clipboard_ops_30s)

    # A window ending during actual text input is not a sensible interruption
    # point, even when the old annotator marked it positive.
    if idle < 10 and text30 >= 2:
        return 0, "active_recent_input", "窗口结束时仍在连续输入，不应因活动本身弹窗。"

    # Repeated shortcuts or clipboard activity do not identify a learning
    # difficulty; they may represent navigation, paste, or inspection.
    if clipboard30 > 0 or (control30 >= 3 and text30 < 5):
        return -1, "shortcut_or_clipboard_ambiguous", "主要是快捷键/剪贴板或非文本操作，无法判断需要帮助。"

    # A long idle interval with no recent activity is compatible with reading,
    # checking output, waiting, or leaving the page.  It is not causal evidence
    # of a need for an intervention.
    if (idle >= 60 and keys30 == 0) or (idle >= 30 and keys30 == 0 and keys60 == 0):
        return -1, "long_idle_no_recent_evidence", "长时间无近期编辑证据，可能在读题、检查、等待或离开页面。"

    # Keep a positive only when a recent edit is followed by a bounded pause.
    # This is a candidate for a low-disruption prompt, not proof that help works.
    if (10 <= idle < 30 and text30 >= 1) or (30 <= idle < 60 and keys60 >= 8):
        return 1, "recent_edit_then_pause", "停顿前仍有近期编辑，且停顿处于有限范围，保留为帮助候选。"

    return -1, "insufficient_evidence", "存在停顿但缺少足够的即时行为证据，标为不确定。"


def main() -> None:
    labels = pd.read_csv(LABELS)
    windows = pd.read_csv(WINDOWS)
    review_input = pd.read_csv(REVIEW_INPUT)

    feature_cols = [
        "window_id", "solution_id", "event_index", "window_end_time", "judge",
        "current_idle_s", "keys_30s", "text_keys_30s", "keys_60s",
        "backspace_30s", "enter_30s", "control_30s", "clipboard_ops_30s",
        "row_changes_30s", "column_changes_30s", "key_summary", "code_replay",
    ]
    features = windows[feature_cols]
    review = review_input.merge(
        features.drop(columns=["judge", "key_summary", "code_replay"]),
        on=["window_id", "solution_id"], how="left", suffixes=("_review", "_window"),
        validate="one_to_one",
    )

    # The review input already contains the features used in the first pass;
    # prefer the canonical window table when a duplicate exists.
    for col in [
        "event_index", "window_end_time", "judge", "current_idle_s", "keys_30s",
        "text_keys_30s", "keys_60s", "backspace_30s", "enter_30s", "control_30s",
        "clipboard_ops_30s", "row_changes_30s", "column_changes_30s",
    ]:
        if f"{col}_window" in review:
            review[col] = review[f"{col}_window"].combine_first(review.get(f"{col}_review"))
    review["old_label"] = 1
    classified = review.apply(classify, axis=1, result_type="expand")
    classified.columns = ["new_label", "reason_code", "review_reason"]
    review = pd.concat([review, classified], axis=1)
    review["new_label"] = review.new_label.astype(int)

    reviewed = labels.copy()
    change_map = review.set_index("window_id").new_label
    reviewed["label"] = reviewed.apply(
        lambda r: int(change_map[r.window_id]) if r.window_id in change_map else int(r.label),
        axis=1,
    )
    reviewed.to_csv(REVIEWED, index=False, encoding="utf-8-sig")

    changes = review.loc[review.new_label.ne(review.old_label), [
        "window_id", "solution_id", "event_index", "window_end_time", "old_label",
        "new_label", "reason_code", "review_reason", "judge", "current_idle_s",
        "keys_30s", "text_keys_30s", "keys_60s", "backspace_30s", "enter_30s",
        "control_30s", "clipboard_ops_30s", "row_changes_30s", "column_changes_30s",
    ]].copy()
    changes["review_version"] = "positive-recheck-v1"
    changes["reviewer"] = "codex_independent_conservative_review"
    changes.to_csv(CHANGES, index=False, encoding="utf-8-sig")

    original_counts = labels.label.value_counts().to_dict()
    reviewed_counts = reviewed.label.value_counts().to_dict()
    changed_counts = changes.new_label.value_counts().to_dict()
    reason_counts = review.reason_code.value_counts().to_dict()
    report = f"""# 人工正例二次复核

## 范围

- 原始合并标签：500条，其中原始`1`为{original_counts.get(1, 0)}条。
- 仅复核原始标签为`1`的窗口；原始标签文件未修改。
- 复核使用窗口结束时已可见的行为特征，不使用未来事件。

## 复核结果

|标签|复核后数量|原始1窗口在该标签的数量|
|---|---:|---:|
|`1` 该提示|{reviewed_counts.get(1, 0)}|{sum(1 for x in review.new_label if x == 1)}|
|`0` 不该提示|{reviewed_counts.get(0, 0)}|{changed_counts.get(0, 0)}|
|`-1` 不确定/跳过|{reviewed_counts.get(-1, 0)}|{changed_counts.get(-1, 0)}|

本次修改：{len(changes)}条（`1 -> 0`：{changed_counts.get(0, 0)}，`1 -> -1`：{changed_counts.get(-1, 0)}）。

## 判定依据

|规则|数量|处理|
|---|---:|---|
|`active_recent_input`|{reason_counts.get("active_recent_input", 0)}|改为0|
|`shortcut_or_clipboard_ambiguous`|{reason_counts.get("shortcut_or_clipboard_ambiguous", 0)}|改为-1|
|`long_idle_no_recent_evidence`|{reason_counts.get("long_idle_no_recent_evidence", 0)}|改为-1|
|`recent_edit_then_pause`|{reason_counts.get("recent_edit_then_pause", 0)}|保留1|
|`insufficient_evidence`|{reason_counts.get("insufficient_evidence", 0)}|改为-1|

`1`仅表示“可以作为低打扰帮助候选”，不是已经证明学生需要帮助；`-1`表示当前证据不能支持干预判断。

## 产物

- `prototype_labels_human_reviewed.csv`：复核后的独立标签副本。
- `prototype_label_review_changes.csv`：逐条记录旧标签、新标签、理由和复核版本。

原始`prototype_labels_human_complete.csv`及用户导出的两个文件均未覆盖。
"""
    REPORT.write_text(report, encoding="utf-8")
    print(f"reviewed={len(reviewed)} changes={len(changes)}")
    print(review.new_label.value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
