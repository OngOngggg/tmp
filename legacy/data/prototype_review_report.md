# 人工正例二次复核

## 范围

- 原始合并标签：500条，其中原始`1`为90条。
- 仅复核原始标签为`1`的窗口；原始标签文件未修改。
- 复核使用窗口结束时已可见的行为特征，不使用未来事件。

## 复核结果

|标签|复核后数量|原始1窗口在该标签的数量|
|---|---:|---:|
|`1` 该提示|23|23|
|`0` 不该提示|297|7|
|`-1` 不确定/跳过|180|60|

本次修改：67条（`1 -> 0`：7，`1 -> -1`：60）。

## 判定依据

|规则|数量|处理|
|---|---:|---|
|`active_recent_input`|7|改为0|
|`shortcut_or_clipboard_ambiguous`|2|改为-1|
|`long_idle_no_recent_evidence`|46|改为-1|
|`recent_edit_then_pause`|23|保留1|
|`insufficient_evidence`|12|改为-1|

`1`仅表示“可以作为低打扰帮助候选”，不是已经证明学生需要帮助；`-1`表示当前证据不能支持干预判断。

## 产物

- `prototype_labels_human_reviewed.csv`：复核后的独立标签副本。
- `prototype_label_review_changes.csv`：逐条记录旧标签、新标签、理由和复核版本。

原始`prototype_labels_human_complete.csv`及用户导出的两个文件均未覆盖。
