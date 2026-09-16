# Offline research audit

本报告统一重算三套标签版本，避免旧报告与最终标签口径混用。所有模型使用按 solution_id 分组的 5 折 OOF；模型特征只取窗口前可见的数值行为特征。

## 标签与 session 审计

| label version | sessions | homogeneous sessions | homogeneous rate | median windows/session |
|---|---:|---:|---:|---:|
| recall_candidates | 84 | 43 | 51.2% | 5.0 |
| human_reviewed | 83 | 63 | 75.9% | 4.0 |
| human_complete | 84 | 38 | 45.2% | 5.0 |

## 解释

- `full` 包含当前多尺度行为特征；`no_idle_pause` 去除 `current_idle_s` 和所有 `pause_*`，用于检查标签与停顿信号的循环；`minimal` 只保留当前基线所需的三个特征。
- `rule` 是 `idle>=20 && keys_30s<8 && clipboard_ops_30s==0`，只作为可解释基线。
- `f1_ci_low/high` 是按 session 重采样的 95% 区间；它反映 session 聚类不确定性，不是独立窗口置信区间。
- 模型分数表示与当前人工操作性标签的一致程度，不表示识别了学生真实心理状态，也不表示提示有效。

## 主要结果

完整数值见 `model_comparison.csv`。重点查看：同一 label version 下 `full` 与 `no_idle_pause` 的差异，以及三套 label version 间结果是否稳定。若去除 idle/pause 后性能大幅下降，说明当前标签强依赖停顿定义，不能把高分解释成独立状态识别。

## 选择性预测

`selective_prediction.csv` 给出逻辑回归在不同置信度下的覆盖率、拒答率和正例召回。在线系统应允许低置信度样本 abstain，而不是强制二分类。

## 使用边界

1. 不能用这些离线结果声称主动提示改善 AC、学习成绩或挫败感。
2. `human_complete`、`human_reviewed` 和 `recall_candidates` 是不同操作性标签，不能挑选分数最高的一套作为唯一真值。
3. 候选外漏报仍未被人工充分标注；下一步应按 session 抽样标注正常输入、等待判题、失焦/离开和候选未命中窗口。

## 全量事件驱动候选审计

全量候选 172,622 条，覆盖 37,462 个 session；其中 169 条的 `trigger_time` 无法解析，冷却统计只使用可解析时间。按‘触发后 120 秒内至少 3 个非修饰/非导航事件’定义的自然活动恢复率为 30 秒 35.0%、60 秒 53.2%、120 秒 70.5%。其中 0.0% 的候选在 120 秒内无后续事件，属于删失/离开混合情形，不能简单当作失败。

冷却结果见 `candidate_cooldown.csv`。这些结果只描述真实候选负载和自然后果，不代表展示提示后的因果效果。
