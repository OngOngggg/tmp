# 数据抽取与清洗

`extract_clean_dataset.py` 是数据库到离线分析数据集的可恢复抽取器。

## 运行

在项目根目录执行：

```powershell
D:\02_code\anaconda3\python.exe extract_clean_dataset.py --output data\clean_oj --resume
```

密码优先读取环境变量 `OJ_DB_PASSWORD`，未设置时读取项目根目录 `.env`。脚本只读 MySQL，在本地 `data/clean_oj` 写入结果。中断后重复执行同一命令即可从 `scan_checkpoint.json` 继续。

## 默认筛选口径

- `key_action.problem_id > 0` 且 `solution_id > 0`；
- 只保留 JSON 中 `type=down` 且时间可解析的事件；
- 有效事件数至少 30；
- 事件跨度 60 到 1800 秒；
- 时间解析率至少 0.8；
- 同一 `solution_id` 只保留质量更高的一行；
- 关联不到 `csuoj_db.solution` 的孤立提交不进入最终 CSV。

所有阈值都可以通过命令行覆盖，例如：

```powershell
D:\02_code\anaconda3\python.exe extract_clean_dataset.py --min-duration 30 --min-parse-ratio 0.95 --resume
```

## 输出

- `data/clean_oj/clean_sessions.csv`：session 元数据、最终判题结果、代码长度、事件质量指标；
- `data/clean_oj/events/key_action_clean.csv`：每个 session 一行，只含规范化的 `down` 事件；
- `data/clean_oj/candidates.sqlite3`：去重和断点续跑用的本地暂存；
- `data/clean_oj/scan_checkpoint.json`：扫描进度。

当前一次完整扫描得到 `41,696` 个有效 session。最终判题结果是事后元数据，只能用于标签/结果分析，不能作为窗口触发特征；窗口结束后的事件同样不能用于在线判断。

## 生成窗口

现有 prototype 构建器已支持清洗目录：

```powershell
D:\02_code\anaconda3\python.exe labeling\build_prototype.py `
  --events-dir data\clean_oj\events `
  --sessions-file data\clean_oj\clean_sessions.csv `
  --output-dir data\clean_oj\prototype
```

这样不会覆盖已有的 `labeling/data` 标注结果；不传 `--output-dir` 时仍保持旧版默认输出位置。

## 提交时间线与客观锚点

按操作文档的下一步，先生成启用提交的全量时间线：

```powershell
D:\02_code\anaconda3\python.exe labeling\extract_submission_timeline.py --resume
D:\02_code\anaconda3\python.exe labeling\build_submission_context.py
```

产出：

- `submission_timeline.csv`：524,916 条启用提交；
- `session_submission_context.csv`：41,696 个 clean session 的提交前上下文。

`last_known_judge_before`、`prior_submit_count`、`time_since_prior_s` 是可以作为窗口特征的因果字段。`own_result`、`next_submit_result_after`、`pair_outcome` 和 `pair_*` 只能用于事后评价。

## 全量事件驱动候选

```powershell
D:\02_code\anaconda3\python.exe labeling\build_full_causal_candidates.py
```

当前产出 `full_causal_candidates.csv` 共 172,622 条：

- `idle_30s`：168,656 条；
- `backspace_pause_2s`：3,966 条；
- 覆盖 37,462 个 session。

候选的因果特征只使用 `event_time < trigger_time` 的事件。`outcome_*`、`own_result` 和 `pair_*` 字段明确标记为评价字段，禁止直接送入在线触发器。
