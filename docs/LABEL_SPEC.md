# Need / Interruptibility / Outcome 标注规范 v1

本规范固定窗口级任务的定义、字段和标注规则。三者不是一个三分类标签：

```text
Need             当前是否存在帮助需求证据
Interruptibility 当前是否适合打扰
Outcome          触发之后实际发生了什么
```

## 1. 分析单位

一条样本是一个事件驱动候选点：

```text
candidate = (created_by, problem_id, solution_id, trigger_time)
```

`trigger_time` 是系统假设做决策的时刻。所有触发特征必须满足：

```text
event_time < trigger_time
```

同一连续 idle gap 只保留一个 `idle_30s` 候选；同一候选点可以同时拥有 Need、Interruptibility 和 Outcome 字段，但三者来源不同。

## 2. Need：帮助需求证据

### 正式定义

`Need` 不声称直接观测学生的心理状态。它表示：

> 仅根据 `trigger_time` 之前已经可见的行为，是否有足够证据认为帮助内容可能与当前编程进展相关。

标签取值：

| 值 | 含义 |
|---|---|
| `1` | 有帮助需求证据，值得进入确认阶段 |
| `0` | 当前证据更支持正常活动、等待、检查或没有需求 |
| `-1` | 信息不足或无法区分，跳过 |

### 标注为 `1` 的证据

满足以下一项或多项，且没有明显反证：

- 近期反复修改、退格或局部修正，进展明显停滞；
- 多次提交/尝试后仍未解决，且当前仍处于任务过程；
- 长时间低活动与此前持续编辑或调试形成明显反差；
- 行为显示可能在同一局部问题上循环，而不是一次性离开。

### 不应标为 `1` 的情况

- 只是刚提交或等待判题；
- 最近仍有连续有效编辑；
- 明显是检查输出、读题或思考，且没有困难证据；
- 长时间没有动作，但没有任何可识别的任务上下文；
- 仅因为最终结果是 WA/CE/RE 就判定需要帮助。

## 3. Interruptibility：可打扰性

### 正式定义

`Interruptibility` 表示：

> 在 `trigger_time` 发送帮助是否可能造成不必要的打断。

它不是“学生是否需要帮助”的同义词，而是对当前干预时机的判断。

标签取值：

| 值 | 含义 |
|---|---|
| `show_now` | 当前适合进入展示决策 |
| `delay` | 可能需要帮助，但应等待或观察 |
| `suppress` | 当前不应打扰 |
| `-1` | 信息不足，无法判断 |

### `show_now` 的条件

- 没有刚提交、运行或等待判题的迹象；
- 没有处于冷却期；
- 没有刚恢复连续输入；
- 当前停顿与困难证据相符；
- 没有明显的检查、阅读、粘贴或离开证据。

### `delay` 的条件

- `Need=1`，但刚提交、可能在等待结果；
- 当前上下文不足以区分思考和卡住；
- 有长 idle，但没有足够困难证据；
- 候选刚被触发，尚未满足冷却或观察窗口。

### `suppress` 的条件

- 仍在连续编辑；
- 明显正在检查、等待、复制粘贴或离开；
- 处于冷却期；
- 当前候选主要由噪声或异常事件造成。

如果焦点、运行状态和真实剪贴板事件在数据库中缺失，字段必须注明这是：

```text
interruptibility_proxy
```

不能声称是直接观测的真实可打扰性。

## 4. Outcome：未来结果

`Outcome` 不由人工主观判断，而由触发点之后的日志自动计算。它不能作为触发特征。

### 推荐字段

| 字段 | 定义 |
|---|---|
| `outcome_next_event_s` | 触发后的下一事件时间 |
| `outcome_keys_30s` | 触发后 30 秒内事件数 |
| `outcome_text_keys_120s` | 触发后 120 秒内文本键数 |
| `outcome_recovered_30s` | 30 秒内是否恢复有效输入 |
| `outcome_recovered_120s` | 120 秒内是否恢复有效输入 |
| `outcome_next_submit_s` | 距离下一次提交的时间 |
| `outcome_next_submit_result` | 下一次提交的结果 |
| `outcome_ac_within_1h` | 1 小时内是否出现 AC |
| `pair_long_term_outcome` | 用户-题目级长期结果 |

初始的“有效恢复输入”定义为触发后时间窗口内出现至少 3 个非修饰、非导航键；该阈值是可调分析参数，必须在实验中固定后再评估，不能按测试结果临时修改。

如果触发点位于 session 末尾，未来窗口不可观测，应记为缺失/删失，而不是自动记为 `0`。

## 5. 数据字段规范

### 身份和时间

```text
candidate_id
solution_id
created_by
problem_id
candidate_type
trigger_time
```

### 因果特征

```text
current_idle_s
keys_5s / keys_10s / keys_30s / keys_60s / keys_120s
text_keys_*
pause_count_*
pause_total_*
backspace_*
enter_*
clipboard_ops_*
prior_submit_count
previous_submission_result
previous_submission_time
previous_submission_age_s
```

如果采用 10 分钟安全窗口，使用明确命名：

```text
previous_submission_result_safe_10m
```

不要把它直接叫 `last_known_judge_before`，除非有真实判题完成/可见时间。

### 人工标签

```text
need_label
interruptibility_label
need_reason
interruptibility_reason
annotator_id
annotation_version
annotation_confidence
annotation_uncertain_reason
```

### 评价字段

所有未来字段统一使用 `outcome_` 或 `pair_` 前缀：

```text
outcome_*
pair_long_term_outcome
next_submit_*
ac_within_*
```

这些字段禁止进入在线触发模型。

## 6. 标注流程

### 第一阶段：因果标注

标注者只能看到：

- `trigger_time` 之前的按键特征；
- 近似代码回放；
- 已满足安全时间条件的历史提交结果；
- 题目和语言等非未来信息。

必须隐藏：

- 当前 solution 的最终结果；
- 后续按键；
- 下一次提交；
- `pair_long_term_outcome`；
- 规则或模型推荐结果。

标注者先标 `Need`，再独立标 `Interruptibility`，不能先看系统推荐。

### 第二阶段：事后评价

由脚本自动加入 `Outcome`。如需人工分析未来行为，必须放在单独的事后页面，不得回写成因果标签。

### 一致性要求

- 至少两名标注者独立标注一部分样本；
- 报告 Need 和 Interruptibility 各自的 Cohen's kappa；
- `-1` 不强行转为二分类；
- 分歧样本由第三方或共同讨论仲裁；
- 保留原始标注、仲裁结果和版本号。

## 7. 决策映射

最终系统决策不是人工标签本身，而是策略层输出：

| Need | Interruptibility | 默认策略 |
|---:|---|---|
| 1 | `show_now` | 进入展示候选 |
| 1 | `delay` | 延迟观察 |
| 1 | `suppress` | 静默记录 |
| 0 | 任意确定值 | 不展示 |
| -1 | 任意 | 不自动展示，进入抽检 |

该映射是系统策略，不是新的监督标签。

## 8. 不能声称的内容

在没有在线对照实验前，不得声称：

- 提示提高了 AC 率；
- 提示改善了学习效果；
- 提示降低了真实挫败感；
- 已经直接测量了学生的可打扰性；
- `pair_long_term_outcome` 是窗口级 ground truth。

