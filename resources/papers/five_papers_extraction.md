# 五篇核心论文正文级提取（标注与实验细节）

本文件基于 5 篇论文的**完整正文**（已下载 PDF 并用 pdftotext 提取），逐篇提取 8 类字段：
标签定义、标注者身份与数量、标注材料、分歧处理、样本量、训练测试划分、完整实验指标、局限性原文表述。
所有数值均引自正文，非摘要猜测。

---

## 1. Dong et al. (2021) — EDM

**完整引用**：Dong, Y., Marwan, S., Shabrina, P., Barnes, T., Price, T. (2021). *Using Student Trace Logs To Determine Meaningful Progress and Struggle During Programming Problem Solving.* EDM 2021, pp. 439–445.

### 标签定义
- **挣扎（struggling）的操作性定义**：学生在「典型时间量」内未能取得「显著进展」。原文：“we consider a student to be struggling during problem-solving when they could not make enough progress within a typical amount of time.”
- **进展度量**：改编 SourceCheck 算法的 mapping cost，反转为 similarity score（相似度分数）。某个快照的「进展」= 当前快照与上一快照的相似度差。
- **显著进展阈值**：所有 trace 的「绝对进展（absolute progress）」值的 **25 百分位**。Squiral = **1.25**，Guessing Game = **1.5**。
- **典型时间阈值**：做出显著进展所用时间的 **75 百分位**。Squiral = **105.3s**，GG = **84.5s**。
- **挣扎时刻** = 耗时 > 典型时间的 code chunk；**进展时刻** = 耗时 ≤ 典型时间的 chunk。

### 标注者身份与数量
- **3 位专家标注者（expert raters），全部是论文作者**。
- 身份：均为计算机科学研究生（computer science graduate students）。其中 2 位有大量 GG trace 分析经验，3 位均有大量 Squiral trace 分析经验。
- 原文明确：“The expert raters were not pedagogical experts and had experience levels on par with experienced TAs.”（非教学专家，经验相当于资深助教）

### 标注材料
- 定制界面，让标注者**视觉逐步浏览学生代码变化**（step through code changes）。
- 标注时参考**动作之间的时间间隔**与**动作类型**。
- 要求标注者**避免后见之明（hindsight）**：不得用后续动作来为早期干预辩护。

### 分歧处理
- 先在一份**训练数据集**上练习标注，每标注一个样本立即讨论。
- 正式标注：挣扎样本**分三轮**，每轮标注 1/3，每轮结束后**集中讨论分歧、消除因疏忽造成的分歧**。
- **不强制达成完全一致**（“We did not require the experts to reach a complete consensus ... experts sometimes have different opinions”）。
- 报告 **Fleiss' Kappa**（讨论前后均报告）。
- 进展样本：独立标注后检查分歧以修正疏忽错误。

### 样本量
- Squiral：**45 条 trace，25,160 行动行**，平均耗时 29.6 分钟，平均分 9.8/12。
- Guessing Game (GG)：**59 条 trace，22,744 行动行**，平均 30.5 分钟，平均分 11.7/12。
- 预处理：删除超过 5 分钟无动作的空闲时间。
- 标注子样本（20% 采样）：Squiral **29 挣扎 + 29 进展**；GG **57 挣扎 + 54 进展**。

### 训练测试划分
- **无机器学习模型训练**。是描述性算法 + 人工验证。无 train/test split。

### 完整实验指标
| 指标 | Squiral (3 raters) | GG (2 raters) |
|---|---|---|
| 挣扎样本专家同意率 | 77.0% (N=29) | 83.3% (N=57) |
| 挣扎样本 Fleiss' Kappa (讨论前/后) | 0.805 / 0.847 | 0.539 / 0.646 |
| 进展样本专家同意率 | 85.2% (N=29) | 85.1% (N=54) |
| 进展样本 Fleiss' Kappa | 0.853 | 0.819 |

- 关键表述：“over 77% of the time ... agreed an intervention was needed ... Over 85% ... agreed an intervention was not needed.”

### 局限性原文
1. “we only used three expert raters ... were not pedagogical experts and had experience levels on par with experienced TAs. Hence the evaluation result may be different if rated by experienced instructors.”
2. “our work is limited by a small sample size with only two programming assignments.”
3. SourceCheck 的「solution matching」问题：学生换解法时相似度分数会非单调下降，导致误判挣扎。
4. 「logic errors」和「human factors」无法被纯距离度量捕获（需要语义理解）。

---

## 2. Tabarsi et al. (2022) — CSEDM (Zenodo)

**完整引用**：Tabarsi, B. T., Limke, A., Reichert, H., Qualls, R., Price, T., Martens, C., Barnes, T. (2022). *How to Catch Novice Programmers' Struggles: Detecting Moments of Struggle in Open-Ended Block-Based Programming Projects using Trace Log Data.* CSEDM 2022, pp. 57–65. DOI: 10.5281/zenodo.6983260.

### 标签定义
- **挣扎** = 学生的**负向自我评估时刻（negative self-assessment moments）**，源自 Gorson & O'Rourke (2020) 的 13 个时刻，改编为 **15 个场景**（前 13 个对应原 13 时刻，后 2 个是否定式）。
- **7 个检测器**（规则）：Sprite Deletion、Overly Idle（>5 分钟无动作）、Scant Blocks（开始 5 分钟后脚本块 <3）、Minor Change（运行间 1-2 块微调）、Last Rows Count（最后 10 分钟动作数）、Excessive Runs（无改动连续运行 >2 次）、Blocks Per Minute。
- 标签不是人工给「时刻」打标，而是**用学生自报告作为 gold 参照**。

### 标注者身份与数量
- **检测器设计**：**4 位专家** = 1 位 CS 教育专家教授 + 3 位博士生（全部为作者）；其中 2 位做过大量 Snap! 研究，2 位是 Snap! 编程专家。
- **验证标注**：**2 位专家**逐步标记 trace（第 1 位逐动作分析单条 trace；第 2 位用 Snap Playback 回放 5 名学生的编码过程）。
- **学生自报告**：第一天 **16 人**，第二天 **13 人**。

### 标注材料
- iSnap（Snap! 变体）**trace log**（积木式编程动作 + 快照）。
- **学生自报告问卷**（6 点 Likert 满意度 + 15 个场景的发生/感受）。

### 分歧处理
- **无一致性统计（未报告 kappa）**。用 Spearman 秩相关 + 事后专家标记来验证。
- 专家标记仅作为定性解释检测器成败的依据，不构成独立 gold standard。

### 样本量
- 45 名非 CS 专业学生的入门课，**19 条匹配到问卷的 trace**，合计 **12,262 行动行**。
- 人口统计：7 女 / 11 男 / 1 保密。

### 训练测试划分
- **无模型训练**，纯规则检测器 + 相关性分析。无 train/test split。

### 完整实验指标
- 采用 **Spearman 秩相关 + p 值**（p<0.05 显著），**区分 occurrence（是否发生）与 valence（感受效价，1=bad/2=ok/3=good）**。
- 显著相关示例（valence）：
  - Overly Idle ↔ 「looked up how to do something」 r=-0.5595, p=0.0468
  - Overly Idle ↔ 「spent long time looking for error」 r=-0.6299, p=0.0282
  - Overly Idle ↔ 「unsure what to work on」 r=-0.6753, p=0.0226
  - Last Rows Count ↔ 「started over」 r=0.6464, p=0.0231
  - Blocks Per Minute ↔ 「feeling about programming」 r=-0.5212, p=0.0221
- **无 precision/recall/F1/kappa**（报告的是相关系数）。

### 局限性原文
1. “limited by a low participation rate and its generalizability needs to be verified.”
2. “we found a significant number of p-values ... this could lead to the multiple comparison problem. We consider addressing this issue ... using methods such as Bonferroni or Benjamini-Hochberg correction.”
3. 仅收集了两个编码 session（各约 1 小时）的数据，不足以预测最终成绩。

---

## 3. Schwartz et al. (2025) — ECAI (arXiv:2508.17353)

**完整引用**：Schwartz, N., Fairstein, R., Segal, A., Gal, K. (2025). *Detecting Struggling Student Programmers using Proficiency Taxonomies.* ECAI 2025. arXiv:2508.17353.

### 标签定义
- **挣扎（struggling）**：**客观自动定义**，原文：“a student is defined as struggling if they either fail one or more unit tests for a given task **or** require significantly more attempts than 75% of their peers to complete the task successfully.”
- 明确避免依赖首次尝试成功（因为迭代式开发会普遍增加尝试次数）。
- 示例：CodeWorkout 例题 630 名尝试者中 179 名定义为挣扎；FalconCode 例题 168 名尝试者中 48 名挣扎。

### 标注者身份与数量
- **非人工标注**。标签由单元测试 + 提交次数自动派生。
- 但**分类法构建**用了人工访谈：**2 位计算机科学教师（30+ 年教学经验）+ 2 位 CS1 课程 TA**。
- 这些教师/TA 完成了一份关于挣扎学生挑战的问卷，并给文献提炼的「挣扎指标」打分。

### 标注材料
- **代码提交历史 + 单元测试结果**（自动评分）。
- 访谈/问卷用于构建「Coding Proficiency Taxonomy」。

### 分歧处理
- **无人工标注分歧**（标签客观）。无 kappa 报告。

### 样本量
- **CodeWorkout**（Java，美国公立大学入门课）：**630 学生，50 任务**（10-26 行代码）。
- **FalconCode**（Python，美国空军学院）：**1,330 学生，408 任务**（基础 1-3 行 + lab 10-50 行）。
- 每任务最多取 100 次最近尝试。

### 训练测试划分
- **5 折交叉验证（CV-5）**，**按学生划分**（保证每个学生只出现在训练或测试集）。
- 沿用 CSEDM Data Challenge 协议：**用前 30 次提交预测后续 20 次提交**。

### 完整实验指标（ROC-AUC %，均值 ± 标准差）
**CodeWorkout：**
| 模型 | ROC-AUC |
|---|---|
| DKT + Target Task ID | 76.27 ± 2.2 |
| Code-DKT + Target Task ID | 70.93 ± 4.3 |
| SAKT | 76.11 ± 1.09 |
| **PTM** | **77.09 ± 1.8** * |

**FalconCode：**
| 模型 | ROC-AUC |
|---|---|
| DKT + Target Task ID | 63.54 ± 1.8 |
| Code-DKT + Target Task ID | 62.17 ± 2 |
| SAKT | 70.52 ± 0.8 |
| **PTM** | **73.18 ± 0.9** * |

**Ablation（PTM 消融）：**
| 变体 | CodeWorkout | FalconCode |
|---|---|---|
| No-Tax & No-Hist | 72.50 ± 3.5 | 69.13 ± 1.3 |
| No-Tax | 75.52 ± 1.7 | 71.33 ± 0.6 |
| PTM | 77.09 ± 1.8* | 73.18 ± 0.9* |

- 显著性用 **paired bootstrap + Bonferroni 校正**；* 表示显著优于其余。

### 局限性原文
1. GenAI 时代学生可能靠 AI 工具或抄袭表现出「成功」，而实际未掌握技能——“identifying genuine struggle remains a challenge ... students might appear successful while relying on AI tools or copying.”（本研究未考虑，留待未来）
2. “we did not include precision or recall scores due to the imbalanced nature of the datasets.”（只用 ROC-AUC）
3. 单元测试只测功能正确性，可能不完全反映概念理解。
4. 分类法部分层未显式建模（如 testing、documentation 因数据集限制被省略）。
5. CodeT5/CodeLlama 有微小增益但计算成本高，未采用。

---

## 4. Pu et al. (2025) — CHI (arXiv:2502.18658)

**完整引用**：Pu, K., Lazaro, D., Arawjo, I., Xia, H., Xiao, Z., Grossman, T., Chen, Y. (2025). *Assistance or Disruption? Exploring and Evaluating the Design and Trade-offs of Proactive AI Programming Support.* CHI 2025, Article 152. DOI: 10.1145/3706598.3713357.

### 标签定义（因变量）
- **disruption（打断）**的量化定义：“instances when, during a system-initiated intervention, the user switched their context to process AI's actions but found them unhelpful and interruptive, resulting in the dismissal or reversion of the AI actions.”
- **效率**：用户表达意图的时间（expression time）与解读 AI 响应的时间（interpretation time），按「interaction episode」计时。
- **主动干预**由 6 个规则启发式触发（Table 1）：idle（初始 30s 阈值）、代码块完成（Python 反缩进）、程序执行、多行修改、代码注释、保持选择（15s 阈值）。

### 标注者身份与数量
- **18 名高年级 CS 学生**（8 女 10 男；平均 21.3 岁，SD 1.49；编码经验均值 5.6 年；15 人用过 ChatGPT 类工具，13 人偶尔用 AI 编程）。
- 定性分析：访谈由 **3 位研究者独立编码**，随后 **1 位研究者做主题分析（thematic analysis）**。

### 标注材料
- **编辑器活动 + 任务上下文**：caret 位置、文件内容、用户活动（或缺乏活动）、console 输出。
- 3 个编程任务（event scheduler / word guessing / budget tracker），改编自 LeetCode。

### 分歧处理
- 定性编码由 3 人独立完成 + 1 人主题分析（未报告编码者间 kappa）。

### 样本量
- **18 参与者 × 3 条件 × 3 任务 = 54 个任务实例**。
- **1,004 个人机交互 episode** 用于分析。
- **398 个主动干预实例**（proactivity instances）。
- 每个 session 约 90 分钟，报酬 $40。

### 训练测试划分
- **组内被试设计（within-subject）**，3 个条件（PromptOnly / CodeGhost / Codellaborator），条件顺序 **counterbalanced**。
- 无机器学习训练。

### 完整实验指标
**打断量化（398 个主动实例）：**
- **212 (53.3%) 有效参与**；**48 (12.1%) 打断**；**138 (34.7%) 被忽略/未注意**。

**Likert 主观打断感（Friedman 检验，χ²=22.1, df=2, p<0.001）：**
- CodeGhost 均值 4.61 (SD 1.58) > Codellaborator 3.78 (1.86) > PromptOnly 1.56 (1.15)。
- Wilcoxon + Bonferroni：CodeGhost > PromptOnly（Z=3.44, p<0.01）；Codellaborator > PromptOnly（Z=3.10, p<0.01）；CodeGhost vs Codellaborator 无显著差异（Z=-1.51, p=0.131）。

**解读时间（one-way ANOVA，F(2,856)=41.1, p<0.001）：**
- PromptOnly 34.5s > CodeGhost 19.8s > Codellaborator 18.7s（p<0.001）。

**表达时间（F(2,652)=2.36, p=0.095，不显著）。**

**AI 感知意识（Friedman χ²=12.7, df=2, p<0.001）：** PromptOnly 6.56 > Codellaborator 5.44 > CodeGhost 4.17。

**主动启发式效果：** 最有效的是 multi-line change (73.1%)、user-written comment (69.2%)、program execution (66.7%)；最差的是 idle 启发式（用户空闲时往往在高认知负荷思考，被忽略约 50%）。

### 局限性原文
1. “Our design exploration is not exhaustive ... only allows for single-file coding in Python. The human-AI interactions and code provenance information are not persisted across sessions.”（外部效度有限）
2. “the inconsistency in responses from LLM. Despite efforts to minimize randomness, participants did not always receive the same quality or level of proactivity for similar queries.”（LLM 响应不稳定，影响信任与任务时长）
3. 低风险、小规模任务场景，无规模性/可维护性/安全性等工程考量。
4. 建议未来做纵向使用研究、支持多文件多语言、真实编程环境。

---

## 5. Koutcheme et al. (2024) — ITiCSE (arXiv:2405.05253)

**完整引用**：Koutcheme, C., Dainese, N., Sarsa, S., Hellas, A., Leinonen, J., Denny, P. (2024). *Open Source Language Models Can Provide Feedback: Evaluating LLMs' Ability to Help Students Using GPT-4-As-A-Judge.* ITiCSE 2024, pp. 52–58. DOI: 10.1145/3649217.3653612.

### 标签定义
- **反馈质量的 3 个二元标准**（沿用 Hellas et al. 2023 的专家标注）：
  1. **completeness**：识别并提及所有实际问题（all actual issues）。
  2. **perceptivity**：识别并提及至少一个实际问题（at least one actual issue）。
  3. **selectivity**：不识别不存在的问题（does not identify non-existent issues）。
- 每个标准视为一个独立的**二元分类任务**（每个帮助请求一条实例）。

### 标注者身份与数量
- **ground truth 来自 1 位人类专家**（原研究 Hellas et al. 2023 中「有丰富编程教学经验」的评估者，qualitative analysis）。
- **GPT-4 作为自动 judge** 重新标注同样 150 条反馈（用相同 rubric）。

### 标注材料
- **学生帮助请求对应的错误程序代码 + GPT-3.5 生成的反馈文本** + 问题描述 + 模型解。
- 数据来自 Aalto 大学在线入门编程课（Dart 语言）。

### 分歧处理
- 用 **Cohen's kappa** 量化 GPT-4 与人类专家的一致度。
- 明确指出 GPT-4 存在**正向偏置**（倾向于给更积极的评价）。

### 样本量
- **150 条帮助请求**（15 个最多帮助请求的练习 × 10 条随机采样）。
- ground truth 标注统计：completeness True=82/False=68；perceptivity True=127/False=23；selectivity True=78/False=72（共 283 条 True / 167 条 False）。

### 训练测试划分
- **无模型训练**（评估任务）。无 train/test split。

### 完整实验指标（GPT-4-as-judge vs 人类专家）
| 标准 | precision | recall | f0.5 | f1 | accuracy | kappa |
|---|---|---|---|---|---|---|
| completeness | 0.70 | 0.95 | 0.74 | 0.81 | 0.75 | **0.48** |
| perceptivity | 0.84 | 1.00 | 0.87 | 0.91 | 0.85 | **0.22** |
| selectivity | 0.65 | 0.94 | 0.69 | 0.77 | 0.71 | **0.40** |

- 关键结论：GPT-4 能**可靠识别低质量反馈**（高 recall），但**整体过于乐观**；perceptivity 的 kappa 仅 0.22，且相比「全预测多数类」的 dummy 模型仅提升 2 个百分点（数据偏斜所致）。

### 局限性原文
1. “we only take a look at a small subset of data coming from one institution, and we will need more to make our results even more robust.”
2. “Dart is hardly the most popular programming language ... GPT-4 as a judge could exhibit stronger evaluation performance for a language with more presence such as Python.”
3. “we only evaluated the ability of GPT-4 to judge the quality of the feedback generated by a single other language model (GPT-3.5), for which GPT-4 might be biased towards giving positive results.”
4. 结果「不提供 per-feedback 的保证，只是统计概览」；LLM judge 不应单独作为评估手段，需人工判断兜底。

---

## 横向对比速览

| 维度 | Dong 2021 | Tabarsi 2022 | Schwartz 2025 | Pu 2025 | Koutcheme 2024 |
|---|---|---|---|---|---|
| 标签来源 | 专家人工评估 | 学生自报告 | 客观（单元测试/尝试数） | 行为量化（打断/时间） | 专家 + GPT-4 judge |
| 标注者 | 3 位 CS 研究生（=TA 级） | 4 专家设计 + 2 专家验证 | 2 教师+2 TA（访谈，非标注） | 18 被试 + 3 研究者编码 | 1 人类专家 + GPT-4 |
| 是否独立标注 | 是（3 轮独立） | 否（学生个体 + 专家定性） | 不适用 | 3 人独立编码 | GPT-4 独立重标 |
| 一致性指标 | Fleiss' Kappa 0.54–0.85 | 无（Spearman 相关） | 无 | 未报告 | Cohen's kappa 0.22–0.48 |
| 是否 uncertain 类 | 是（"not now"） | 否 | 否 | 否 | 否 |
| 样本量 | 104 traces / 139 标注样本 | 19 traces / 12262 行 | 630+1330 学生 | 54 任务 / 1004 episode | 150 条 |
| 训练/测试 | 无 | 无 | 5 折 CV 按学生分 | 组内 counterbalanced | 无 |
| 主要指标 | 同意率 77%/83% + Fleiss K | Spearman r + p | ROC-AUC | ANOVA + 时间 + 打断率 | P/R/F1/kappa |
| 是否在线实验 | 否 | 否 | 否 | 是（用户研究） | 否 |
