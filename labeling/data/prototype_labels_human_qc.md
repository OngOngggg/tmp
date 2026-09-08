# 完整人工标签数据质量报告

## 数据来源

- 第一批：C:\Users\10950\Downloads\prototype_labels.csv，235条。
- 第二批：C:\Users\10950\Downloads\prototype_labels_remaining.csv，265条。
- 合并后输出：`prototype_labels_human_complete.csv`。
- 原始下载文件未修改，标签值未为改善指标而调整。

## 完整性检查

- 合并总行数：500。
- 唯一window_id：500。
- 两批重复window_id：0。
- 标签无法匹配窗口：0。
- 尚未标注窗口：0。
- 非法或缺失标签：0。
- solution_id不一致：0。

## 标签分布

|label|含义|数量|
|---:|---|---:|
|1|该提示|90|
|0|不该提示|290|
|-1|不确定/跳过|120|

确定二分类标签：380条；涉及session：84个。

## 说明

这份文件用于正式离线评估。若后续需要复核某条标签，应在单独的审计文件中记录old_label、new_label、reason和reviewer，不直接覆盖本文件。
