# 代码 diff 特征 —— 迁移到另一台电脑运行说明

> 脚本：`labeling/build_code_diff_features.py`
> 本文档回答：去新电脑上跑这个脚本，需要带哪些文件、装什么环境、怎么连数据库、跑完看什么。

---

## 1. 这台脚本在做什么（30 秒回顾）

从 OJ 数据库 `csuoj_db.source_code` 取出每个提交的最终代码，对同一 (user, problem) 的**相邻两次提交**做 diff，产出：

- 事后字段：`line_diff_ratio` / `net_growth` / `changed_lines`（本次提交 vs 上次提交，会话结束才知道）
- 因果字段：`prev_submit_line_diff` / `prev_submit_net_growth`（上次提交的 diff，会话开始前已知）

主信号是**行级 diff**（`SequenceMatcher` 对行序列），字符级降为辅助列。

---

## 2. 必须带过去的东西（4 类）

### 2.1 代码（git 里有的）

直接 `git clone` 或 `git pull` 就能拿到：

- `labeling/build_code_diff_features.py` —— 唯一要跑的脚本
- `environment.yml` —— 环境声明

### 2.2 输入数据（⚠️ git 里没有，必须单独拷贝）

`.gitignore` 排除了 `data/clean_oj/`，所以这两个文件**不会**跟着 git 走，要手动拷：

| 文件 | 大小 | 说明 |
|---|---|---|
| `data/clean_oj/submission_timeline.csv` | ~几十 MB | 全量提交时间线（52 万行） |
| `data/clean_oj/session_submission_context.csv` | ~几 MB | clean session 上下文（4.2 万行） |

**拷法**：U 盘 / 网盘 / `scp` 都行，放到新电脑对应项目根目录的 `data/clean_oj/` 下即可（脚本默认路径是相对项目根的 `data/clean_oj/`，不用改）。

### 2.3 数据库密码（⚠️ 不进 git，手动配）

脚本里 `host` 和 `port` 是硬编码的（`122.207.108.6:53306`），只有**密码**从环境变量或 `.env` 读。

新电脑上二选一：

```powershell
# 方式 A：环境变量（临时）
set OJ_DB_PASSWORD=你的密码

# 方式 B：项目根目录建 .env 文件（内容一行）
OJ_DB_PASSWORD=你的密码
```

> 本项目本机的 `.env` 被 gitignore 忽略了，不会同步过去，必须在新电脑重新建。

### 2.4 网络（⚠️ 最容易踩的坑）

数据库是 `122.207.108.6:53306`（校内/远程 MySQL）。**新电脑必须能访问这个 IP**。如果之前是靠校园网 / VPN / 内网才能连，新电脑要先确认网络通不通：

```powershell
# 测试端口是否可达（Windows PowerShell）
Test-NetConnection 122.207.108.6 -Port 53306
```

不通的话，脚本会卡在 `pymysql.connect` 报连接超时。

---

## 3. 环境准备

脚本只依赖 `pymysql` + `pandas`（`difflib` 是标准库）。

**推荐**：用 conda 按 `environment.yml` 建环境（Python 3.13 + pandas 3.0 + pymysql）：

```powershell
conda env create -f environment.yml
conda activate oj-demo
```

**或者**：已有 conda 环境，直接装两个包：

```powershell
pip install pymysql pandas
```

> 本机实测版本：pymysql 1.4.6 + pandas 3.0.3，能正常跑。pandas 版本不需要严格 3.0，2.x 也能跑。

---

## 4. 运行

```powershell
# 在项目根目录下执行
python labeling/build_code_diff_features.py
```

带参数版（通常不用，默认值已对）：

```powershell
python labeling/build_code_diff_features.py `
  --timeline data/clean_oj/submission_timeline.csv `
  --context  data/clean_oj/session_submission_context.csv `
  --out      data/clean_oj/code_diff_features.csv `
  --report   data/clean_oj/code_diff_features.md
```

**预期耗时**：约 13 分钟（主要是 4.2 万次 diff 计算），期间每 5000 条打印一次进度：

```
  diff progress: 0/41696
  diff progress: 5000/41696
  ...
```

---

## 5. 输出与验收

跑完产出两个文件，都在 `data/clean_oj/`：

| 文件 | 内容 |
|---|---|
| `code_diff_features.csv` | 特征表（41,696 行，含因果 `prev_submit_*` 列） |
| `code_diff_features.md` | 自动生成的报告 |

**验收标准**：脚本末尾打印的这组数字应该和本机一致：

```
cleaned_sessions_compared=41,696  missing=20,446
line_similarity quantiles:
0.50    0.9000
0.75    0.9630
0.90    0.9867
0.95    1.0000
...
                   count    mean  median
pair_outcome
breakthrough       16501  0.2231  0.0909
fully_stuck         2158  0.2467  0.1034
immediate_success   2591  0.3396  0.2340
```

如果数字对得上 → 环境、数据、数据库连接都正确。

---

## 6. 已知结论（跑之前先知道，避免误判）

- `missing=20,446`（49%）**不是 bug**。这些是该 (user, problem) 的**首次提交**，没有"上一个提交"可比，diff 天然无法计算。数据库查询覆盖率是 100%，逻辑正确。
- 完整实验记录见 `data/clean_oj/code_diff_features_experiment.md`（也需手动拷贝过去，或者只在本机看）。

---

## 7. 快速检查清单

- [ ] 新电脑能 ping 通 / TCP 连通 `122.207.108.6:53306`
- [ ] 拷了 `data/clean_oj/submission_timeline.csv` 和 `session_submission_context.csv`
- [ ] 配好了 `OJ_DB_PASSWORD`（环境变量或 `.env`）
- [ ] `python` 环境有 `pymysql` + `pandas`
- [ ] 在项目根目录跑 `python labeling/build_code_diff_features.py`
- [ ] 末尾数字与本机一致（`41,696 / 20,446`）
