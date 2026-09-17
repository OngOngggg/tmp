"""Generate a separate labeling page for windows not yet in the user's export.

The existing labeling page, old labels, and old scripts are preserved. AI labels
are displayed as references only and are never copied into user labels.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import build_prototype


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "sessions" / "prototype_label_remaining.html"
USER_LABELS = Path(r"C:\Users\10950\Downloads\prototype_labels.csv")
AI_LABELS = DATA / "prototype_labels_ai_full.csv"
AI_REVIEW = DATA / "prototype_labels_ai_review.csv"


def main() -> None:
    windows = pd.read_csv(DATA / "prototype_windows.csv")
    if USER_LABELS.exists():
        user = pd.read_csv(USER_LABELS, usecols=["window_id"])
        done = set(user.window_id.astype(str))
    else:
        done = set()

    ai = pd.read_csv(AI_LABELS, usecols=["window_id", "label"])
    ai = ai.rename(columns={"label": "ai_label"})
    rows = windows[~windows.window_id.astype(str).isin(done)].merge(
        ai, on="window_id", how="left", validate="one_to_one"
    )

    if AI_REVIEW.exists():
        review = pd.read_csv(AI_REVIEW, usecols=["window_id", "reason"])
        review = review.rename(columns={"reason": "ai_reason"})
        rows = rows.merge(review, on="window_id", how="left", validate="one_to_one")

    original_path = build_prototype.PAGE_OUT
    build_prototype.PAGE_OUT = OUT
    try:
        build_prototype.make_page(rows.to_dict("records"))
    finally:
        build_prototype.PAGE_OUT = original_path

    html = OUT.read_text(encoding="utf-8")
    html = html.replace("Prototype window labeling", "Prototype remaining window labeling")
    html = html.replace("prototype_labels", "prototype_labels_remaining")
    ai_panel = (
        '<p class="hint"><b>AI参考（仅供判断，不会自动写入你的标签）</b><br>'
        "AI标签：${r.ai_label===1?'1 该弹':r.ai_label===0?'0 不该弹':'-1 跳过/不确定'}"
        "${r.ai_reason?`<br>AI理由：${esc(r.ai_reason)}`:''}</p>"
    )
    marker = '<h3>窗口特征</h3>'
    html = html.replace(marker, ai_panel + marker, 1)
    html = html.replace(
        "所有窗口都已标注。点击顶部按钮导出 prototype_labels_remaining.csv。",
        "所有剩余窗口都已标注。点击顶部按钮导出 prototype_labels_remaining.csv。",
    )
    OUT.write_text(html, encoding="utf-8")

    print(f"remaining_windows={len(rows)}")
    print(f"already_labeled={len(done)}")
    print(f"ai_reference_rows={int(rows.ai_label.notna().sum())}")
    print(f"page={OUT}")


if __name__ == "__main__":
    main()
