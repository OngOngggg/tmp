# 阈值与参数治理方案

## 核心原则

本项目不把 `30s` 当作学生“已经卡住”的真值边界。它只能是一个可复现的工程候选值。任何参数必须回答四个问题：

1. 它控制的是识别、决策、运营，还是事后评价？
2. 它的初始范围来自哪里？
3. 它在什么数据切分上被选择？
4. 如果相邻值表现相同，论文如何避免伪装出“精确最优值”？

## 参数来源表

| 参数 | 当前工程值/范围 | 参数含义 | 初始依据 | 本项目的确定方法 | 不能声称 |
|---|---:|---|---|---|---|
| `idle_candidate_s` | 5--120s；含 27/30/33s | 何时产生候选，不等于立即提示 | Pu et al. (2025) 把 30s 作为一种 idle heuristic；Dong et al. (2021) 则按“显著进展所需时间”的分布确定时间阈值 | 按 `solution_id` 分组的开发/测试切分；在开发集按帮助召回、误提示率和提示预算选取；测试集只报告 | 30s 是跨任务最优值，或 idle 就是 Need |
| `keys_30s_limit` | 1--30 | 低活动辅助条件 | 没有通用的跨平台常数；按键量只是低活动代理 | 与 idle 分开扫描；报告标签口径和预算敏感性 | 少于 5/8 个按键就是卡住 |
| `activity_context_s` | 30s（现有字段） | 统计触发点之前的行为证据 | 工程上与当前规则和已有窗口字段保持一致 | 另做 10/30/60/120s 消融；不得因方便而固定成理论常数 | 30s 是认知窗口或最佳观察长度 |
| `cooldown_s` | 0/60/300/600/900/1200s | 控制提示频率和用户负担 | 运营约束，不是心理学阈值 | 以候选数/session、P95 候选数和在线打扰预算确定；当前 600s 约 1.50 候选/session | 10 分钟代表学生恢复期 |
| `recovery_horizon_s` | 30/60/120s | 观察触发后的自然行为 | 结果观察窗口；不能回写触发时刻标签 | 用恢复/运行/提交 hazard 曲线和删失分析选择报告窗口 | 120s 内恢复是提示造成的 |
| `min_recovery_events` | 1/3/5/10 | 把“继续活动”操作化为事件数 | 操作定义，当前 3 只是中间候选 | 敏感性分析；同时报告事件类型、删失和离开 | 三个事件等于真正解决问题 |
| `previous_submission_safe_window` | 5/10/15min | 结果可见性的保守代理 | 数据没有明确返回时间时的时间安全窗 | 与判题/运行日志核对；无法核对则字段名保留 `previous_submission_result` | 上一次提交结果必然已被学生看到 |
| `model_show_threshold` | 不预设 0.5 | 模型输出转为展示/延迟/抑制的策略点 | 0.5 只是分类习惯，不是交互目标 | 在开发集按 utility、校准和提示预算选择；独立测试报告 | 概率 0.5 具有心理学含义 |

## 文献如何使用

- Dong et al. (2021) 的启发不是复制某个秒数，而是先定义显著进展，再用数据分布确定“完成进展所需时间”的分位数。因此本项目优先采用分位数、风险曲线和任务/用户分层，而不是照搬 30s。
- Tabarsi et al. (2022) 使用 5 分钟 `Overly Idle` 作为多个 detector 之一，说明长 idle 也只是候选信号，不能解释为唯一的困难标签。
- Pu et al. (2025) 使用 30s idle 作为主动触发 heuristic，但其结果显示 idle 触发容易被忽略。因此该值可作为复现实验基线，不能作为本项目的理论证明。
- Horvitz (1999) 与 Iqbal and Bailey (2008) 支持把时机看成中断成本与任务上下文的权衡；它们不提供本项目的秒数。

## 选择协议

### 开发/测试隔离

按 `solution_id` 分组切分，避免同一 session 的窗口同时出现在选择和评估中。未知标签 `-1` 不参与监督评分，但必须报告其数量；标签版本分别分析，不能挑一个最有利版本作为唯一真值。

### 选择目标

不单独最大化 F1。至少同时报告：

```text
Recall(Need)
False-prompt rate
Prompts/session
P95 prompts/session
Calibration / abstention
```

一个可解释的初始效用是：

```text
utility = recall - false_prompt_rate
```

论文正式实验应再做不同中断成本 `lambda` 的敏感性分析，并把提示预算作为约束，而不是事后挑一个漂亮分数。

### 稳定性判据

如果 27/30/33s 的测试集差异落在 session bootstrap 置信区间内，报告“稳定区间”而不是“30s 最优”。如果不同标签口径选出不同阈值，报告标签依赖，并优先采用跨口径、低打扰且具有运营可行性的参数。

### 当前可复现实验

```powershell
& "D:\02_code\anaconda3\python.exe" labeling/threshold_selection.py --max-prompt-rate 0.20
```

输出：

- `labeling/data/offline_research/threshold_sweep.csv`
- `labeling/data/offline_research/threshold_selection.json`
- `labeling/data/offline_research/cooldown_sweep.csv`
- `labeling/data/offline_research/threshold_selection_report.md`

## 论文中对 30 秒的正式表述

> 30 秒最初作为工程候选阈值，并参考主动式编程辅助研究中的 idle heuristic。由于既有研究并未证明其为普适最优值，本文将 idle 时间视为待估计的策略参数，在包含 27、30、33 秒等邻近值的候选集合中，使用按 session 分组的开发/测试协议、帮助召回、误打扰成本和提示预算联合选择。若邻近阈值表现不可区分，则不宣称存在精确最优点，而报告稳定区间及其运营折中。

