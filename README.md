# oj_demo

配对编程 AI 助手：基于按键行为推断开发者状态（IDLE / DEBUG），在最合适的时机提供建议（side_note）。

## 快速开始

- 项目总手册：[docs/PROJECT_HANDBOOK.md](docs/PROJECT_HANDBOOK.md)
- 环境配置：[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)
- 数据管线：[docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md)
- 标签规范：[docs/LABEL_SPEC.md](docs/LABEL_SPEC.md)

## 目录结构

```
oj_demo/
├── docs/                  # 正式文档
├── extract_clean_dataset.py   # 数据清洗入口
├── labeling/              # Gen 2 核心 pipeline
├── legacy/                # Gen 1 归档（旧脚本 + 旧数据）
├── lit_pdf/               # 文献
└── resources/             # 原始标签归档
```

详细说明见 [docs/PROJECT_HANDBOOK.md](docs/PROJECT_HANDBOOK.md)。
