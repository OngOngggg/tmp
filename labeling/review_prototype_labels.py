"""Batch-review prototype windows with a conservative, low-interruption policy.

This produces new review artifacts and never overwrites the downloaded labels.
The rule intentionally prefers 0/-1 when the evidence could be explained by
reading, checking output, or leaving the editor idle.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WINDOWS = DATA / "prototype_windows.csv"
USER_LABELS = Path(r"C:\Users\10950\Downloads\prototype_labels.csv")
FIRST100 = DATA / "prototype_labels_first100_ai_final.csv"
FULL_OUT = DATA / "prototype_labels_ai_full.csv"
REMAINING_OUT = DATA / "prototype_labels_ai_remaining400.csv"
REVIEW_OUT = DATA / "prototype_labels_ai_review.csv"
DIFF_OUT = DATA / "prototype_labels_ai_disagreements.csv"
REPORT_OUT = DATA / "prototype_labels_ai_report.md"


def code_signal(value: object) -> int:
    text = re.sub(r"[^A-Za-z0-9_#%<>=+*/;{}()\[\]\\]", "", str(value or ""))
    return len(text)


def classify(row: pd.Series) -> tuple[int, str]:
    total = max(float(row.get("total_keys", 0) or 0), 1.0)
    progress = float(row.get("event_index", 0) or 0) / total
    idle = float(row.get("current_idle_s", 0) or 0)
    keys30 = int(row.get("keys_30s", 0) or 0)
    text30 = int(row.get("text_keys_30s", 0) or 0)
    text60 = int(row.get("text_keys_60s", 0) or 0)
    text120 = int(row.get("text_keys_120s", 0) or 0)
    ctrl30 = int(row.get("control_30s", 0) or 0)
    mod30 = int(row.get("modifier_keys_30s", 0) or 0)
    clip30 = int(row.get("clipboard_ops_30s", 0) or 0)
    pause30 = float(row.get("pause_total_30s", 0) or 0)
    signal = code_signal(row.get("code_replay", ""))

    # Very sparse or malformed traces are not safe positive examples.
    if signal < 30 or total < 80:
        return -1, "按键/代码证据过少或回放异常，跳过"

    # Control/C/V dominated activity is usually clipboard or editor control.
    if clip30 and text30 <= max(4, 2 * clip30) and mod30 >= text30:
        return -1, "最近主要是快捷键/剪贴板操作，不足以判断需要弹窗"
    if keys30 and ctrl30 / keys30 >= 0.5 and text30 <= 5:
        return -1, "修饰键占比过高，不像持续编码"

    # A long quiet period after substantial progress is more likely reading,
    # checking output, or being away than asking for help.
    if idle >= 60 and text30 == 0:
        return 0, "长时间无文本输入，保守视为阅读/检查，不打扰"
    if idle >= 30 and text30 == 0 and progress >= 0.45:
        return 0, "代码已有较大进展且当前空闲，优先不打扰"

    # Recent active typing is not a good time to interrupt.
    if idle <= 5 and text30 >= 5:
        return 0, "最近仍在持续输入，不应因活动本身弹窗"
    if text30 >= 10 and idle <= 15:
        return 0, "近期仍有明显文本输入，没有明确卡住证据"

    # Potential stuck/slow phase: enough code exists, recent progress is low,
    # and the student is not yet at the end of the session. Keep this narrow.
    if progress < 0.72 and 10 <= idle < 45 and text30 <= 3 and text60 > 0:
        return 1, "近期输入很少但仍在任务中，可能卡住，可考虑弹窗"
    if progress < 0.60 and 5 <= idle < 20 and text30 <= 2 and text60 <= 12 and pause30 >= 8:
        return 1, "短窗口低速且有明显停顿，可能需要帮助"

    # Ambiguous low activity is deliberately skipped rather than promoted.
    if idle >= 10 and text30 <= 3:
        return -1, "低活动可能是思考/阅读，证据不足"
    return 0, "没有明确卡住证据，保守不打扰"


def main() -> None:
    windows = pd.read_csv(WINDOWS)
    user = pd.read_csv(USER_LABELS) if USER_LABELS.exists() else pd.DataFrame()
    first = pd.read_csv(FIRST100) if FIRST100.exists() else pd.DataFrame()

    predictions: list[int] = []
    reasons: list[str] = []
    for _, row in windows.iterrows():
        label, reason = classify(row)
        predictions.append(label)
        reasons.append(reason)

    review = windows[["window_id", "solution_id", "event_index", "window_end_time"]].copy()
    review["my_label"] = predictions
    review["reason"] = reasons
    if not user.empty:
        review = review.merge(user[["window_id", "label"]].rename(columns={"label": "user_label"}),
                              on="window_id", how="left")
        review["same_as_user"] = review["my_label"].eq(review["user_label"])
    else:
        review["user_label"] = pd.NA
        review["same_as_user"] = pd.NA

    # Preserve the completed first-100 review as the authoritative prefix.
    if not first.empty:
        prefix = first.set_index("window_id")["label"]
        mask = review.window_id.isin(prefix.index)
        review.loc[mask, "my_label"] = review.loc[mask, "window_id"].map(prefix)
        review.loc[mask, "reason"] = "前100条已完成复核，沿用AI最终标签"
        if "user_label" in review:
            review.loc[mask, "same_as_user"] = review.loc[mask, "my_label"].eq(review.loc[mask, "user_label"])

    final = review[["window_id", "solution_id", "event_index", "window_end_time", "my_label"]].rename(columns={"my_label": "label"})
    final.to_csv(FULL_OUT, index=False, encoding="utf-8-sig")
    review.iloc[100:].to_csv(REMAINING_OUT, index=False, encoding="utf-8-sig")
    review.to_csv(REVIEW_OUT, index=False, encoding="utf-8-sig")
    comparable_diff = review[review.user_label.notna() & review.same_as_user.eq(False)]
    comparable_diff.to_csv(DIFF_OUT, index=False, encoding="utf-8-sig")

    remaining = review.iloc[100:]
    comparable = review[review.user_label.notna()]
    report = [
        "# Prototype 标签批量复核报告",
        "",
        f"- 原型窗口总数：{len(windows)}",
        f"- 本次批量复核：第101–500条，共 {len(remaining)} 条",
        f"- AI最终标签分布：{final.label.value_counts().sort_index().to_dict()}",
        f"- 下载文件已有用户标签：{len(comparable)} 条",
        f"- 在已有用户标签中，一致：{int(comparable.same_as_user.sum())} 条，不一致：{int((~comparable.same_as_user).sum())} 条",
        "- 判定策略：优先降低误打扰；长时间idle且无文本输入通常判0；快捷键/剪贴板或异常记录判-1；只在低速、仍处于任务中且有一定停滞证据时判1。",
        "- 原始 C:/Users/10950/Downloads/prototype_labels.csv 未修改。",
    ]
    REPORT_OUT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("windows", len(windows))
    print("remaining_reviewed", len(remaining))
    print("final_counts", final.label.value_counts().sort_index().to_dict())
    print("user_comparable", len(comparable), "same", int(comparable.same_as_user.sum()), "different", int((~comparable.same_as_user).sum()))
    print("full", FULL_OUT)
    print("remaining", REMAINING_OUT)
    print("review", REVIEW_OUT)
    print("diff", DIFF_OUT)
    print("report", REPORT_OUT)


if __name__ == "__main__":
    main()
