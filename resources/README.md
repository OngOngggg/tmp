# 项目资源归档说明（resources/）

本目录用于把项目交接所需的外部资料集中归档，方便下一个 AI / 接手人一次性找到“论文 + 原始数据”。

## 目录结构

```text
resources/
├── papers/           已归档的相关论文（PDF 正文 + txt 提取 + 文献笔记）
├── original_labels/  用户从浏览器标注页面导出的两份原始标签 CSV（只读归档）
└── README.md         本说明
```

## 1. papers/ —— 相关论文

来源：`lit_pdf/`（原位置保留，此处为归档副本）。

| 文件 | 说明 |
|---|---|
| dong2021.pdf / .txt | Dong et al. (2021)，EDM，SourceCheck 代码进展 + 时间阈值判断挣扎时刻 |
| tabarsi2022.pdf / .txt | Tabarsi et al. (2022)，7 个规则 detector + 学生自报告 |
| schwartz2025.pdf / .txt | Schwartz et al. (2025)，PTM 深度学习预测学生任务级挣扎 |
| pu2025.pdf / .txt | Pu et al. (2025)，6 类启发式主动触发 + LLM，主动帮助与打扰权衡 |
| koutcheme2024.pdf / .txt | Koutcheme et al. (2024)，GPT-4-as-judge 评反馈质量 |
| tabarsi_meta.json | Tabarsi 论文元数据 |
| five_papers_extraction.md | 5 篇正文级字段提取（标签/标注者/样本/划分/指标/局限） |
| literature_evidence_for_report.md | 汇报用文献证据速览 |

## 2. original_labels/ —— 原始人工标签

来源：用户浏览器标注页面导出的两份 CSV，此前散落在 `C:\Users\10950\Downloads\`，现归档到此处（只读副本，原 Downloads 文件未删除）。

| 文件 | 说明 |
|---|---|
| prototype_labels.csv | 第一批导出标签（235 条） |
| prototype_labels_remaining.csv | 第二批导出标签（265 条） |

> 这两份是全部人工标签的**可追溯源头**。项目内 `labeling/data/` 下的标签文件（human_complete / human_reviewed / recall_candidates）都是由它们合并、复核、再生成而来。**归档副本不要修改**；若需复核，另存审计文件。

## 3. 原始按键数据（未复制，位置说明）

**位置：`data/export/key_action_batch_001.csv` ~ `key_action_batch_116.csv`**

- 共 116 个文件，约 **6.63 GB**。
- 这是最原始的按键事件导出，字段：
  ```
  id, action, solution_id, start_time, problem_id, created_by, created_time
  ```
- `action` 是 JSON 字符串（按键事件数组），每个事件含 `key / time / type(up|down) / row / column`。

**为什么没有复制到 resources/：**

1. 体积 6.63 GB，复制会再占用等量磁盘空间；
2. `build_prototype.py`、`export_filtered.py` 等脚本硬编码依赖 `data/export/` 路径，移动会破坏脚本；
3. 它本来就已经在项目目录 `D:\02_code\project\python\oj_demo\data\export\` 下面，属于“已经在项目里”。

如果确实需要把原始按键流一并打包带走，请直接复制整个 `data/export/` 目录，而不要移动它。

## 4. 其他关键数据位置

| 数据 | 位置 |
|---|---|
| 清洗后的 session | `labeling/data/clean_sessions.csv`（约 41,927 行） |
| 原型窗口特征表 | `labeling/data/prototype_windows.csv`（500 × 77） |
| 最终统一标签 | `labeling/data/prototype_labels_recall_candidates.csv`（69/297/134） |
| 事件驱动候选 | `labeling/data/event_driven_candidates.csv`（462 条） |

## 5. 快速阅读顺序

1. `PROJECT_HANDBOOK.md`（项目总手册，先读这个）
2. `resources/papers/five_papers_extraction.md`（论文做了什么）
3. `labeling/data/small_paper_completion_plan.md`（小论文还差什么）
4. `tomorrow_report_revised.md`（阶段汇报口径）
