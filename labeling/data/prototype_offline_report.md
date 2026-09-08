# Prototype 离线规则与模型评估

- 窗口总数：500
- 已知标签（排除 -1）：356
- 正样本：18，负样本：338
- session 数：83
- 验证方式：按 solution_id 分组的 5 折 GroupKFold，避免同一 session 的窗口同时出现在训练和测试中。

## 最佳候选规则

`low_speed_mid_task`：Precision=81.2%，Recall=72.2%，F1=76.5%，触发=16 条。

## 分组留出模型

Logistic Regression：Precision=27.5%，Recall=77.8%，F1=40.6%，预测弹窗=51 条。
Random Forest：Precision=33.3%，Recall=22.2%，F1=26.7%，预测弹窗=12 条。

## 运营侧解释

Logistic Regression 的 OOF 预测中，每个 session 平均弹窗数为 0.61，平均误弹数为 0.45。
预测弹窗数为 0 的 session：48/83。

## 重要特征（描述性）

current_idle_s (0.0506)、keys_5s (0.0000)、text_keys_5s (0.0000)、modifier_keys_5s (0.0000)、clipboard_ops_5s (0.0000)、pause_count_5s (0.0000)、pause_total_5s (0.0000)、pause_p90_5s (0.0000)、backspace_5s (0.0000)、enter_5s (0.0000)

## 限制

这些标签是保守的人工/AI 原型标签，不是线上干预结果；模型指标只能说明对当前标注标准的拟合能力，不能证明弹窗改善了学习效果。下一步若上线，应先做小规模灰度/A-B，并把误弹率和每 session 弹窗次数设为硬约束。

产物：`prototype_offline_rule_metrics.csv`、`prototype_offline_oof_predictions.csv`、`prototype_offline_session_metrics.csv`、`prototype_offline_feature_importance.csv`。
