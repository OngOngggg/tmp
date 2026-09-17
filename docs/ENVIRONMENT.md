# OJ Demo 统一运行环境

## 当前规范环境

本机已验证可用的 Anaconda base 环境：

```text
D:\02_code\anaconda3\python.exe
Python 3.13.5
NumPy 2.4.6
pandas 3.0.3
scikit-learn 1.6.1
```

后续项目实验统一使用这个解释器，不使用 Codex bundled Python，也不依赖 Windows Store 的 `python` 占位命令。

## 验证环境

```powershell
& "D:\02_code\anaconda3\python.exe" -c "import sys, numpy, pandas, sklearn; print(sys.executable); print('numpy', numpy.__version__); print('pandas', pandas.__version__); print('sklearn', sklearn.__version__)"
```

## 运行当前离线实验

```powershell
& "D:\02_code\anaconda3\python.exe" labeling/offline_research_eval.py --bootstrap 1000
```

## 新机器重建环境

项目提供了 `environment.yml`。如果 Conda 插件导致 `env create` 报错，可先在当前 PowerShell 会话禁用插件：

```powershell
$env:CONDA_NO_PLUGINS = "true"
conda env create -f environment.yml
conda activate oj-demo
```

环境文件用于重建依赖；当前机器的正式运行命令仍使用已验证的 base 解释器。

## 研究可复现性要求

- 运行日志中记录 `sys.executable` 和 NumPy/pandas/scikit-learn 版本；
- 随机森林固定 `n_jobs=1`，避免受限 Windows 环境下 joblib 多进程触发权限错误；
- 不把 `.env`、原始学生代码、行为导出和数据库密码提交到仓库；
- Conda 环境出现升级时，重新运行离线基线并保存结果版本；
- 论文表格使用 `labeling/data/offline_research/` 中的结果文件，不手工改数字。
