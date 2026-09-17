# 项目资源归档说明（resources/）

本目录用于归档项目交接所需的原始人工标签数据。

## 目录结构

```text
resources/
├── original_labels/  用户从浏览器标注页面导出的原始标签 CSV（只读归档）
└── README.md         本说明
```

## original_labels/ —— 原始人工标签

来源：用户浏览器标注页面导出的两份 CSV，此前散落在 `C:\Users\10950\Downloads\`，现归档到此处（只读副本，原 Downloads 文件未删除）。

| 文件 | 说明 |
|---|---|
| prototype_labels.csv | 第一批导出标签（235 条） |
| prototype_labels_remaining.csv | 第二批导出标签（265 条） |

> 这两份是全部人工标签的**可追溯源头**。项目内 `legacy/data/` 下的标签文件（human_complete / human_reviewed / recall_candidates）都是由它们合并、复核、再生成而来。**归档副本不要修改**；若需复核，另存审计文件。

## 文献

相关论文现统一存放在 `lit_pdf/` 目录（PDF 正文 + txt 提取 + 文献笔记），此处不再重复归档。

## 原始按键数据（位置说明）

**位置：`data/export/key_action_batch_001.csv` ~ `key_action_batch_116.csv`**

- 共 116 个文件，约 **6.63 GB**。
- 这是最原始的按键事件导出，字段：
  ```
  id, action, solution_id, start_time, problem_id, created_by, created_time
  ```
- `action` 是 JSON 字符串（按键事件数组），每个事件含 `key / time / type(up|down) / row / column`。

**为什么没有复制到 resources/：**

1. 体积 6.63 GB，复制会再占用等量磁盘空间；
2. 脚本硬编码依赖 `data/export/` 路径，移动会破坏脚本；
3. 它本来就已经在项目目录 `D:\02_code\project\python\oj_demo\data\export\` 下面，属于"已经在项目里"。

如果确实需要把原始按键流一并打包带走，请直接复制整个 `data/export/` 目录，而不要移动它。

## 快速阅读顺序

1. `docs/PROJECT_HANDBOOK.md`（项目总手册，先读这个）
2. `lit_pdf/five_papers_extraction.md`（论文做了什么）
3. `legacy/data/small_paper_completion_plan.md`（小论文还差什么）
4. `docs/tomorrow_report_revised.md`（阶段汇报口径）
