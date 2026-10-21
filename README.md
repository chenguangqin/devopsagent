# DevOpsAgent Workshop

这是一个面向 Agent 开发课程的 Harbor 评测工程。它提供三个功能等价、实现技术不同的
DevOps Agent：

- `native`：直接基于 Amazon Bedrock Converse API 实现 agent loop；
- `langchain`：基于 LangChain `create_agent`；
- `strands`：基于 Strands Agents SDK。

三者统一以 CLI 运行，生产代码不依赖 Harbor。目前不实现 ACP 协议。

此外，Iteration 1 提供了 SDK 无关的 Generic Command Adapter。它可以直接评测一个
完整外部 Agent，而不在评测工程内重建其 Model、Prompt、Loop、Tools、MCP、Skills 或
Memory。Descriptor、Variant、Attempt 状态隔离和 Deadline 规则见
[`docs/COMMAND_AGENT_EVALUATION.md`](docs/COMMAND_AGENT_EVALUATION.md)。

## 架构

```text
                         production boundary
┌─────────────────────────────────────────────────────────────┐
│ devopsagent-native | devopsagent-langchain | ...            │
│         model → agent loop → JSONL tool call                │
└──────────────────────────────┬──────────────────────────────┘
                               │ stdin/stdout
                    ┌──────────┴──────────┐
                    │                     │
             local tool client     Harbor adapter
                    │                     │
             local subprocess      BaseEnvironment.exec()
                                          │
                                   isolated Trial container
```

关键边界：

- `src/devopsagent/` 中没有任何 Harbor import；
- Agent 调用模型发生在宿主机，可直接使用 EC2 instance profile；
- Harbor 只存在于 `evaluation/`，负责启动黑盒 CLI 并转发工具调用；
- 同一个 Agent CLI 不经过 Harbor 也可以在本地目录运行。

## 安装

Python 3.12+，使用 `uv`：

```bash
# 只安装原生 Bedrock Agent
uv sync

# 安装某一种框架
uv sync --extra langchain
uv sync --extra strands

# 课程评测机：三个 Agent + Harbor + 开发工具
uv sync --all-extras
```

评测机还需要 Docker、Docker Compose 和 Buildx。

完整的 AWS Workshop 环境搭建、版本固定、Bedrock 权限、Harbor Smoke Test 和故障处理见
[`docs/EXPERIMENT_ENVIRONMENT_SETUP_SPEC.md`](docs/EXPERIMENT_ENVIRONMENT_SETUP_SPEC.md)。

## 独立运行 CLI

CLI 的本地模式会把 shell 工具绑定到指定工作目录：

```bash
uv run devopsagent-native \
  --protocol local \
  --workdir /tmp/agent-work \
  --instruction "创建 hello.txt，写入 hello，并验证内容"

uv run devopsagent-langchain \
  --protocol local \
  --workdir /tmp/agent-work \
  --instruction "检查当前目录并生成目录清单"

uv run devopsagent-strands \
  --protocol local \
  --workdir /tmp/agent-work \
  --instruction "创建并运行一个输出 ok 的 shell 脚本"
```

公共参数包括：

| 参数 | 默认值 |
|---|---|
| `--model-id` | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `--region` | `us-west-2` |
| `--max-steps` | `12` |
| `--max-tokens` | `4096` |
| `--system-prompt` | 内置 DevOps 提示词 |

## Harbor 评测

先验证适配器参数：

```bash
uv run harbor agent schema evaluation.harbor_adapter:NativeCliHarborAgent
uv run harbor agent schema evaluation.harbor_adapter:LangChainCliHarborAgent
uv run harbor agent schema evaluation.harbor_adapter:StrandsCliHarborAgent
```

单独评测一个 Agent：

```bash
uv run harbor run \
  -p examples/tasks/hello-devopsagent \
  -a evaluation.harbor_adapter:NativeCliHarborAgent \
  -m global.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --ak region=us-west-2 \
  --ak max_steps=8 \
  --ak max_tokens=2048 \
  -e docker
```

将类名替换为 `LangChainCliHarborAgent` 或 `StrandsCliHarborAgent` 即可评测另外两种
实现。

### 三 Agent 对比

评测矩阵会对相同任务或数据集依次执行三个 Agent，并输出分数、异常数和 token：

```bash
uv run python -m evaluation.run_matrix \
  --path examples/tasks/hello-devopsagent \
  --model-id global.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --region us-west-2 \
  --max-steps 8
```

也可以使用等价入口 `uv run devopsagent-eval ...`。

评测数据集：

```bash
uv run python -m evaluation.run_matrix \
  --dataset <dataset-name>@<version> \
  --attempts 3 \
  --n-concurrent 2
```

结果保存在 `evaluation/jobs/<timestamp>/`，其中每个 engine 有独立的 Harbor Job，
总表写入 `matrix-summary.json`。

## 通用外部 Agent 评测

外部 Agent 使用 Descriptor v0.2 和 Variant v0.2 接入。评测器从 Variant 固定的 Git
commit 创建只读语义的 source snapshot，再为每个 attempt 建立独立副本；运行产生的
Memory、Reports、Result 和 Artifact 不会回写源仓库，也不会流入另一个 attempt。

```bash
uv run command-agent-eval \
  --variant path/to/baseline.toml \
  --task-id case-001 \
  --instruction "生成分析报告" \
  --attempts 2 \
  --n-concurrent 2
```

仓库中的确定性 Agent 夹具用于验证完整边界。`demomcp` 的最小 shim 和 Descriptor
模板位于 `evaluation/spikes/demomcp/`，Evaluation Core 本身不 import Strands。

### 无 Docker 的 Harbor Smoke Test

Harbor 0.24 没有内置 host environment。本仓库提供
`evaluation.host_environment:TrustedHostEnvironment`，仅用于运行仓库内可信任务：

```bash
uv run harbor run \
  --path examples/tasks/hello-host-harbor \
  --agent evaluation.harbor_adapter:NativeCliHarborAgent \
  --model us.anthropic.claude-sonnet-4-6 \
  --env evaluation.host_environment:TrustedHostEnvironment \
  --n-concurrent 1 \
  --yes
```

该环境将 Harbor 的虚拟路径映射到 Trial 临时目录，不启动 Docker，也不提供容器、
网络或资源隔离，禁止用于学员提交和正式评测。

### Terminal-Bench 正式任务子集

课程首轮建议从 `terminal-bench-sample@2.0` 中选择以下五个任务：

| 任务 | 主要能力 |
|---|---|
| `log-summary-date-ranges` | 日志探索、边界日期、精确 CSV |
| `sqlite-with-gcov` | 源码构建、编译参数、PATH、验证 |
| `configure-git-webserver` | Git hook、Web 服务、后台进程 |
| `fix-code-vulnerability` | 代码诊断、CWE、修复、测试 |
| `polyglot-c-py` | 复杂约束下的跨语言实现 |

先只运行 native Agent，确认任务镜像、权限和超时配置：

```bash
uv run devopsagent-eval \
  --dataset terminal-bench-sample@2.0 \
  --engines native \
  --include-task log-summary-date-ranges \
  --include-task sqlite-with-gcov \
  --include-task configure-git-webserver \
  --include-task fix-code-vulnerability \
  --include-task polyglot-c-py \
  --max-steps 30 \
  --tool-timeout-seconds 300 \
  --n-concurrent 1
```

基础设施跑通后，移除 `--engines native` 即可用三个 Agent 跑同一任务集。任务清单也
保存在 `evaluation/presets/terminal-bench-course.txt`。

### 学员 Agent 改造赛

比赛采用 7 道公开开发题和 3 道讲师隐藏题。赛题结构、计分、预演及防过拟合规则见
[`docs/COMPETITION_TASK_SUITE.md`](docs/COMPETITION_TASK_SUITE.md)。

```bash
uv run devopsagent-eval \
  --dataset terminal-bench@2.0 \
  --preset evaluation/presets/terminal-bench-competition.txt \
  --engines native \
  --max-steps 40 \
  --tool-timeout-seconds 300 \
  --n-concurrent 2
```

### 多场景 Agent Engineering 实验

跨 Terminal、数据分析、工具调用、软件工程和可观测性的独立实验见
[`docs/AGENT_ENGINEERING_EVALUATION_SPEC.md`](docs/AGENT_ENGINEERING_EVALUATION_SPEC.md)。
该实验使用 `agent-engineering-eval`、独立 suite/variant 配置和结果目录，不改变上面的
DevOps 比赛。

学员应从
[`docs/STUDENT_LAB_MANUAL.md`](docs/STUDENT_LAB_MANUAL.md)
开始操作，并使用
[`docs/templates/EXPERIMENT_RECORD.md`](docs/templates/EXPERIMENT_RECORD.md)
记录每轮假设、控制变量、结果和发布决策。

```bash
uv run agent-engineering-eval --list

uv run agent-engineering-eval \
  --suite evaluation/suites/agent-engineering-core.toml \
  --include-status ready \
  --include-status spike \
  --dry-run
```

## CLI 工具协议

协议为逐行 JSON，stdout 只承载协议消息，日志写 stderr。

```text
adapter -> CLI  {"type":"start","instruction":"..."}
CLI -> adapter  {"type":"tool_call","id":"...","name":"shell","arguments":{...}}
adapter -> CLI  {"type":"tool_result","id":"...","status":"success","output":"..."}
CLI -> adapter  {"type":"finish","status":"completed", ...metrics}
```

因此以后可以增加 HTTP、容器或远程服务 transport，而不需要修改三个 Agent 的工具
语义。ACP 可作为后续单独的协议层加入。

## 课程实验建议

三个 Agent 保持模型、任务和工具一致，可以用于观察开发框架本身带来的差异。之后可逐步
增加实验变量：

1. agent loop 和最大步数；
2. 工具 schema、输出截断和错误反馈；
3. system prompt、skills 与 context policy；
4. RAG、记忆和动态 workflow；
5. subagent 与并行策略；
6. 在隐藏任务集上执行回归门禁。

每轮只改变一个变量，至少运行多个 attempt，并同时记录 reward、异常、token 和执行时间。

## 开发验证

```bash
uv run python scripts/check_bedrock.py
uv run pytest -q
uv run ruff check .
```

仓库内置的 `hello-devopsagent` 任务用于验证“模型调用 → CLI 协议 → Harbor 环境工具 →
verifier”整条链路。
