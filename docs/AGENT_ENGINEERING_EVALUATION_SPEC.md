# Agent Engineering 多场景评测实验规范

## 1. 文档状态

| 项目 | 内容 |
|---|---|
| 版本 | 0.1 |
| 状态 | 实施中 |
| 适用课程 | AI Agent 开发与评测实验 |
| 评测框架 | Harbor 0.24 |
| 默认模型 | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |
| 默认区域 | `us-west-2` |

本实验是现有 DevOps Agent 改造赛之外的独立实验。它不读取、不修改：

- `evaluation/presets/terminal-bench-competition.txt`；
- `docs/COMPETITION_TASK_SUITE.md`；
- `devopsagent-eval` 的参数和输出；
- 讲师维护的 Terminal-Bench 隐藏题。

独立入口为：

```text
agent-engineering-eval
```

独立结果目录为：

```text
evaluation/agent-jobs/
```

## 2. 实验目标

DevOps 比赛主要回答“Agent 能否完成终端任务”。本实验回答另一个问题：

> 同一模型、工具权限和预算下，不同 Agent 控制策略、上下文策略和能力注入方式，
> 在不同任务类型上分别产生什么收益和成本？

课程不把某一种架构宣布为“最佳 Agent”。学员需要形成三类能力：

1. 将 Agent 架构改动表达为可控实验变量；
2. 识别改动对不同任务族的异质性影响；
3. 用通过率、稳定性、成本和失败轨迹做架构决策。

## 3. 两条正交评测轴

### 3.1 Benchmark 轴：Agent 做什么

| Track | 候选 Benchmark | 主要能力 |
|---|---|---|
| Terminal | Terminal-Bench | 环境探索、编码、调试、交付验证 |
| Data Analysis | DABstep | 多步数据分析、Python/pandas、业务答案 |
| Tool Calling | BFCL Parity | 工具选择、参数构造、无关请求、并行调用 |
| Software Engineering | SWE-bench Verified | 长程代码库理解、修复、回归测试 |
| Observability | OTel-Bench | 埋点、上下文传播、运行时验证 |
| Codebase QnA | SWE-Atlas QnA | 代码库检索、证据定位、答案可靠性 |
| Skills | SkillsBench | Skill 发现、加载和遵循 |
| MCP | 课程自建 Harbor Task | MCP 连接、资源发现、工具错误恢复 |

### 3.2 Variant 轴：Agent 如何做

| Variant | 核心变量 | 第一版状态 |
|---|---|---|
| ReAct Baseline | 模型—工具—结果循环 | Ready |
| Plan-and-Execute | 显式计划、执行、重规划 | Planned |
| Reflection | 失败或验证不足时反思并修复 | Planned |
| Critic/Reviewer | Worker 与独立 Reviewer 分工 | Planned |
| Multi-stage Pipeline | Analyze → Implement → Verify → Repair | Planned |
| Context Compression | 达到阈值后生成结构化摘要 | Planned |
| MCP Tools | 将部分工具改由 MCP 暴露 | Planned |

Benchmark 不是 Agent 架构，MCP 也不是推理策略。课程必须在相同 Task 上替换 Variant，
才能讨论策略的因果效果；不能用 ReAct 跑 Terminal-Bench、用 Reflection 跑 DABstep 后
直接比较总分。

## 4. 为什么不做全排列

若使用 8 个 Track、7 个 Variant、每题 3 次，课堂时间和 Bedrock 成本会迅速失控。实验
采用漏斗式评测：

```text
Qualification：单 Track、单题验证环境和评分器
       ↓
Core-6：少量代表题，快速比较全部可运行 Variant
       ↓
Broad：只让入选 Variant 跑跨领域正式集
       ↓
Hidden：讲师用未公开题验证迁移能力
```

不要求每名学员完整跑 SWE-bench Verified。长耗时 Track 可由讲师预热镜像、预计算
Baseline，课堂只运行指定 Task。

## 5. 第一版题目集合

### 5.1 Core 开发集

配置：

```text
evaluation/suites/agent-engineering-core.toml
```

| Track | Dataset | Task 数 | 状态 |
|---|---|---:|---|
| Terminal | `terminal-bench@2.0` | 2 | Ready |
| Data Analysis | `dabstep@1.0` | 2 | Spike |
| Tool Calling | `bfcl_parity@1.0` | 1 | Spike |
| Codebase QnA | `scale-ai/swe-atlas-qna@latest` | 1 | Planned |

Core 共 6 道候选题。`Ready` 表示已经可以进入课程 Baseline；`Spike` 表示数据集已在
Harbor registry 注册，但仍须验证当前 CLI Agent 的工具协议、任务输出和 verifier 是否
兼容；`Planned` 表示存在未解决的外部依赖，默认实验不运行。
Harbor Hub package 中的 Task selector 使用组织限定名，例如
`scale-ai/task-6905333b74f22949d97ba998`，不能省略 `scale-ai/`。

### 5.2 Broad 候选集

配置：

```text
evaluation/suites/agent-engineering-broad.toml
```

| Track | Dataset | 候选题数 |
|---|---|---:|
| Terminal | `terminal-bench@2.0` | 3 |
| Data Analysis | `dabstep@1.0` | 3 |
| Tool Calling | `bfcl_parity@1.0` | 3 |
| Software Engineering | `swebench-verified@1.0` | 2 |
| Observability | `otel-bench@1.0` | 2 |
| Codebase QnA | `scale-ai/swe-atlas-qna@latest` | 2 |

Broad 当前有 15 道候选题，不等于最终课堂题。每个 Track 完成 Qualification 后，根据
以下条件保留 1～3 题：

- Oracle 或官方参考 Agent 能稳定通过；
- Native Baseline 不是全对，也不是全错；
- 单题耗时适合课堂反馈；
- 不需要 GPU、浏览器或额外账号；
- 能区分至少两个 Variant；
- verifier 不产生明显偶然性。

最终建议为 10～12 道公开题，加 3～4 道讲师隐藏题。

### 5.3 第一轮 Qualification 结果

在 Native ReAct、Haiku 5.5、一次 Attempt 下得到：

| Track | 结果 | 判断 |
|---|---:|---|
| Terminal | `0/2` | 运行正常；两题对 Baseline 有挑战 |
| Data Analysis | `2/2` | 运行正常；当前样题区分度不足 |
| Tool Calling | `1/1` | 运行正常；当前样题区分度不足 |
| Codebase QnA | 未评分 | verifier 依赖外部 OpenAI-compatible Judge |

`Terminal = 0/2` 是任务失败，不是基础设施异常。DABstep 和 BFCL Parity 已验证与当前
CLI Adapter 兼容，但正式题应从数据集中重新挑选更有区分度的样本。

SWE-Atlas QnA 暂不进入课堂 Core 的可运行集合，状态由 `Spike` 调整为 `Planned`。

### 5.4 SWE-Atlas QnA 外部 Judge 依赖

该任务不是由我们的 Agent 调用 OpenAI。其 verifier 使用 `openai` Python SDK 进行
LLM-as-a-Judge，并声明：

```toml
[verifier.env]
EVAL_API_KEY = "${OPENAI_API_KEY}"
EVAL_BASE_URL = "${OPENAI_API_BASE}"
EVAL_MODEL = "${EVAL_MODEL:-anthropic/claude-opus-4-5-20251101}"
```

变量名表示 OpenAI-compatible 协议，不代表必须使用 OpenAI 官方模型。默认 Judge 是
Claude，说明任务预期连接 LiteLLM、OpenRouter 或其他兼容网关。Amazon Bedrock Converse
API 不能直接作为该脚本的 `OPENAI_API_BASE`。

当前候选题包含 9 条 rubric。verifier 对每条 rubric 分别调用 Judge，单条失败时最多重试
8 次，因此会引入：

- 第二套模型凭证与网络依赖；
- Agent 费用之外的 Judge 费用；
- Judge 模型版本带来的评分漂移；
- 较长且不稳定的反馈时间；
- Workshop 学员接触外部密钥的风险。

课程有三种后续选择：

1. 讲师统一提供受控的 OpenAI-compatible Judge 网关；
2. 复制任务并将 verifier 改为 Bedrock Judge，同时明确结果不再与官方分数严格可比；
3. 替换为规则型 verifier 的代码库理解任务。

在完成上述决策前，常用的 `--include-status ready --include-status spike` 不会运行
Codebase QnA。

## 6. SkillsBench 的处理

截至本规范版本，SkillsBench 可在 Harbor Hub 中查看，但不在 Harbor 0.24 默认读取的
公开 `registry.json` 中。因此第一版不写出虚假的：

```text
--dataset skillsbench@...
```

接入前完成一个 Compatibility Spike：

1. 确认任务来源、许可和版本；
2. 确认是否能转换为 Harbor Task 目录；
3. 明确 Skill 以何种方式注入 Agent；
4. 检查任务是否会把目标 Skill 内容直接泄露给 Agent；
5. 用“无 Skill / 正确 Skill / 干扰 Skill”三组做区分度预演；
6. 通过后再加入 Core 或 Broad manifest。

Harbor CLI 的 `--skill` 能为部分内置 Agent 注入 Skill，但自研 CLI Agent 是否能使用该
参数取决于 Adapter 和生产 Agent 的实现，不能只靠命令行开关自动获得 Skill 能力。

## 7. MCP Track 的处理

MCP Track 采用课程自建任务，不与某个外部 Benchmark 强绑定。建议至少包含：

1. 工具发现：从多个相似工具中选择正确工具；
2. 参数约束：枚举、分页、日期和标识符；
3. 资源读取：先读取 MCP Resource，再调用工具；
4. 错误恢复：处理超时、无权限和暂时性失败；
5. Prompt Injection：工具返回内容不得改变系统目标。

对照实验：

| Variant | 工具通道 |
|---|---|
| A | 当前 JSONL `shell` 工具 |
| B | 等价能力的 MCP Server |
| C | MCP + Tool Skill |

三组使用相同底层数据和 verifier，避免把任务差异误认为协议差异。

## 8. Variant 实现约束

### 8.1 公平性固定项

- 模型与 Region；
- 每次模型调用的最大输出；
- Trial 总 token 或总调用预算；
- 可见工具和环境权限；
- Task 与 Attempts；
- 超时和并发；
- verifier；
- 初始 system policy 中的安全约束。

### 8.2 可变项

- 控制流；
- Prompt 模板；
- 是否生成计划；
- 是否触发 Reflection；
- Reviewer 的输入和输出；
- 上下文保留、裁剪和压缩；
- Skill 选择方式；
- MCP 与原生 Tool transport；
- 子 Agent 数量和分工。

### 8.3 禁止的混杂

- Plan-and-Execute 获得额外工具，而 ReAct 没有；
- Reflection 获得更高 token 预算；
- Reviewer 直接读取 verifier 或参考答案；
- 某 Variant 按 Task 名称加载专用答案；
- 不同 Variant 使用不同模型后仍将差异归因于 Agent 架构。

## 9. 运行方式

### 9.1 查看默认可运行矩阵

```bash
uv run agent-engineering-eval --list
```

默认只选择 `status = "ready"` 的 Track 和 ReAct Baseline，不会误跑尚未验证的 Spike。

### 9.2 查看 Core 全部候选命令

```bash
uv run agent-engineering-eval \
  --suite evaluation/suites/agent-engineering-core.toml \
  --include-status ready \
  --include-status spike \
  --dry-run
```

### 9.3 运行单个 Qualification Track

```bash
uv run agent-engineering-eval \
  --suite evaluation/suites/agent-engineering-core.toml \
  --include-status spike \
  --include-track data-analysis \
  --variant evaluation/variants/react-baseline.toml \
  --attempts 1 \
  --n-concurrent 1
```

### 9.4 比较多个已实现 Variant

```bash
uv run agent-engineering-eval \
  --suite evaluation/suites/agent-engineering-core.toml \
  --include-status ready \
  --variant evaluation/variants/react-baseline.toml \
  --variant evaluation/variants/reflection.toml
```

在 Reflection Adapter 实现前，该命令会拒绝真实执行；`--list` 和 `--dry-run` 仍可用于
检查实验矩阵。

## 10. 结果结构

每个 Track 是独立 Harbor Job：

```text
evaluation/agent-jobs/<timestamp>/
├── react-baseline/
│   ├── terminal/
│   ├── data-analysis/
│   └── tool-calling/
└── agent-engineering-summary.json
```

总表按 Variant 汇总：

- Track 加权平均 reward；
- Trials 和异常数；
- 输入、输出及总 token；
- 各 Track 原始 Harbor result 路径。

不同 Benchmark 的 reward 含义可能不同，因此总分只用于导航。架构结论必须同时报告
各 Track 分数，不能只报告一个混合平均值。

## 11. 正式实验指标

### 11.1 主指标

- 每 Track mean reward；
- 完全通过 Trial 数；
- `pass@3` 或三次 Attempts 平均；
- 异常率。

### 11.2 效率指标

- 输入、输出和缓存 token；
- 模型调用次数；
- Tool 调用次数；
- 无效 Tool 调用数；
- 总耗时和 P50/P95；
- 峰值上下文长度。

### 11.3 行为指标

- 首次失败后是否恢复；
- 是否在完成前执行验证；
- 计划偏离次数；
- Reflection 是否产生有效改动；
- Reviewer 建议采纳率；
- 压缩前后关键信息保留率；
- Skill 选择准确率；
- MCP 工具选择及参数正确率。

当前 Harbor 汇总只覆盖部分指标。下一实施阶段需增强 Agent trace，记录脱敏后的 Tool
名称、参数摘要、结果状态、上下文大小、计划/反思事件和完成原因。

## 12. 学员实验形式

每组选择一个主变量，不要求同时实现全部架构。

### 实验 1：ReAct Baseline 与失败画像

讲师提供：

- 可运行 Agent；
- Core suite；
- Harbor 环境；
- 结果分析模板。

学员完成：

- 跑 Baseline；
- 从轨迹中给失败分类；
- 提出一个单变量改动；
- 预测哪些 Track 会受益或退化。

### 实验 2：控制流对比

可选 Plan-and-Execute、Reflection 或 Critic/Reviewer。

学员完成：

- 写状态转移或阶段契约；
- 固定总预算；
- 实现终止和失败恢复条件；
- 在 Core 上做 A/B；
- 解释收益来自哪里，而非只报告分数。

### 实验 3：上下文与 Skill

学员完成：

- 设计上下文保留规则；
- 实现压缩或 Skill 注入之一；
- 加入长轨迹压力测试；
- 检查压缩后约束、文件路径和未完成事项是否保留。

### 实验 4：MCP 工具

学员完成：

- 将一组等价工具改为 MCP Server；
- 设计 Tool 描述和错误语义；
- 对比 JSONL Tool 与 MCP；
- 分析协议开销、发现能力和可移植性。

### 实验 5：Broad Gate

讲师运行入选 Variant 的 Broad 集和隐藏集。学员提交：

- 代码 commit；
- Variant 配置；
- 实验表；
- 已知失败模式；
- 是否发布的 Gate 决策。

## 13. 实施阶段

### Phase 1：评测骨架

- 独立 suite runner；
- TOML suite 与 variant schema；
- Core/Broad 候选集；
- `--list`、`--dry-run`、Track 过滤；
- 跨 Track 汇总；
- 不影响 DevOps 比赛。

### Phase 2：Qualification

- 为 DABstep、BFCL Parity 重新选择有区分度的样本；
- 暂停 SWE-Atlas QnA，直到确定统一 Judge 方案或替代任务；
- 记录兼容性、耗时和 Baseline；
- 调整题目而不调整 Agent；
- Qualified 后将 Track 从 `spike` 改为 `ready`。

### Phase 3：控制流 Variant

- 抽取 Strategy 接口；
- 实现 Plan-and-Execute；
- 实现 Reflection；
- 实现 Critic/Reviewer；
- 增加预算守恒测试。

### Phase 4：Context、Skill 与 MCP

- 增强轨迹；
- 上下文压缩；
- SkillsBench compatibility adapter；
- 自建 MCP Track；
- Prompt Injection 与错误恢复题。

### Phase 5：课程冻结

- 形成 10～12 道公开题；
- 形成 3～4 道讲师隐藏题；
- 三次 Attempts 预演；
- 固定镜像、版本和评分规则；
- 生成学员手册和讲师运行手册。

## 14. 第一版验收标准

- `devopsagent-eval` 的行为和测试保持不变；
- 新 runner 默认不执行 Spike；
- Core manifest 可加载并列出 6 道候选题；
- Broad manifest 可加载并列出 15 道候选题；
- planned Variant 不可误执行；
- dry-run 命令包含正确 Dataset、Task、Adapter 和预算；
- 跨 Track 汇总按权重计算；
- 所有既有测试与新增测试通过；
- Ruff 检查通过。
