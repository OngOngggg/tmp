# OJ 在线编程“主动帮助时机识别”项目 · 完整交接手册

> 本文档面向“下一个 AI / 下一位接手人”，目标是只读本文档即可理解：
> 这个项目在做什么、为什么这么做、已经做到哪一步、有哪些结果、有哪些坑、接下来该往哪走。
> 所有数值均来自仓库内已有产物，未为了“好看”而修改任何标签或结论。

---

## 0. 一句话定位

这是一个**硕士毕业论文方向下的离线原型项目**，研究问题不是“怎么生成提示内容”，而是：

> 在在线判题（Online Judge，OJ）编程过程中，能否仅依据“当前时刻之前已经发生的行为”，识别出**适合主动提供帮助的候选时刻**，同时尽量不打断学生正常的思考、检查、等待和离开。

核心结论（当前阶段）：**长 idle + 近期低活动可以作为高召回候选信号，但纯规则/传统模型目前没有显著超过可解释规则；真正困难的是区分“卡住”和“思考/检查/等待/离开”。**

---

## 1. 项目背景与前因后果

### 1.1 出发点

现在很多编程学习系统已经能解释报错、给提示、甚至直接给代码。但有一个更靠前的问题被忽略了：**什么时候该主动提供帮助？**

学生“一段时间没按键”并不等于卡住，可能是：

- 读题；
- 想算法；
- 检查代码；
- 看运行/判题结果；
- 已经暂时离开。

如果系统只看“多久没按键”就弹窗，很容易把正常思考误判成卡住，造成打扰。

### 1.2 研究定位

本项目**不研究提示内容**，只研究**帮助时机**。并且把问题拆成三个层次：

- **Candidate（候选时刻）**：行为上可能存在帮助需求，值得进一步检查；
- **Confirmed（确认时刻）**：结合代码/上下文后判断提示可能有价值；
- **Shown（展示时刻）**：通过冷却、焦点、运行状态、剪贴板等保护策略后，真正展示给学生的时刻。

> 关键约束：**长 idle 可以成为 Candidate，但不能直接等于 Shown。**

### 1.3 为什么这套做法“不算简单规则”

论文真正的卖点不是“一个 idle 阈值”，而是：

1. 严格因果窗口（禁止未来信息泄漏）；
2. 多尺度行为特征（5/10/30/60/120 秒）；
3. 把“需要帮助”和“适合打扰”拆成两个维度；
4. 显式保留“不确定/跳过”类别；
5. 两阶段架构：高召回候选规则 + 上下文/LLM 抑制误报；
6. 从窗口级指标扩展到 session 级提示频率、冷却、成本。

### 1.4 时间线（由文件时间戳推断）

- `2026-05 ~ 07`：数据导出、清洗、早期规则探索（`export_filtered.py`、`filter_sessions.py`、`rf_classify.py`、`llm_judge.py` 等早期脚本）。
- `2026-07 ~ 08`：构建原型窗口、浏览器标注页面（`build_prototype.py`、`gen_label_page.py`）。
- `2026-08-24 ~ 08-27`：集中完成标签整理、规则消融、逻辑回归、随机森林、文献核对、汇报文档。
- 当前（`2026-09-07`）：请求把项目整理成完整交接文档（即本文件）。

---

## 2. 目录结构与文件清单

项目根目录：`D:\02_code\project\python\oj_demo`

**注意：本项目不是 git 仓库（`git log` 报 `not a git repository`）。所有版本管理依赖文件命名和“新增文件不覆盖旧文件”的约定。**

### 2.1 核心目录

| 路径 | 内容 |
|---|---|
| `data/export/` | 原始按键数据导出，`key_action_batch_001.csv` ~ `key_action_batch_116.csv`，共 116 个文件，约 6.63 GB |
| `data/analysis/` | 早期分析产物（如 `triggers.csv`） |
| `labeling/` | 核心工作目录：脚本 + `data/` 产物 + `sessions/` 标注页面 |
| `labeling/data/` | 清洗后的 session、窗口、标签、评估结果、报告 |
| `labeling/sessions/` | 浏览器标注页面（HTML） |
| `lit_pdf/` | 5 篇核心文献 PDF + txt 提取 + 综述笔记 |
| `resources/` | 归档目录：论文 PDF（papers/）、原始标签（original_labels/）、README 说明 |

### 2.2 根目录关键文件

| 文件 | 作用 |
|---|---|
| `export_filtered.py` | 从 MySQL 导出 key_action 到 `data/export/*.csv` |
| `filter_sessions.py` | 清洗生成 `labeling/data/clean_sessions.csv` |
| `tomorrow_report.md` / `tomorrow_report_revised.md` | 两版阶段汇报（修订版更完整、口径更严谨） |
| `report_expansion_sections.md` | 把“两阶段方案”讲完整、补充 RQ 和对比实验的扩展稿 |

### 2.3 `labeling/` 下关键脚本（按功能）

**数据构建：**

- `build_prototype.py`：核心。生成 `prototype_windows.csv`、空的 `prototype_labels.csv` 模板、`prototype_label.html` 标注页。默认 100 session × 5 窗口 = 500 窗口。
- `build_event_driven_windows.py`：生成事件驱动候选（462 条，其中 448 条 idle_30s、14 条 backspace_pause_2s）。
- `rebuild_windows.py` / `causal_eval.py`：因果窗口构建/检查相关。
- `build_replay.py`：代码近似回放。
- `global_feature_analysis.py`：全局特征分析。

**标注与标签整理：**

- `gen_label_page.py` / `gen_remaining_label_page.py`：生成标注页面。
- `merge_human_labels.py`：合并两批用户导出标签。
- `review_human_positive_labels.py` / `review_prototype_labels.py`：人工正例二次复核。
- `make_recall_candidate_labels.py`：**生成最终统一口径 `prototype_labels_recall_candidates.csv`（69/297/134）**。
- `human_label_audit.py`：标签一致性审计。

**评估：**

- `eval_rules.py` / `extended_ablation.py` / `small_paper_ablation.py`：规则消融。
- `candidate_logistic_regression.py`：逻辑回归（GroupKFold，OOF）。
- `rf_classify.py`：早期随机森林（**注意：旧版，用了未来/全量特征，不能作为正式结果**）。
- `llm_judge.py`：早期 LLM 判断（**注意：旧版 prompt 泄漏未来信息，不能直接复用**）。
- `two_stage_eval.py` / `window_cooldown.py` / `offline_prototype_eval.py`：两阶段/冷却/离线评估。
- `bootstrap_ci.py` / `prototype_rule_stability.py` / `filter_sensitivity.py`：稳定性与阈值敏感性。
- `sample_negatives.py` / `label.py`：负样本/早期标注辅助。
- `keys60_scan.py`：60 秒特征扫描。

### 2.4 与项目无关的遗留文件（不要误以为是本项目的一部分）

- `claw_data2/`：一大坨 `*_leads.csv`，是另一个“展会展商线索爬取”项目的数据，与本项目无关。
- `.vscode/1.py`、`.vscode/accounts.py`、`.vscode/claw.py`：同上，线索抓取相关，与本项目无关。
- `tmp.py`：一个 Tavily 搜索 API 测试脚本（里面硬编码了一个 Tavily key）。
- `061526-5359-01.dmp`：某个进程崩溃转储，与本项目无关。
- `data/扫描仪in-cosmetics_Korea_*.xlsx`：展商扫描数据，与本项目无关。

---

## 3. 数据来源与 Schema

### 3.1 原始数据库

- 主机：`122.207.108.6`
- 库：
  - `experiment_data`（端口 19106）：`key_action` 表（按键动作 JSON）。
  - `csuoj_db`（端口 53306）：`solution`、`source_code` 等表。
- 用户名/密码在脚本里硬编码（`root` / `vlab@csu.admin`），属于安全风险，后续应迁移到环境变量/配置。

### 3.2 原始按键数据 `data/export/key_action_batch_*.csv`

字段：

```
id, action, solution_id, start_time, problem_id, created_by, created_time
```

`action` 是 JSON 字符串，形如一个事件数组：

```json
[
  {"key": "e", "time": "2025/12/5 12:51:04:992", "type": "up", "row": 57, "column": 17},
  {"key": "Backspace", "time": "2025/12/5 12:51:05:849", "type": "up", "row": 57, "column": 17},
  {"key": "Shift", "time": "2025/12/5 12:51:06:692", "type": "down", "row": 57, "column": 17}
]
```

要点：

- 每个事件有 `key`、`time`（多种格式）、`type`（up/down）、`row`、`column`。
- 构建特征时只用 `type == down` 的事件（见 `build_prototype.py` 的 `load_events`）。
- 时间格式非常杂，`parse_time` 里有多个兜底格式（含“把末尾 `:毫秒` 转成 `.毫秒`”的处理）。

### 3.3 `labeling/data/clean_sessions.csv`

字段：`solution_id, problem_id, judge, has_code, duration_s, total_keys`

- 约 41,927 行（session）。
- 早期 `filter_sessions.py` 的过滤是：`duration <= 1800s`、`total_keys >= 10`、有判题、有代码。
- `build_prototype.py` 在此基础上再收紧为：`duration_s >= 60`、`total_keys >= 30`，且每个 solution 去重。
- 最终选中 **100 个 session**（seed=42）。

### 3.4 `labeling/data/prototype_windows.csv`（核心特征表）

- 500 行、100 个唯一 solution、77 列。
- 每条窗口有唯一 `window_id`（`{solution_id}-w{ordinal}`）、`solution_id`、`event_index`、`window_end_time`、`problem_id`、`judge`、`duration_s`、`total_keys`、`key_summary`、`code_replay`。
- 每条窗口包含 5/10/30/60/120 秒窗口下的特征（见第 5 节）。
- `submitted_code` 列通常为空（本地没有完整提交代码；`build_prototype.py` 会尝试从 DB 拉取，失败则为空）。

### 3.5 最终标签 `labeling/data/prototype_labels_recall_candidates.csv`

字段：`window_id, solution_id, event_index, window_end_time, label, source_batch`

500 行，分布：

| label | 含义 | 数量 |
|---:|---|---:|
| 1 | 候选（Candidate） | 69 |
| 0 | 非候选 | 297 |
| -1 | 不确定/跳过 | 134 |

> 这是当前**统一采用**的标签口径（见第 4 节）。

---

## 4. 数据流水线（端到端）

```text
MySQL: experiment_data.key_action + csuoj_db.solution/source_code
        │  export_filtered.py
        ▼
data/export/key_action_batch_001.csv ~ 116.csv   （约 6.63 GB）
        │  filter_sessions.py
        ▼
labeling/data/clean_sessions.csv                 （约 41,927 个 session）
        │  build_prototype.py（再过滤 + 采样 100 session × 5 窗口）
        ▼
labeling/data/prototype_windows.csv              （500 窗口 × 77 列）
        │  + prototype_labels.csv（空模板）
        │  + prototype_label.html（浏览器标注页）
        ▼
人工在浏览器标注 → 两批导出 CSV（在用户 Downloads 目录）
        │  merge_human_labels.py → prototype_labels_human_complete.csv
        │  review_human_positive_labels.py → prototype_labels_human_reviewed.csv
        │  make_recall_candidate_labels.py → prototype_labels_recall_candidates.csv（最终统一口径）
        ▼
评估脚本（eval_rules.py / candidate_logistic_regression.py / rf / llm 等）
```

### 4.1 窗口采样方式（重要，直接影响结论口径）

`build_prototype.py` 的 `main()`：

- 在每个 session 的 `[20% 时长, 90% 时长]` 区间内，用 `np.linspace` 取 **5 个等距时间点**作为窗口结束时间。
- 因此“每个 session 固定 5 个窗口”**不等于真实在线候选分布**。真实在线应该用事件驱动（每个 idle 周期一次候选），这也是后面 `build_event_driven_windows.py` 的动机。

### 4.2 严格因果约束

窗口结束时间记为 `t`。所有特征、代码回放、按键摘要**只使用 `event.time < t`** 的事件。`t` 之后的事件（后续按键、运行、提交、最终判题）一律不参与特征/标签。

> 特别注意：`prototype_windows.csv` 里的 `judge` 列很可能是**整个 solution 的最终判题结果**，而不是“窗口结束前最近一次已知判题”。如果标注者/模型看到了最终 `judge`，会造成后见之明泄漏。**正式实验必须核实这一点，新标注页只展示 `last_known_judge_before_t`。**

---

## 5. 标签体系与口径演进（本项目的关键脉络）

项目历史上出现过**多套标签**，混用时容易出错。按时间顺序梳理：

| 阶段 | 文件 | 分布 | 说明 |
|---|---|---|---|
| 早期子集 | `prototype_first100_review.csv` 等 | 前 100 条 AI 复核 | 探索性 |
| 用户第一批 | `C:\Users\10950\Downloads\prototype_labels.csv` | 235 条（确定 182，跳过 53） | 39 个 session，正例 61、负例 121 |
| 用户第二批 | `C:\Users\10950\Downloads\prototype_labels_remaining.csv` | 265 条 | 与第一批合并 |
| 完整人工 | `prototype_labels_human_complete.csv` | **90 / 290 / 120**（确定 380，84 session） | 合并两批，未改值 |
| 保守复核 | `prototype_labels_human_reviewed.csv` | **23 / 297 / 180**（确定 320） | 只复核原 1，67 条被改（7→0，60→-1） |
| **高召回候选（最终统一）** | `prototype_labels_recall_candidates.csv` | **69 / 297 / 134** | 把 46 条“长 idle 无近期证据”恢复为 1 |

### 5.1 为什么最终采用 69/297/134，而不是 23/297/180

- “23/297/180”是**保守口径**：只有“近期编辑后停顿”等强证据才算 1，长 idle 一律归 -1。
- 但用户明确目标偏向**高召回**（宁可多召回、交给第二阶段 LLM 判断），所以把 46 条“长 idle、无近期编辑证据”的窗口**恢复为候选 1**。
- 于是得到 69/297/134，作为**当前统一口径**。

### 5.2 这套标签“是什么 / 不是什么”

**是：** 面向“规则召回候选 + LLM 二次复核”的操作性候选标签。

**不是：**

- 不是学生真实心理状态的直接观测；
- 不是“已经证明学生需要帮助”；
- 不是最终弹窗 gold truth。

> 结论里有一条关键边界必须写清楚：**69 个正例里有 46 条是根据“长 idle”恢复的，而特征里又有 `current_idle_s` 等 idle 特征，所以“标签定义”和“特征”存在循环/同源性。** 得到的 Recall 只能解释为“复现了当前人工候选标签”，不能解释为“识别了真实帮助需求”。

### 5.3 标签质量问题（必须在论文里承认）

- 单人标注，缺少第二标注者和 Cohen's kappa。
- 完整人工标签下，84 个 session 里有 **38 个 session 的全部窗口被标成同一类别**（“整道题统一标注”偏差）。
- 早期 235 条子集里是 15/39 个 session 全同标签。
- 标注页若展示最终 `judge`，会引入后见之明。

---

## 6. 特征体系

每个窗口有 **61 个数值特征**（逻辑回归/随机森林统一使用）：

- `current_idle_s`：当前连续无输入时长。
- 对 5/10/30/60/120 秒窗口，每个尺度下：
  - `keys_{w}s`：总按键数；
  - `text_keys_{w}s`：文本键数；
  - `modifier_keys_{w}s`：修饰键数；
  - `clipboard_ops_{w}s`：剪贴板操作数（近似：C/V 附近 2 秒内有 Control/Meta）；
  - `pause_count_{w}s` / `pause_total_{w}s` / `pause_p90_{w}s`：停顿次数/总时长/P90；
  - `backspace_{w}s` / `enter_{w}s` / `control_{w}s`；
  - `row_changes_{w}s` / `column_changes_{w}s`：光标行列变化。

另外还有描述性字段：`activity_type_{w}s`（低活动/持续输入/修饰键占多数/剪贴板操作）、`key_summary`（按键压缩摘要）、`code_replay`（近似重建代码）。

**明确排除（不进入模型/规则）：**

- `event_index`、`total_keys`、完整 `duration_s`；
- `submitted_code`、最终 `judge`；
- 窗口结束后的任何事件。

> 原因：线上无法稳定获得总按键数/总时长，且这些字段要么泄漏未来，要么泄漏全局信息。

---

## 7. 关键实验结果

### 7.1 最终统一口径（69/297/134，确定 366 条，84 session）下的规则消融

数据：`prototype_windows.csv` + `prototype_labels_recall_candidates.csv`。
（见 `labeling/data/candidate_label_rule_comparison.md`）

| 规则 | 触发 | TN | FP | FN | TP | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| idle_ge30 | 99 | 254 | 43 | 13 | 56 | 56.6% | 81.2% | 66.7% |
| keys30_lt5 | 133 | 229 | 68 | 4 | 65 | 48.9% | 94.2% | 64.4% |
| **idle20_keys30_lt8_no_clip（主规则）** | 111 | 249 | 48 | 6 | 63 | **56.8%** | **91.3%** | **70.0%** |
| idle20_multiscale | 98 | 256 | 41 | 12 | 57 | 58.2% | 82.6% | 68.3% |
| multiscale_no_clip | 119 | 238 | 59 | 9 | 60 | 50.4% | 87.0% | 63.8% |
| idle20_low_text_row | 111 | 249 | 48 | 6 | 63 | 56.8% | 91.3% | 70.0% |

**主规则（手工基线）：**

```text
current_idle_s >= 20
&& keys_30s < 8
&& clipboard_ops_30s == 0
```

### 7.2 逻辑回归（GroupKFold，OOF，61 特征）

数据：同样 366 条确定窗口，按 `solution_id` 5 折 GroupKFold。
（见 `labeling/data/candidate_logistic_regression.md`）

| 阈值 | 触发 | TP | FP | FN | Precision | Recall | F1 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.30 | 143 | 69 | 74 | 0 | 48.3% | 100.0% | 65.1% |
| 0.40 | 131 | 66 | 65 | 3 | 50.4% | 95.7% | 66.0% |
| 0.50 | 121 | 64 | 57 | 5 | 52.9% | 92.8% | 67.4% |
| 0.60 | 107 | 60 | 47 | 9 | **56.1%** | **87.0%** | **68.2%** |

- ROC-AUC：90.9%；PR-AUC：54.3%。
- 模型：L2 逻辑回归，`C=0.5`，`class_weight=balanced`，标准化，中位数填补。

### 7.3 随机森林（本次新增，已完成复算，但脚本未落盘）

模型：

```python
RandomForestClassifier(
    n_estimators=500, max_depth=4, min_samples_leaf=5,
    max_features="sqrt", class_weight="balanced_subsample",
    random_state=42, n_jobs=-1,
)
```

同样 61 特征 + 按 solution_id 5 折 GroupKFold，OOF：

| 阈值 | 触发 | TP | FP | FN | Precision | Recall | F1 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.30 | 129 | 65 | 64 | 4 | 50.4% | 94.2% | 65.7% |
| 0.40 | 122 | 64 | 58 | 5 | 52.5% | 92.8% | 67.0% |
| 0.50 | 113 | 63 | 50 | 6 | 55.8% | 91.3% | 69.2% |
| 0.60 | 105 | 61 | 44 | 8 | **58.1%** | **88.4%** | **70.1%** |

- ROC-AUC：91.1%；PR-AUC：55.6%。

阈值 0.60 的五折 F1（说明稳定性）：

```text
Fold1 70.0%  Fold2 81.2%  Fold3 70.6%  Fold4 52.6%  Fold5 76.0%
```

特征组重要性（impurity importance，只能解释“模型用了什么”，不能解释因果）：

```text
keys 0.173 > text_keys 0.168 > pause_p90 0.143 >
column_changes 0.139 > current_idle 0.127 > pause_total 0.098
```

### 7.4 三种方法对比（阈值 0.60）

| 方法 | Precision | Recall | F1 |
|---|---:|---:|---:|
| 逻辑回归 0.60 | 56.1% | 87.0% | 68.2% |
| 随机森林 0.60 | 58.1% | 88.4% | 70.1% |
| 手工主规则 | 56.8% | 91.3% | 70.0% |

**结论：随机森林略优于逻辑回归，但没有明显超过手工规则（F1 只差 0.1 个百分点），且规则 Recall 更高。** 当前数据规模下，增加模型非线性没有带来实质收益。

### 7.5 AI 辅助标注（对照性结果，不能当主结果）

AI 批量判断 500 条：`-1=144, 0=338, 1=18`，非常保守。

在与用户标签都给出确定二分类的 163 条重叠上：

- 二分类一致率：73.6%；
- Cohen's kappa：0.242（扣除类别分布后一致性偏低）；
- AI 正例 Precision 84.6% / Recall 21.2% / F1 33.8%。

> 结论口径：AI 更像“极保守的高精度候选筛选器”，**不能当作人工真值替代品**。

### 7.6 事件驱动候选与冷却（面向在线设计）

`build_event_driven_windows.py` 生成 462 个候选（448 个 idle_30s + 14 个 backspace_pause_2s），涉及 93/100 个 session，中位每 session 4 个、最大 14 个。

冷却效果（`event_driven_cooldown_analysis.md`）：

| 冷却 | idle 候选数 | 每 session 平均 | 单 session 最大 |
|---:|---:|---:|---:|
| 无冷却 | 448 | 4.82 | 14 |
| 5 分钟 | 200 | 2.15 | 4 |
| 10 分钟 | 140 | 1.51 | 3 |
| 15 分钟 | 120 | 1.29 | 2 |

idle 候选后的自然恢复（非提示导致，只用于定义 outcome）：

- 30 秒内恢复输入：54.0%；
- 60 秒内：72.1%；
- 120 秒内：86.6%。

> 设计含义：不能把 30/60/120 秒窗口当成三次独立触发；线上应“每个 idle 周期最多一次 + session 冷却 10 分钟 + 最多 2 次展示”。

---

## 8. 方法论要点（论文怎么写才站得住）

1. **监督验证必须按 `solution_id` 分组**（GroupKFold），不能随机拆窗口，否则同一 session 的窗口会泄漏到训练和测试。
2. **阈值不能在同一批结果上挑最高分后宣称泛化**，应在独立验证集或嵌套交叉验证中确定。
3. **只报 Pre/Rec/F1 不够**，还要报：PR-AUC、折间稳定性、每 session 候选/误提示次数、LLM 调用率、延迟、成本。
4. **“需要帮助”和“适合打扰”分开**，LLM/系统输出应是 `show / delay / suppress`，而不是简单 YES/NO。
5. **漏报不能靠第二阶段 LLM 解决**（LLM 看不到规则没召回的窗口）。需要：规则并集 + 未触发窗口低比例抽检 + 主动补充标注 + 迭代。
6. **`judge_pending` 必须单独抑制**，否则网络/判题延迟会被误判成学习困难。

---

## 9. 两阶段方法设计（当前推荐架构）

```text
所有实时事件
  → 高召回规则/轻量模型生成 Candidate
  → 确定性保护过滤（正在输入/判题等待/失焦/冷却/剪贴板）
  → LLM 或轻量模型判断：struggling / thinking / checking / waiting / away / uncertain
  → show（展示低打扰帮助邀请）/ delay（延迟观察）/ suppress（静默）
  → 记录点击/关闭/稍后/继续输入/运行/提交/判题
  → 回流数据更新规则与标签
```

LLM 输出建议（固定 JSON）：

```json
{
  "state": "struggling|thinking_or_reading|checking|waiting|active_editing|away_or_unknown",
  "interruptibility": "appropriate|inappropriate|uncertain",
  "decision": "show|delay|suppress",
  "confidence": 0.0,
  "evidence": ["最多三条来自输入的证据"],
  "missing_information": ["影响判断但缺失的信息"]
}
```

候选规则建议用多种事件的**并集**：

1. 长停顿：`idle >= 30s && keys_30s < 5`；
2. 失败后停滞：最近判题 WA/CE/TLE/MLE，编辑后再次停顿；
3. 近期编辑后暂停：`10s <= idle < 30s && text_keys_30s >= 1`；
4. 反复修改/运行且无推进；
5. 异常行为：连续退格、光标来回、行列变化大但文本增长少。

保护规则（确定性，不交给 LLM）：

- `judge_pending` / `editor 失焦` / `cooldown` / 同一 idle 周期已提示 → 直接 suppress；
- 每 session 最多 1–2 次、冷却 5–10 分钟；
- 提示文案用非阻塞小卡片：`[查看提示] [继续编写] [稍后再说]`。

上线顺序：**Shadow mode → 内部灰度 → 小规模 A/B（含 holdout）**。

---

## 10. 文献支撑（已核对的 5 篇核心 + 传统模型先例）

### 10.1 五篇核心论文（`lit_pdf/`，均来自正文级提取）

| 论文 | 做法 | 数据/样本 | 对本文的启发 |
|---|---|---|---|
| Dong et al. (2021) | SourceCheck 代码进展 + 时间阈值判断挣扎时刻 | Squiral 45 / GG 59 trace；3 位 TA 级专家评 20% 样本；Fleiss' kappa 0.539~0.853 | 用“进展速度”而非纯 idle 判断挣扎；窗口只看当前时刻以前 |
| Tabarsi et al. (2022) | 7 个规则 detector + 学生自报告对照 | 45 名非 CS 学生，19 条匹配 trace | Overly Idle（5 分钟）只是候选之一；长 idle ≠ 一定需要帮助 |
| Schwartz et al. (2025) | PTM 深度学习 vs DKT/SAKT/Code-DKT | CodeWorkout 630 学生 / FalconCode 1330 学生 | 预测“整名学生在任务上是否挣扎”，不等于窗口级帮助时机 |
| Pu et al. (2025) | 6 类启发式触发 + LLM 上下文响应 | 18 名高年级 CS，54 任务，1004 episode，398 次干预 | 30s idle 触发效果差（约一半被忽略）；多行修改/注释/执行触发更好 |
| Koutcheme et al. (2024) | GPT-4-as-judge 评反馈质量 | 150 条请求，1 专家参考，kappa 0.22~0.48 | LLM 不能单独当 ground truth |

### 10.2 逻辑回归 / 随机森林 / XGBoost 的先例（用于回答“以前有没有人做过”）

| 论文 | 模型 | 数据量 | 任务（与本文不同） |
|---|---|---|---|
| Bergin & Reilly (2006) | 逻辑回归 | 收集 123 人，102 完整样本 | 预测入门编程表现强/弱 |
| Pereira et al. (2020) | RF 基线 + 深度学习 | 2058 学生，6 学期，535,619 提交 | 前两周预测最终通过/失败 |
| Pereira et al. (2021, IEEE Access) | XGBoost + RF + DL | 约 2058 学生 CodeBench 行为 | 可解释预测学生最终表现 |
| Hoq et al. (2023, EDM) | XGBoost/KNN/SVM/Stacking | 772 学生，两学期，每学期 50 作业 | 预测期末成绩 |

**关键判断：**

- 传统模型（LR/RF/XGBoost）在“编程教育成绩预测”里有大量先例，但**“窗口级帮助时机”研究多用规则、代码 trace 进展、或规则+LLM**，传统模型很少直接用于这个细粒度任务。
- 因此本文**不能把“用了随机森林”当创新点**。创新应放在：严格因果多尺度窗口、帮助需求与可打扰性拆分、两阶段高召回候选+LLM 误报抑制、以及 session 级/在线代价评估。

### 10.3 相关文献清单文件

- `lit_pdf/five_papers_extraction.md`：5 篇正文级字段提取（标签/标注者/样本/划分/指标/局限）。
- `lit_pdf/literature_evidence_for_report.md`：汇报用的证据速览。
- `labeling/data/literature_references.md`：设计原则文献（Horvitz、Iqbal & Bailey、VanLehn、Wood/Bruner/Ross 等）。
- `labeling/data/literature_informed_intervention_design.md`：由文献推导出的状态机与 A/B 设计。

---

## 11. 已知问题与风险（务必不要踩）

1. **标签-特征循环**：69 正例中 46 条因“长 idle”恢复为 1，而特征含 `current_idle_s`，所以 Recall 高可能只是“模型复现了标注规则”。
2. **单标注者 + 整题统一标注偏差**：84 session 中 38 个全同标签；缺 Cohen's kappa。
3. **窗口抽样不代表在线分布**：固定 5 窗口/session，真实在线应事件驱动。
4. **`judge` 字段可能是最终结果**，若给标注者/模型看到会泄漏未来。
5. **`code_replay` 是近似重建**，Shift 组合、粘贴、复杂编辑器操作会导致字符错乱/不完整，不能当作真实源码。
6. **84 个独立 session 太少**，随机森林折间 F1 从 52.6% 到 81.2%，稳定性不足。
7. **早期 `llm_judge.py` 泄漏未来信息**（用了 after 按键、submitted_code、最终 judge、total_keys/duration），不能直接复用。
8. **早期 `rf_classify.py` 也泄漏未来**（用了 `keys_10s_after/keys_30s_after`、`code_at_trigger` 之前的 after 信息），只能当历史脚本，不能当正式结果。
9. **硬编码密钥/密码**：`llm_judge.py`（API key）、`tmp.py`（Tavily key）、`export_filtered.py`/`filter_sessions.py`/`build_prototype.py`（DB 账号密码）。后续必须迁移到环境变量，且不要提交到公开仓库。
10. **不是 git 仓库**：没有版本控制，改文件要“另存新文件 + 记录 old/new”，避免覆盖原始标签和用户导出文件。
11. **离线指标 ≠ 学习效果**：所有 Pre/Rec/F1 只说明“检测器与人工判断一致”，不证明提示提高了 AC 率或学习效果。
12. **XGBoost 未安装**：本机 `import xgboost` 会失败；未经用户同意不要安装。
13. **原始用户标签**：两份源头文件已归档到 `resources/original_labels/`（`prototype_labels.csv` 第一批、`prototype_labels_remaining.csv` 第二批）。原 Downloads 副本仍在 `C:\Users\10950\Downloads\`，但归档副本为只读可追溯源头；复核时另存审计文件，不覆盖归档。

---

## 12. 未来方向

### 12.1 小论文补全（短期，把当前离线做成“完整闭环”）

1. 修正标签体系：增加 `observed_state`（struggling/thinking/checking/waiting/away/unknown）和 `confidence`。
2. 第二名标注者独立标注，算 Cohen's kappa 并仲裁。
3. 抽查规则未触发的窗口，估计第一阶段漏报率。
4. 完整 session 回放：加冷却/首次触发保护/同一 idle 只一次，报告每 session 候选数、误提示数、每 10 分钟触发数。
5. 真正跑通“规则+LLM 复核”，补一张：第一阶段候选 / 最终保留 / Precision / Recall / F1 / 每 session 提示 / LLM 调用率 的对比表。
6. 把 XGBoost 作为补充基线（安装需先征得同意），但仍按 solution_id GroupKFold。
7. 把 `judge` 对齐到“窗口前最近一次已知结果”，消除后见之明。

### 12.2 在线验证（中期，把“检测”升级为“是否真有用”）

- **Shadow mode**：规则触发但不展示，只记录候选频率和后续行为。
- **非阻塞提示**：`[查看提示] [继续编写] [稍后再说]`。
- **“我需要帮助”按钮**：发现规则漏报。
- **随机 holdout**：候选点随机分“展示 / 暂不展示”，比较恢复有效编辑时间、运行/提交时间、错误是否减少。
- 记录两类在线标签：**时机标签**（need_now/delay/not_needed/unknown）与**内容标签**（helpful/partly_helpful/unhelpful/not_rated），不要混成一个三分类。

### 12.3 大论文扩展（长期，从“原型”到“完整主动帮助系统”）

主线：**“候选识别 → 误打扰控制 → 在线干预验证 → 反馈迭代”**。

- 工作一：离线候选识别（即当前小论文主体）。
- 工作二：上下文感知误打扰抑制（接入代码状态、运行/提交历史、页面焦点、编辑器状态，LLM/轻量模型区分卡住/思考/检查/等待/离开）。
- 工作三：在线主动帮助系统 + 用户研究（随机对照 + 主观反馈 + 行为结果）。
- 可选工作四：个性化（按学生历史接受率/拒绝率/主动求助调整阈值与冷却）。

建议的四个 RQ：

- RQ1 候选识别：多尺度行为 + 代码进展 + 运行提交上下文能否提升候选召回？
- RQ2 误打扰控制：LLM 二次判断能否区分状态、减少误提示？
- RQ3 系统代价：两阶段能否降低每 session 误提示、LLM 调用、延迟、成本？
- RQ4 在线效果（需在线实验）：提示是否缩短恢复有效编程时间，且不显著增加主观打扰？

---

## 13. 给下一个 AI 的操作建议

**优先做（收益最高）：**

1. 先读 `PROJECT_HANDBOOK.md`（本文件）和 `labeling/data/small_paper_completion_plan.md`。
2. 用 `candidate_logistic_regression.py` 作为模板，补写 `candidate_random_forest.py`（参数和结果见第 7.3 节，当前只完成复算、脚本未落盘）。
3. 写一个“规则+LLM 复核”的离线评估脚本，替换掉会泄漏未来的 `llm_judge.py`。
4. 写“完整 session 回放 + 冷却”脚本，补 session 级指标。
5. 抽检规则未触发窗口，做漏报分析。

**不要做（会引入错误/风险）：**

- 不要覆盖 `prototype_labels_recall_candidates.csv`、`prototype_labels_human_complete.csv`、`prototype_labels_human_reviewed.csv`、用户 Downloads 里的两份原始标签。
- 不要为了“结果好看”改标签值。
- 不要把旧 `rf_classify.py` / `llm_judge.py` 的结果写进论文。
- 不要随机拆窗口做交叉验证（必须按 solution_id 分组）。
- 不要未经同意安装 xgboost 或对外调用付费 API。

---

## 14. 运行环境

- 系统：Windows，Shell 为 PowerShell。
- Python：`3.13.5`，解释器路径 `D:\02_code\anaconda3\python.exe`。
- 关键包：
  - `pandas`（有 `numexpr 2.10.1 < 2.10.2` 的兼容性警告，不影响运行）；
  - `scikit-learn 1.6.1`；
  - `numpy`；
  - `pymysql`（数据导出/清洗用）；
  - `openai`（早期 `llm_judge.py` 用）；
  - **`xgboost` 未安装**。
- IDE 配置：`.vscode/settings.json` 用 conda 环境。
- 无 git 仓库。

---

## 15. 关键文件快速索引

| 想找什么 | 看哪里 |
|---|---|
| 最终统一标签 | `labeling/data/prototype_labels_recall_candidates.csv`（69/297/134） |
| 窗口特征表 | `labeling/data/prototype_windows.csv`（500×77） |
| 规则消融（统一口径） | `labeling/data/candidate_label_rule_comparison.md` |
| 逻辑回归结果 | `labeling/data/candidate_logistic_regression.md` |
| 完整人工标签评估 | `labeling/data/prototype_complete_human_eval.md` |
| 保守复核标签评估 | `labeling/data/prototype_reviewed_eval.md` |
| 高召回候选标签说明 | `labeling/data/prototype_recall_candidate_report.md` |
| AI 标签一致性 | `labeling/data/ai_label_validation.md` |
| 规则稳定性/CI | `labeling/data/prototype_rule_stability.md` |
| 事件驱动冷却 | `labeling/data/event_driven_cooldown_analysis.md` |
| 小论文补全计划 | `labeling/data/small_paper_completion_plan.md` |
| 两阶段规格 | `labeling/rule_llm_two_stage_spec.md` |
| 文献证据 | `lit_pdf/literature_evidence_for_report.md`、`lit_pdf/five_papers_extraction.md` |
| 汇报稿（修订版） | `tomorrow_report_revised.md` |
| 大论文扩展思路 | `report_expansion_sections.md` |

---

## 16. 一句话给下一个接手人

> 这个项目已经完成了“从原始按键数据到严格因果窗口、人工候选标签、规则/逻辑回归/随机森林离线评估”的闭环，当前最有价值的结论是：**复杂模型没明显超过可解释规则，真正的瓶颈是帮助需求的定义、运行/提交/代码上下文，以及用在线反馈验证“提示是否真的有用”**。下一步请优先补“随机森林脚本落盘 + 规则+LLM 两阶段离线评估 + 完整 session 回放/漏报抽检”，而不是继续堆更复杂的分类器。

