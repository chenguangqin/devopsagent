# Agent Engineering 学员实验操作手册

## 1. 手册说明

本手册面向参加 AI Agent 开发课程的学员，目标不是完成一个固定答案，而是完成一次可复现的
Agent 工程实验：

```text
运行 Baseline
→ 阅读轨迹
→ 提出失败假设
→ 只改变一个主要变量
→ 在相同任务和预算下复测
→ 根据证据决定保留或回退
```

当前必做范围：

- Native Bedrock Agent；
- ReAct 风格 Agent Loop；
- Terminal-Bench；
- DABstep；
- BFCL Parity；
- Harbor 结果和轨迹分析；
- 单变量 A/B 实验。

当前不作为学员必做内容：

- SWE-Atlas QnA：评分器需要额外的 OpenAI-compatible Judge；
- SWE-bench Verified 和 OTel-Bench：尚未完成课堂 Qualification；
- Plan-and-Execute、Reflection、Critic、Pipeline、Context Compression 和 MCP：
  配置已经预留，Adapter 尚未实现。

不要尝试真实运行状态为 `planned` 的 Variant。

## 2. 学习目标

完成实验后，你应能够：

1. 解释模型、Agent Loop、Tool、Harbor Adapter、Task Environment 和 Verifier 的边界；
2. 独立运行一个 CLI Agent，并使用 Harbor 对它评分；
3. 区分任务失败、Agent 异常和评测基础设施异常；
4. 从轨迹判断失败发生在探索、执行、验证还是终止阶段；
5. 设计一个控制变量实验，而不是同时修改多个组件；
6. 同时使用 reward、稳定性、token 和运行时间评价改动；
7. 给出“发布、继续实验或回退”的工程决策。

## 3. 时间与产出

建议实验时间为 3.5～4.5 小时。

| 阶段 | 建议时间 | 主要产出 |
|---|---:|---|
| Lab 0：环境检查 | 20 分钟 | 环境检查结果 |
| Lab 1：理解 Agent Loop | 30 分钟 | 架构图和调用链说明 |
| Lab 2：运行 Baseline | 45 分钟 | Baseline 结果表 |
| Lab 3：失败诊断 | 40 分钟 | 失败分类与证据 |
| Lab 4：单变量改造 | 60～90 分钟 | 代码/配置和实验假设 |
| Lab 5：A/B 复测 | 45 分钟 | 对照结果与决策 |

每组最终提交：

- Git commit；
- Variant 配置；
- 一份实验记录；
- Baseline 与改造后结果路径；
- 一页结论：改了什么、为什么、在哪些任务上有效、代价是什么。

实验记录模板：

```text
docs/templates/EXPERIMENT_RECORD.md
```

## 4. 实验规则

### 4.1 固定变量

除非讲师明确要求，以下项目保持不变：

| 变量 | 固定值 |
|---|---|
| Model | `global.anthropic.claude-haiku-5-5` |
| Region | `us-west-2` |
| Environment | Docker |
| Max steps | 40 |
| Max tokens/call | 4096 |
| Tool timeout | 300 秒 |
| Attempts | 开发阶段 1 次 |
| Concurrent trials | 1 |

### 4.2 每轮只改变一个主要变量

允许的单变量示例：

- System Prompt 中的完成条件；
- Tool 描述；
- Tool 输出裁剪方式；
- 完成前验证策略；
- 失败后的有限重试；
- 上下文保留或压缩策略；
- 显式 Plan；
- Reviewer。

第一轮不要同时修改 Prompt、Loop、Tool Schema 和模型参数，否则无法判断分数变化来自哪里。

### 4.3 禁止事项

- 根据 Task 名称写专用答案；
- 匹配 instruction 文本后输出预制命令；
- 读取 Task 的 `tests/`、`solution/`、verifier 或参考答案；
- 修改 Benchmark Task 和评分器；
- 使用不同模型后将差异归因于 Agent 架构；
- 只报告总分，不保留逐题结果和失败证据。

## 5. Lab 0：环境检查

### 5.1 获取最新代码

```bash
cd /home/ec2-user/workspace/my-workspace/devopsagent
git pull --ff-only origin main
git status --short
```

验收：

- 当前分支为课程指定分支；
- `git status --short` 没有意外修改。

### 5.2 安装依赖

```bash
uv sync --all-extras
```

该命令安装 Native、LangChain、Strands、Harbor 和开发检查工具。

### 5.3 检查基础设施

```bash
docker --version
docker compose version
docker buildx version
docker info
uv run harbor --version
```

课程已验证版本：

```text
Docker Compose v5.6.0
Docker Buildx v0.36.0
Harbor 0.24.0
```

### 5.4 检查 AWS 与 Bedrock

```bash
aws sts get-caller-identity
uv run python scripts/check_bedrock.py
```

预期：

```text
Bedrock connection works
```

### 5.5 检查课程工程

```bash
uv run pytest -q
uv run ruff check .
```

记录：

- Python/Harbor 版本；
- Docker/Compose/Buildx 版本；
- AWS Account；
- 测试结果；
- 是否存在网络或镜像拉取问题。

如果本节未通过，不要进入正式评测。

## 6. Lab 1：理解 Agent 调用链

### 6.1 阅读以下文件

```text
src/devopsagent/cli.py
src/devopsagent/runners/native.py
src/devopsagent/loop.py
src/devopsagent/tools.py
src/devopsagent/protocol.py
evaluation/harbor_adapter.py
```

回答以下问题：

1. Bedrock 模型在哪里调用？
2. Agent Loop 在什么条件下继续下一步？
3. `shell` Tool 的 Schema 在哪里定义？
4. 为什么生产 Agent 不需要 import Harbor？
5. shell 命令最终在哪里执行？
6. reward 由 Agent、Adapter 还是 Verifier 计算？

### 6.2 独立运行 CLI

先在 Harbor 之外验证 Agent：

```bash
mkdir -p /tmp/devopsagent-student-lab

uv run devopsagent-native \
  --protocol local \
  --workdir /tmp/devopsagent-student-lab \
  --max-steps 8 \
  --instruction "创建 hello.txt，写入 hello-agent，然后读取文件验证内容"
```

检查：

```bash
ls -la /tmp/devopsagent-student-lab
cat /tmp/devopsagent-student-lab/hello.txt
```

验收：

- Agent 能调用 Bedrock；
- Agent 能生成 Tool Call；
- 本地 Tool Client 能执行命令；
- 文件内容正确；
- stderr 中能看到状态、步骤、Tool Call 和 token。

### 6.3 画出边界

在实验记录中补全：

```text
Task instruction
  → Harbor Adapter
  → Agent CLI
  → Bedrock
  → Tool Call
  → Harbor Environment
  → Docker container
  → Verifier
  → Reward
```

## 7. Lab 2：运行 ReAct Baseline

### 7.1 查看评测矩阵

```bash
uv run agent-engineering-eval --list
```

默认只显示 `ready` Track。

查看 Ready 和 Spike：

```bash
uv run agent-engineering-eval \
  --include-status ready \
  --include-status spike \
  --list
```

当前应看到：

- Terminal：2 题；
- Data Analysis：2 题；
- Tool Calling：1 题。

Codebase QnA 是 `planned`，不会出现在该命令中。

### 7.2 Dry Run

```bash
uv run agent-engineering-eval \
  --include-status ready \
  --include-status spike \
  --dry-run
```

`--dry-run` 只打印 Harbor 命令，不会：

- 下载镜像；
- 启动 Docker；
- 调用 Bedrock；
- 执行 Agent；
- 产生评分。

在运行前检查：

- Dataset；
- Task selector；
- Agent Adapter；
- Model；
- Max steps；
- Attempts；
- Concurrent trials。

### 7.3 分 Track 运行 Baseline

先运行 Terminal：

```bash
uv run agent-engineering-eval \
  --include-status ready \
  --include-track terminal \
  --attempts 1 \
  --n-concurrent 1
```

再运行 DABstep：

```bash
uv run agent-engineering-eval \
  --include-status spike \
  --include-track data-analysis \
  --attempts 1 \
  --n-concurrent 1
```

最后运行 BFCL Parity：

```bash
uv run agent-engineering-eval \
  --include-status spike \
  --include-track tool-calling \
  --attempts 1 \
  --n-concurrent 1
```

首次实验分开运行，便于定位镜像、任务协议或 verifier 问题。环境稳定后可一次运行：

```bash
uv run agent-engineering-eval \
  --include-status ready \
  --include-status spike \
  --attempts 1 \
  --n-concurrent 1
```

### 7.4 已知参考结果

Native ReAct、Haiku 5.5、一次 Attempt 的首轮结果：

| Track | 参考结果 | 说明 |
|---|---:|---|
| Terminal | `0/2` | 两道挑战题均失败，但环境运行正常 |
| Data Analysis | `2/2` | 当前样题较简单 |
| Tool Calling | `1/1` | 当前样题较简单 |

你的结果可能因模型随机性不同。参考结果不是标准答案。

## 8. Lab 3：读取结果和诊断失败

### 8.1 找到最近一次运行

```bash
RUN_DIR=$(find evaluation/agent-jobs \
  -mindepth 1 -maxdepth 1 -type d \
  | sort | tail -1)

echo "$RUN_DIR"
find "$RUN_DIR" -maxdepth 4 -name result.json -print
```

一次完整运行的结构类似：

```text
evaluation/agent-jobs/<timestamp>/
├── react-baseline/
│   ├── terminal/
│   ├── data-analysis/
│   └── tool-calling/
└── agent-engineering-summary.json
```

### 8.2 查看跨 Track 汇总

```bash
jq . "$RUN_DIR/agent-engineering-summary.json"
```

字段含义：

| 字段 | 含义 |
|---|---|
| `weighted_mean` | 已成功评分 Track 的加权平均 |
| `scored_tracks` | 实际得到评分的 Track 数 |
| `infra_failures` | Dataset、环境或 verifier 等基础设施失败数 |
| `trials` | 已完成 Trial 数 |
| `errors` | Harbor 记录的异常 Trial 数 |
| `input_tokens` | Agent 输入 token |
| `output_tokens` | Agent 输出 token |

只有在 `infra_failures = 0` 且所有预期 Track 都已评分时，才能把 `weighted_mean` 当作完整
实验结果。

### 8.3 查看逐题结果

选择某个 Track：

```bash
JOB_DIR="$RUN_DIR/react-baseline/terminal"

printf 'task\treward\tstatus\tsteps\ttools\tinput\toutput\n'

for RESULT in "$JOB_DIR"/*/result.json; do
  jq -r '[
    .task_name,
    (.verifier_result.rewards.reward // "NA"),
    (.agent_result.metadata.status // "NA"),
    (.agent_result.metadata.steps // "NA"),
    (.agent_result.metadata.tool_calls // "NA"),
    (.agent_result.n_input_tokens // 0),
    (.agent_result.n_output_tokens // 0)
  ] | @tsv' "$RESULT"
done | column -t -s $'\t'
```

### 8.4 查看 Agent 轨迹

列出 Agent 产物：

```bash
find "$JOB_DIR" -path '*/agent/agent-result.json' -print
find "$JOB_DIR" -path '*/agent/agent-stderr.log' -print
```

查看某条轨迹：

```bash
AGENT_RESULT=$(find "$JOB_DIR" \
  -path '*/agent/agent-result.json' \
  | sort | head -1)

jq . "$AGENT_RESULT"
```

当前轨迹记录：

- Step；
- Stop reason；
- 模型文本；
- Tool 名称；
- 总步骤；
- Tool Call 数；
- token；
- 最终状态。

当前版本不会完整记录 Tool 参数和 Tool 输出，这是需要改进的可观测性缺口。

### 8.5 区分三类结果

#### A. Reward 为 0，Exceptions 为 0

含义：

- Agent 正常结束；
- Verifier 正常运行；
- 交付结果不满足要求。

这是任务失败，应分析 Agent 行为。

#### B. Trial Exception

可能原因：

- Agent CLI 崩溃；
- Bedrock 权限或限流；
- Tool 超时；
- Docker 环境异常；
- Verifier 异常。

这不是普通的任务失败。

#### C. `infra_failures > 0`

可能原因：

- Dataset 名称或版本错误；
- Task selector 不存在；
- 缺少 verifier 环境变量；
- 镜像无法拉取；
- 外部 Judge 不可用。

不要把基础设施失败计算为 Agent 分数。

### 8.6 失败分类

对每个失败 Trial 选择一个主要类别：

| 类别 | 典型表现 |
|---|---|
| 探索不足 | 未查看关键文件、配置或测试入口 |
| 假设错误 | 过早决定根因，未收集证据 |
| Tool 使用错误 | 命令、路径、cwd 或参数错误 |
| 输出淹没 | 大量 Tool 输出挤占上下文 |
| 执行不完整 | 找到方案但没有真正修改环境 |
| 验证不足 | 修改后没有运行针对性检查 |
| 过早终止 | 一次失败后直接给出最终回答 |
| 步骤耗尽 | 到达 `max_steps` |
| 上下文丢失 | 忘记任务约束、路径或未完成事项 |
| Verifier/环境 | Agent 外部问题 |

每个判断必须引用至少一条轨迹证据。

## 9. Lab 4：设计单变量改造

### 9.1 写实验假设

先填写实验记录，不要立即改代码：

```text
观察：
失败发生在……

假设：
如果增加/修改……，Agent 将在……阶段改善。

预测：
Terminal 的……任务可能提升；
DABstep/BFCL 可能不变或产生……代价。

主要变量：
本轮只改变……
```

### 9.2 方案 A：只修改 System Prompt

复制 Baseline Variant：

```bash
cp evaluation/variants/react-baseline.toml \
  evaluation/variants/student-react.toml
```

编辑为：

```toml
[variant]
id = "student-react"
title = "Student ReAct experiment"
status = "ready"
agent = "evaluation.harbor_adapter:NativeCliHarborAgent"

[agent_kwargs]
system_prompt = """
You are an agent operating in an isolated benchmark environment.
Inspect the environment before choosing a solution.
Act on the environment instead of only explaining.
Before finishing, verify the requested behavior and inspect the produced artifacts.
Do not read benchmark tests, verifier files, or reference solutions.
"""
```

注意：

- 这是 Prompt 实验，不要同时修改 `loop.py`；
- 不要在 Prompt 中出现 Task 名称或任务答案；
- Prompt 可以要求验证，但不应泄露 verifier。

### 9.3 方案 B：修改 Agent Loop

核心文件：

```text
src/devopsagent/loop.py
```

可选择一个方向：

- 完成前增加一次有限验证阶段；
- Tool 失败后允许一次结构化恢复；
- 增加显式的 `observe → decide → act` 状态；
- 对过早终止增加一次确认；
- 在达到步骤预算前预留验证步骤。

设计要求：

- 有明确终止条件；
- 不允许无限重试；
- 不根据 Task 名称分支；
- 总预算与 Baseline 相同；
- 新增行为能在轨迹中被识别。

### 9.4 方案 C：修改 Tool 设计

核心文件：

```text
src/devopsagent/tools.py
src/devopsagent/protocol.py
```

可选择一个方向：

- 改善 `shell` Tool 描述；
- 对长输出保留头部和尾部，而非只保留头部；
- 为超时和非零退出码提供更可操作的错误摘要；
- 提醒 Agent 使用 `cwd`，减少长路径命令；
- 增加受控的文件读取 Tool，与通用 shell 做对照。

不要扩大宿主机权限，也不要让 Agent 读取 Harbor verifier。

### 9.5 修改后先做本地检查

```bash
uv run pytest -q
uv run ruff check .

uv run devopsagent-native \
  --protocol local \
  --workdir /tmp/devopsagent-student-lab \
  --max-steps 8 \
  --instruction "检查当前目录，创建 result.txt 写入 verified，并确认文件内容"
```

只有本地检查通过后才进入 Harbor A/B。

## 10. Lab 5：A/B 复测

### 10.1 同时运行 Baseline 和学生 Variant

```bash
uv run agent-engineering-eval \
  --include-status ready \
  --include-track terminal \
  --variant evaluation/variants/react-baseline.toml \
  --variant evaluation/variants/student-react.toml \
  --attempts 1 \
  --n-concurrent 1
```

如果修改发生在共享的 `loop.py`，Baseline Adapter 也会使用修改后的代码，不能形成真正的
A/B。此时应采用以下方式之一：

1. 用 Git commit 分别运行并保存结果；
2. 为新策略建立独立 Runner/Adapter；
3. 使用 Git worktree 准备 Baseline 和 Experiment 两份代码。

只修改 Variant Prompt 时，可以在同一代码版本中直接比较。

### 10.2 扩展到跨场景验证

Prompt/策略在 Terminal 上改善后，再运行 DABstep 和 BFCL：

```bash
uv run agent-engineering-eval \
  --include-status spike \
  --include-track data-analysis \
  --include-track tool-calling \
  --variant evaluation/variants/react-baseline.toml \
  --variant evaluation/variants/student-react.toml \
  --attempts 1 \
  --n-concurrent 1
```

需要回答：

- Terminal 提升是否以 DABstep/BFCL 退化为代价？
- Token 是否显著增加？
- Tool Call 是否增加但没有提高 reward？
- 改动是否只对某一类失败有效？

### 10.3 稳定性复测

只有单次结果显示有希望时，才运行三次 Attempts：

```bash
uv run agent-engineering-eval \
  --include-status ready \
  --include-track terminal \
  --variant evaluation/variants/react-baseline.toml \
  --variant evaluation/variants/student-react.toml \
  --attempts 3 \
  --n-concurrent 1
```

单次成功可能是随机波动。至少比较：

- mean reward；
- full reward trials；
- 异常数；
- 输入/输出 token；
- 总耗时。

## 11. 实验决策

### 11.1 建议保留

满足以下大部分条件：

- 主要目标 Track 有稳定提升；
- 保留 Track 没有明显退化；
- 没有新增基础设施异常；
- Token 和耗时增长可接受；
- 改动能解释，且不是 Task 特化；
- 隐藏任务上仍能迁移。

### 11.2 继续实验

适用于：

- 单次提升但三次结果不稳定；
- Reward 不变但行为明显改善；
- 某类任务提升、另一类任务退化；
- 成本增长过高；
- 轨迹不足以确认因果链。

### 11.3 回退

适用于：

- 只对某个已知 Task 有效；
- 引入无限循环或大量无效 Tool Call；
- Token 显著增加但 reward 不变；
- 基础任务出现回归；
- 修改绕过或依赖 verifier。

## 12. 提交要求

### 12.1 代码

```bash
git status --short
git diff --check
uv run pytest -q
uv run ruff check .
git log -1 --oneline
```

提交中不要包含：

- `evaluation/agent-jobs/`；
- 下载的 Benchmark 镜像或任务副本；
- AWS/OpenAI/API 密钥；
- `.env`；
- Harbor 缓存；
- 临时分析文件。

### 12.2 实验记录

复制模板：

```bash
cp docs/templates/EXPERIMENT_RECORD.md \
  experiment-record.md
```

至少填写：

- 假设；
- 固定变量；
- 主要改动；
- Baseline 和 Experiment commit；
- 完整运行命令；
- 逐 Track/逐 Task 结果；
- Token 和异常；
- 两条以上轨迹证据；
- 是否发布的结论。

### 12.3 最终陈述

用三分钟回答：

1. Baseline 为什么失败？
2. 你改变了哪个变量？
3. 哪个证据支持你的解释？
4. 哪些任务没有改善？
5. 如果再做一轮，你会验证什么？

## 13. 常见问题

### 13.1 命令瞬间结束

检查是否使用了：

```text
--dry-run
```

Dry Run 不执行评测。

### 13.2 Mean 为 0，但 Exceptions 为 0

环境和评分器正常，Agent 没有通过任务。分析轨迹，不要重装 Harbor。

### 13.3 `compose build requires buildx 0.17.0 or later`

Buildx 版本过旧。课程验证版本为 `v0.36.0`，参考：

```text
docs/EXPERIMENT_ENVIRONMENT_SETUP_SPEC.md
```

### 13.4 缺少 `OPENAI_API_KEY`

说明选中了使用外部 LLM Judge 的任务，例如 SWE-Atlas QnA。该 Track 当前为 `planned`，
不是学员必做项。不要自行申请或共享外部密钥。

### 13.5 某个任务运行很久

在另一个终端查找最新 Trial：

```bash
find evaluation/agent-jobs -maxdepth 5 \
  \( -name trial.log -o -name job.log \) \
  -type f -print
```

查看末尾日志：

```bash
tail -n 80 <trial.log-path>
```

不要在 verifier 正常运行时重复启动同一任务。

### 13.6 Bedrock 报权限或模型错误

重新检查：

```bash
aws sts get-caller-identity
uv run python scripts/check_bedrock.py
```

确认 Region 为 `us-west-2`，Model ID 为：

```text
global.anthropic.claude-haiku-5-5
```

### 13.7 分数下降是否代表改动无效

不一定。先检查：

- 是否是相同 Task、模型和预算；
- 是否发生基础设施失败；
- 是否只运行了一次；
- 是否修复了一种失败但引入另一种失败；
- 是否降低了 token 或异常率。

最终结论必须来自多次 Attempts 和跨 Track 结果。

## 14. 扩展实验入口

以下配置用于课程后续阶段，目前只能 `--list` 或 `--dry-run`：

```text
evaluation/variants/plan-and-execute.toml
evaluation/variants/reflection.toml
evaluation/variants/critic-reviewer.toml
evaluation/variants/pipeline.toml
evaluation/variants/context-compression.toml
evaluation/variants/mcp-tools.toml
```

示例：

```bash
uv run agent-engineering-eval \
  --variant evaluation/variants/reflection.toml \
  --include-status ready \
  --dry-run
```

Adapter 实现并通过课程验收后，讲师会将对应 Variant 的状态改为 `ready`。
