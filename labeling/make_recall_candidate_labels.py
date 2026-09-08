"""Create a recall-oriented candidate-label variant.

This is intentionally separate from the conservative reviewed labels.  Long
idle windows are restored to candidate-positive because the online system is
allowed to send them to an LLM for a second-stage decision.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REVIEWED = DATA / "prototype_labels_human_reviewed.csv"
CHANGES = DATA / "prototype_label_review_changes.csv"
OUT = DATA / "prototype_labels_recall_candidates.csv"
OUT_CHANGES = DATA / "prototype_recall_candidate_changes.csv"
REPORT = DATA / "prototype_recall_candidate_report.md"

def main() -> None:
    labels = pd.read_csv(REVIEWED)
    changes = pd.read_csv(CHANGES)
    # Restore only the conservative reclassification of original positives;
    # this keeps the candidate variant traceable to the 90 reviewed positives.
    restore = changes[changes.reason_code.eq("long_idle_no_recent_evidence")].copy()
    restore_ids = set(restore.window_id)
    out = labels.copy()
    out.loc[out.window_id.isin(restore_ids), "label"] = 1
    out.to_csv(OUT, index=False, encoding="utf-8-sig")

    restore["candidate_old_label"] = restore.new_label
    restore["candidate_new_label"] = 1
    restore["candidate_reason"] = (
        "高召回候选：长时间无近期编辑/新反馈，先送二次LLM复核；不直接等同于最终应弹窗。"
    )
    restore[["window_id", "solution_id", "event_index", "window_end_time",
             "candidate_old_label", "candidate_new_label", "reason_code",
             "candidate_reason", "judge", "current_idle_s", "keys_30s",
             "text_keys_30s", "keys_60s"]].to_csv(OUT_CHANGES, index=False, encoding="utf-8-sig")

    counts = out.label.value_counts().to_dict()
    report = f"""# 高召回候选标签版本

这是面向“规则召回候选 + LLM二次复核”的标签版本，不替代严格人工标签。

- 基础文件：`prototype_labels_human_reviewed.csv`
- 恢复为候选正例：{len(restore)}条长时间无近期编辑证据的窗口。
- 当前分布：`1`候选={counts.get(1, 0)}，`0`={counts.get(0, 0)}，`-1`={counts.get(-1, 0)}。

长时间无输入可能表示卡住，也可能表示读题、检查、等待或离开页面。因此这里把它定义为“宁可多召回、交给LLM判断”的候选，不把它直接解释为学生已经明确需要帮助。

## 漏报处理

仅让LLM复核规则触发的窗口，无法发现规则没有召回的漏报。在线设计应采用：

1. 多个高召回规则取并集（长idle、失败结果后停滞、近期编辑后暂停、异常重复运行/修改）；
2. 对规则未触发窗口做低比例LLM抽检或第二检测器扫描，持续发现漏报模式；
3. 把新发现的漏报模式加入候选规则，再在独立时间段重新评估。

最终报告同时给出候选召回率和LLM确认后的有效提示率，不能只报告LLM候选集上的Precision。
"""
    REPORT.write_text(report, encoding="utf-8")
    print(f"restored_long_idle={len(restore)}")
    print(out.label.value_counts().sort_index().to_string())

if __name__ == "__main__":
    main()
