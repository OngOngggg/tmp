# 离线研究优先方案

## 1. 当前阶段的研究边界

现阶段只回答三个问题：

1. 在严格因果窗口内，哪些历史行为信号与人工帮助候选标签稳定相关？
2. 这些关系在不同标签口径、不同 session 和不同特征集合下是否稳定？
3. 事件驱动候选、冷却和自然恢复的真实运营代价是多少？

现阶段不声称学生心理状态已被直接识别，也不声称提示造成了恢复、AC 或学习收益。

## 2. 已完成的离线审计

脚本：`labeling/offline_research_eval.py`

输出目录：`labeling/data/offline_research/`

- `model_comparison.csv`：三套标签、规则和分组 OOF 逻辑回归的统一比较；
- `selective_prediction.csv`：置信度阈值、覆盖率和 abstention；
- `label_audit.json`：session 同质标签审计；
- `candidate_cooldown.csv`：全量事件候选的冷却负载；
- `candidate_outcome_audit.json`：自然恢复和删失摘要；
- `offline_research_report.md`：自动生成的研究口径报告。

### 2.1 关键观察

- 最终高召回标签（69/297）上，主规则 F1 约 0.70，按 session bootstrap 的 95% 区间约为 0.63–0.76；
- 保守复核标签（23/297）上，主规则 F1 约 0.39，说明标签口径会显著改变结论；
- 完整人工标签（90/290）上，主规则 F1 约 0.70；
- 三套标签的 session 全同标签比例约为 45%–76%，窗口并非独立样本；
- 去除 `current_idle_s` 和 `pause_*` 后，LR 仍有一定排序能力，但 F1、PR-AUC 和校准下降，表明模型既利用停顿信号，也受到停顿定义影响；
- 复杂模型暂时没有超过可解释规则的明确证据，不能把“换 RF/Transformer”作为创新点；
- 全量事件候选 172,622 条覆盖 37,462 个 session，10 分钟冷却后约 56,153 条，平均每 session 1.50 条；
- 事件候选后的自然恢复率约为 30 秒 35.0%、60 秒 53.2%、120 秒 70.5%。这些是观察性 Outcome，不是提示效果。

## 3. 论文中的离线主张

### 可以主张

- 严格因果、事件驱动的候选构造流程是可复现的；
- 多尺度行为特征对当前操作性标签具有一定区分能力；
- 简单规则在当前标签上具有可解释的高召回基线；
- 冷却机制可以把候选频率控制在可运营范围；
- 低置信度 abstention 能把自动决策限制在更可靠的样本上。

### 暂时不能主张

- `Need` 是学生真实心理需求；
- `idle` 等于卡住；
- 下一次输入或 AC 是提示造成的；
- 当前标签可以作为唯一 gold truth；
- AI 已经替代传统 Navigator；
- 离线分数足以证明线上提示值得展示。

## 4. 下一批离线实验

### 实验 A：标签去循环

构造三类标签：最终高召回、保守人工复核、完整人工。对每类标签分别比较：

- full：全部窗口前数值行为特征；
- no-idle-pause：删除 `current_idle_s` 和 `pause_*`；
- minimal：只保留 `current_idle_s`、`keys_30s`、`clipboard_ops_30s`。

主要指标：session 分组 PR-AUC、Brier、ECE、F1 及 session bootstrap 区间。

停止标准：如果去循环后只剩下接近多数类的性能，论文必须把结果降级为“候选规则复现”，不能写成状态识别。

### 实验 B：候选集外漏报审计

从每个 session 抽取：

- 规则命中候选；
- 规则未命中的正常输入窗口；
- 提交后等待窗口；
- 运行/判题附近窗口；
- 长 idle 但最终没有明显困难证据的窗口。

至少两名标注者只看触发时刻之前的信息，独立标注 `Need`、`Interruptibility` 和 `unknown`。候选集外样本必须单独报告，不能与规则命中样本混合计算一个漂亮的 F1。

### 实验 C：用户/任务/时间泛化

依次使用：

- solution/session 分组；
- 用户分组；
- 时间前段训练、后段测试；
- 题目分组或留一题测试（可行时）。

如果只在 session 内 OOF 有效，而跨用户或跨时间明显下降，结论应改为“个体/批次内可用”，不能写成普适模型。

### 实验 D：选择性预测与运营代价

对模型输出使用 confidence threshold：低置信度样本 abstain。报告：

- coverage；
- abstention rate；
- retained accuracy；
- 正例召回；
- 每 session 触发次数；
- 每 session 误触发次数。

线上策略默认宁可 abstain，不把不确定窗口强制转成 `show`。

### 实验 E：Outcome 风险基线

在不把未来变量用于触发的前提下，单独拟合 30/60/120 秒恢复风险、下一次运行风险和下一次提交风险。该实验只用于描述自然过程，不能替代随机对照。

## 5. 技术路线的收缩

当前不直接上 POMDP 或大型 Transformer。推荐顺序：

1. 标签和候选集外标注；
2. 规则、LR、校准和 abstention；
3. HSMM 或离散 hazard 作为机制验证；
4. 只有当 duration/context 消融带来跨用户稳定增益时，才加入更复杂的时序模型；
5. Shadow mode 后再做候选级随机对照。

这使“技术深度”来自可识别性、持续时间、不确定性和风险约束，而不是模型数量。

## 6. 当前最重要的下一步

1. 统一论文只引用 `offline_research` 的新结果，清楚标注旧报告的历史标签口径；
2. 完成候选集外双人标注；
3. 修正并验证 `previous_submission_result` 的可见时间代理；
4. 把 `Need`、`Interruptibility` 和 `Outcome` 作为三个独立 estimand；
5. 只有完成以上步骤，才进入 HSMM 和在线策略实验。

## 7. 阈值选择与参数治理

`30s` 不再作为默认真理。参数的定义、文献依据、选择协议和论文表述统一见 [`THRESHOLD_GOVERNANCE.md`](THRESHOLD_GOVERNANCE.md)。当前可复现实验入口为：

```powershell
& "D:\02_code\anaconda3\python.exe" labeling/threshold_selection.py --max-prompt-rate 0.20
```

该实验按 `solution_id` 分组选择 idle 和低活动阈值，在留出集报告 27/30/33 秒的近邻稳定性，并统计冷却对候选负载的影响。它仍然只支持“与操作性标签的一致程度”和“自然候选代价”的主张，不支持提示因果效果。
