# DevOpsAgent Harbor 实验环境搭建规范

## 1. 文档目的

本文定义 DevOpsAgent 课程实验环境从裸 EC2 主机检查，到 Docker Compose、Docker
Buildx、Harbor、Bedrock、课程项目和正式 Benchmark Task 验证的完整搭建流程。

本文记录的是已经实际跑通的版本组合，不建议在培训现场临时升级到未经验证的新版本。

## 2. 已验证版本基线

| 组件 | 已验证版本 |
|---|---|
| 操作系统 | Amazon Linux 2023 |
| CPU 架构 | `x86_64` |
| CPU | 8 vCPU |
| 内存 | 30 GiB |
| 根磁盘 | 100 GiB，约 91 GiB 可用 |
| Docker Client | `25.0.14` |
| Docker Server | `25.0.16` |
| Docker Compose | `v5.6.0` |
| Docker Buildx | `v0.36.0` |
| Harbor | `0.24.0` |
| Python | `>=3.12` |
| Python 包管理器 | `uv` |
| AWS Region | `us-west-2` |
| Bedrock Model ID | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |

关键兼容性说明：

1. 主机最初已经安装 Docker，但没有 Docker Compose。
2. 安装 Compose `v5.6.0` 后，Harbor 首次构建任务失败：

   ```text
   compose build requires buildx 0.17.0 or later
   ```

3. 主机原有 Buildx 为 `v0.12.1`，升级到 `v0.36.0` 后 Harbor 官方
   `hello-world` Task 得分为 `1.000`。

## 3. 环境架构

```text
EC2 host
├── AWS instance profile
│   └── Bedrock InvokeModel permissions
├── DevOpsAgent Python environment
│   ├── native Agent
│   ├── LangChain Agent
│   ├── Strands Agent
│   └── Harbor adapter
├── Harbor
│   ├── dataset/task downloader
│   ├── trial orchestrator
│   └── verifier
└── Docker
    └── isolated task containers
```

模型调用发生在 EC2 宿主机，Task 的命令执行发生在 Docker Trial 容器。AWS 凭证不需要
挂载到 Task 容器中。

## 4. AWS 和网络前置条件

### 4.1 EC2 Instance Profile

EC2 角色至少需要以下 Bedrock Runtime 权限：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "*"
    }
  ]
}
```

Native Agent 使用 Converse；LangChain 和 Strands 可能使用流式模型接口，因此同时保留
`InvokeModelWithResponseStream`。

### 4.2 出站网络

实验主机需要通过 HTTPS 访问：

- GitHub 和 `raw.githubusercontent.com`
- GitHub Container Registry：`ghcr.io`
- Docker Hub：`docker.io`，Terminal-Bench 2.0 部分任务镜像使用该 Registry
- Python 包仓库
- `astral.sh`，仅在需要安装 `uv` 时使用
- Amazon Bedrock Runtime `us-west-2`

Harbor Task 定义从 Git 仓库下载，Task 环境通常从 `ghcr.io` 拉取镜像。

## 5. 主机资源检查

登录 EC2 后执行：

```bash
uname -m
lscpu
free -h
lsblk
df -h
cat /etc/os-release
```

推荐最低资源：

| 资源 | 最低建议 | 课程已验证 |
|---|---:|---:|
| CPU | 4 vCPU | 8 vCPU |
| 内存 | 16 GiB | 30 GiB |
| 可用磁盘 | 40 GiB | 91 GiB |
| Swap | 非必需 | 0 |

正式 Task 首轮使用：

```text
--n-concurrent 1
```

避免多个构建型任务同时拉镜像、编译和调用模型。

## 6. 验证 Docker

```bash
docker --version
docker info
systemctl is-active docker
```

预期：

```text
active
```

如果 Docker 未启动：

```bash
sudo systemctl enable --now docker
```

如果当前用户执行 Docker 时出现权限错误：

```bash
sudo usermod -aG docker "$USER"
```

重新登录 SSH 后再运行 `docker info`。不要在权限配置完成前使用 Harbor。

## 7. 安装 Docker Compose

Amazon Linux 2023 的当前软件源中没有提供需要的 `docker-compose` 包，因此以 Docker CLI
插件形式安装。

### 7.1 x86_64 主机

```bash
COMPOSE_RELEASE=v5.6.0

sudo install -d -m 0755 /usr/local/lib/docker/cli-plugins

curl -fL \
  "https://github.com/docker/compose/releases/download/${COMPOSE_RELEASE}/docker-compose-linux-x86_64" \
  -o /tmp/docker-compose

file /tmp/docker-compose

sudo install -m 0755 \
  /tmp/docker-compose \
  /usr/local/lib/docker/cli-plugins/docker-compose
```

### 7.2 验证

```bash
docker compose version
```

预期：

```text
Docker Compose version v5.6.0
```

如果 `uname -m` 返回 `aarch64`，应下载对应的
`docker-compose-linux-aarch64`，不能使用本文的 x86_64 二进制文件。

## 8. 升级 Docker Buildx

### 8.1 升级原因

主机原有 Buildx：

```text
v0.12.1
```

Compose 构建 Harbor 环境时要求：

```text
buildx 0.17.0 or later
```

因此升级到已验证的 `v0.36.0`。

### 8.2 x86_64 主机安装命令

```bash
BUILDX_RELEASE=v0.36.0

curl -fL \
  "https://github.com/docker/buildx/releases/download/${BUILDX_RELEASE}/buildx-${BUILDX_RELEASE}.linux-amd64" \
  -o /tmp/docker-buildx

file /tmp/docker-buildx

sudo install -m 0755 \
  /tmp/docker-buildx \
  /usr/local/lib/docker/cli-plugins/docker-buildx
```

### 8.3 验证插件优先级

```bash
docker buildx version
docker info | sed -n '/Plugins:/,/Server:/p'
```

预期看到：

```text
buildx:
  Version: v0.36.0
  Path: /usr/local/lib/docker/cli-plugins/docker-buildx

compose:
  Version: v5.6.0
  Path: /usr/local/lib/docker/cli-plugins/docker-compose
```

`/usr/local/lib/docker/cli-plugins` 中的新版插件应覆盖系统原有
`/usr/libexec/docker/cli-plugins/docker-buildx`。

ARM 主机应使用 Buildx 的 `linux-arm64` 二进制文件。

## 9. 安装 uv

先检查：

```bash
uv --version
```

如果 Workshop 镜像已经包含 `uv`，不需要重复安装。否则：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

## 10. 安装并验证 Harbor

课程项目会通过可选依赖安装固定版本 Harbor。若需要在克隆课程项目之前独立验证 Harbor，
可以先安装为 uv tool：

```bash
uv tool install "harbor==0.24.0"
harbor --version
```

预期：

```text
0.24.0
```

安装后通常包含：

```text
harbor
hb
hr
```

## 11. Harbor 官方 Smoke Test

### 11.1 下载官方模板

```bash
mkdir -p "$HOME/workspace"
cd "$HOME/workspace"

git clone --depth 1 \
  https://github.com/harbor-framework/benchmark-template.git \
  harbor-smoke
```

### 11.2 运行 Oracle

```bash
harbor run \
  -p harbor-smoke/tasks/hello-world \
  -a oracle \
  -e docker
```

验收结果：

```text
Trials: 1
Exceptions: 0
Mean: 1.000
```

如果结果为 `RuntimeError`，查看最新 Job：

```bash
JOB_DIR=$(find jobs -mindepth 1 -maxdepth 1 -type d | sort | tail -1)

grep -RniE \
  'error|exception|traceback|runtimeerror|failed' \
  "$JOB_DIR"
```

如果日志包含：

```text
compose build requires buildx 0.17.0 or later
```

返回第 8 节升级 Buildx，再重新运行 Smoke Test。

## 12. 验证 AWS 身份和 Bedrock

### 12.1 AWS 身份

```bash
aws sts get-caller-identity
```

### 12.2 直接调用模型

```bash
aws bedrock-runtime converse \
  --region us-west-2 \
  --model-id global.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --messages '[{
    "role":"user",
    "content":[{"text":"Reply with exactly: Haiku 4.5 is working"}]
  }]' \
  --inference-config '{"maxTokens":32}'
```

预期输出包含：

```text
Haiku 4.5 is working
```

这里使用 `global.anthropic...`，而不是 `us.anthropic...`，因为当前验证的是 Bedrock
Global Cross-Region Inference Profile ID。

## 13. 部署课程项目

### 13.1 克隆项目

```bash
cd "$HOME/workspace"

git clone https://github.com/chenguangqin/devopsagent.git
cd devopsagent
```

如果项目已经存在：

```bash
cd "$HOME/workspace/devopsagent"
git pull --ff-only origin main
```

### 13.2 安装课程评测依赖

```bash
uv sync --all-extras
```

该命令安装：

- Native Bedrock Agent
- LangChain Agent
- Strands Agent
- Harbor `0.24.0`
- 测试与静态检查工具

生产环境如果只运行 Native Agent，不做 Harbor 评测，可以使用：

```bash
uv sync
```

### 13.3 验证项目

```bash
uv run python scripts/check_bedrock.py
uv run pytest -q
uv run ruff check .
```

Bedrock 检查预期：

```text
Bedrock connection works
```

## 14. 验证三个 Harbor Adapter

### 14.1 Adapter 的作用

Harbor 命令中的：

```text
evaluation.harbor_adapter:NativeCliHarborAgent
```

采用标准 Python 导入路径格式：

```text
Python 模块路径:类名
```

具体对应：

```text
evaluation/harbor_adapter.py
└── class NativeCliHarborAgent
```

`NativeCliHarborAgent` 不是负责推理的 Agent，而是 Harbor 与 Native Agent CLI 之间的
协议桥接层。它负责：

1. 接收 Harbor 从 `instruction.md` 读取的任务指令；
2. 在 EC2 宿主机启动 Native Agent CLI；
3. 通过 stdin/stdout JSONL 协议向 CLI 发送任务；
4. 接收 CLI 发出的 shell 工具调用；
5. 使用 Harbor `BaseEnvironment.exec()` 在当前 Trial 的 Docker 容器中执行命令；
6. 将命令输出返回给 Agent CLI；
7. 将 token、步骤数和工具调用数等指标写入 Harbor `AgentContext`。

Adapter 启动的 CLI 等价于：

```bash
python -m devopsagent.cli \
  --engine native \
  --protocol stdio
```

主要交互流程：

```text
Harbor
  │ instruction
  ▼
NativeCliHarborAgent
  │ JSONL start
  ▼
Native Agent CLI
  │ JSONL tool_call
  ▼
NativeCliHarborAgent
  │ BaseEnvironment.exec()
  ▼
Task Docker 容器
  │ command result
  ▼
NativeCliHarborAgent
  │ JSONL tool_result
  ▼
Native Agent CLI
```

典型协议消息如下：

```json
{"type":"start","instruction":"分析日志并生成 summary.csv"}
```

```json
{
  "type": "tool_call",
  "id": "call-id",
  "name": "shell",
  "arguments": {"command": "ls -la /app"}
}
```

```json
{
  "type": "tool_result",
  "id": "call-id",
  "status": "success",
  "output": "exit_code: 0\nstdout:\n...\nstderr:\n"
}
```

职责边界：

| 组件 | 职责 |
|---|---|
| Native Agent CLI | 模型调用、推理、规划、生成命令、决定是否继续 |
| Harbor Adapter | 协议转换、进程启动、工具调用转发、指标回填 |
| Harbor Environment | 创建隔离环境并在 Task 容器中执行命令 |
| Harbor Verifier | 检查最终环境状态并计算 reward |

Adapter 不负责推理、生成命令、执行 verifier 或计算 reward。

这种解耦使 `src/devopsagent/` 不依赖 Harbor。生产部署时可以只运行 Agent CLI；只有进行
Benchmark 评测时才安装 Harbor 并加载 `evaluation/harbor_adapter.py`。

另外两个 Adapter 使用相同协议，只是启动不同的 Agent 实现：

| Adapter | Agent engine |
|---|---|
| `NativeCliHarborAgent` | `native` |
| `LangChainCliHarborAgent` | `langchain` |
| `StrandsCliHarborAgent` | `strands` |

### 14.2 验证 Adapter Schema

```bash
uv run harbor agent schema \
  evaluation.harbor_adapter:NativeCliHarborAgent

uv run harbor agent schema \
  evaluation.harbor_adapter:LangChainCliHarborAgent

uv run harbor agent schema \
  evaluation.harbor_adapter:StrandsCliHarborAgent
```

三个命令都应正常输出 Agent 参数 Schema。

## 15. 运行课程内置端到端 Task

先使用 Native Agent：

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

验收：

```text
Trials: 1
Exceptions: 0
Mean: 1.000
```

该测试验证完整链路：

```text
Harbor
→ 启动 Agent CLI
→ Bedrock 模型调用
→ JSONL tool_call
→ BaseEnvironment.exec()
→ Docker Task
→ verifier
→ reward
```

## 16. 下载正式 Task 供讲师检查

Task 不包含在 Harbor SDK 或 DevOpsAgent 仓库中。Harbor 根据 Registry 在运行时下载。

为了在培训前检查 `instruction.md`、`task.toml` 和环境定义，执行：

```bash
mkdir -p benchmarks

uv run harbor dataset download \
  terminal-bench-sample@2.0 \
  --output-dir benchmarks \
  --export
```

查看任务：

```bash
find benchmarks/terminal-bench-sample \
  -name instruction.md \
  -print
```

例如：

```bash
cat benchmarks/terminal-bench-sample/log-summary-date-ranges/instruction.md
cat benchmarks/terminal-bench-sample/log-summary-date-ranges/task.toml
```

运行时缓存通常位于：

```bash
find "$HOME/.cache/harbor/tasks" \
  -name instruction.md \
  -print
```

## 17. 正式 Task 第一轮验证

### 17.1 单 Task 验证

先运行资源和逻辑最可控的日志任务：

```bash
uv run harbor run \
  -d terminal-bench-sample@2.0 \
  -i log-summary-date-ranges \
  -a evaluation.harbor_adapter:NativeCliHarborAgent \
  -m global.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --ak region=us-west-2 \
  --ak max_steps=30 \
  --ak max_tokens=4096 \
  --ak tool_timeout_seconds=300 \
  -n 1 \
  -e docker
```

### 17.2 课程正式子集

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
  --max-tokens 4096 \
  --tool-timeout-seconds 300 \
  --n-concurrent 1
```

五个任务覆盖：

| Task | 能力 |
|---|---|
| `log-summary-date-ranges` | 日志探索、日期边界、精确 CSV |
| `sqlite-with-gcov` | 构建链、编译参数、PATH、验证 |
| `configure-git-webserver` | Git hook、Web 服务、后台进程 |
| `fix-code-vulnerability` | 仓库理解、CWE、修复、测试 |
| `polyglot-c-py` | 复杂约束、C/Python 跨语言实现 |

Native 链路稳定后，删除：

```text
--engines native
```

即可依次对 Native、LangChain 和 Strands 三个 Agent 运行相同任务集。

### 17.3 Native Baseline 结果解读示例

以下是 Native Agent 在五个 `terminal-bench-sample@2.0` Task 上的一次真实运行结果：

```text
5/5 Mean: 0.400

Trials: 5
Exceptions: 0

Reward 0.0: 3
Reward 1.0: 2

Total runtime: 5m 6s
Total tokens: 138580
```

该结果应解读为：

| 指标 | 含义 |
|---|---|
| `Trials: 5` | 五个 Task 都完成了评测流程 |
| `Exceptions: 0` | Harbor、Adapter、Bedrock 和 Docker 没有基础设施异常 |
| `Mean: 0.400` | 五个 Task 的平均 reward 为 0.4 |
| `Reward 1.0: 2` | 两个 Task 通过 verifier |
| `Reward 0.0: 3` | 三个 Task 的最终环境或产物未满足 verifier |
| `Total runtime: 5m 6s` | 在 `n_concurrent=1` 下串行执行的总时间 |
| `Total tokens: 138580` | 五个 Task 的累计输入和输出 token |

这组结果可以概括为：

```text
基础设施执行成功率：100%
Agent Task 通过率：40%
待优化空间：60%
```

`Exceptions: 0` 不表示所有 Task 都成功。Agent 可能正常结束、没有抛出异常，甚至在最终回复
中声称已经完成，但 Harbor Verifier 仍可能判定输出文件、服务状态或业务结果不正确。

同样，Agent 达到 `max_steps` 后可以正常返回 `max_steps` 状态并进入评分流程。这种情况通常
不会计为 Harbor Exception，但 Task 很可能得到 `0.0`。

#### 查看逐题结果

设置 Job 路径：

```bash
JOB=evaluation/jobs/2026-10-19__14-48-54/native
```

使用 `jq` 查看每个 Task 的 reward、Agent 状态、步骤数、工具调用数和 token：

```bash
jq -r '
["task","reward","status","steps","tools","input","output"],
(.trial_results[] | [
  .task_name,
  (.verifier_result.rewards.reward // "NA"),
  (.agent_result.metadata.status // "NA"),
  (.agent_result.metadata.steps // "NA"),
  (.agent_result.metadata.tool_calls // "NA"),
  (.agent_result.n_input_tokens // 0),
  (.agent_result.n_output_tokens // 0)
]) | @tsv
' "$JOB/result.json" | column -t -s $'\t'
```

这里的 `JOB` 应替换为实际运行输出中的目录。

#### 查看失败轨迹

```bash
find "$JOB" \
  \( -name agent-result.json -o -name agent-stderr.log -o -name trial.log \) \
  -print
```

也可以使用 Harbor Viewer：

```bash
uv run harbor view evaluation/jobs/2026-10-19__14-48-54
```

建议按照以下顺序诊断失败：

1. 先确认 Task 的 reward 和 Agent 最终状态；
2. 检查是否达到 `max_steps`；
3. 检查 Agent 是否执行了 verifier 所需的最终验证；
4. 检查 shell 输出是否过长、截断或污染上下文；
5. 检查 Agent 是否误判成功并提前结束；
6. 最后再调整 prompt、skills、tools 或 agent loop。

#### Token 指标的实验意义

本次五题累计约 `138580` token，平均每题约 `27716` token。该数字是多轮模型调用的累计量，
不是单次上下文长度。Native Agent 每轮都会重新携带已有对话和工具结果，长日志、编译输出和
测试输出会反复进入后续请求，从而放大 token 消耗。

这可以直接作为课程实验的优化目标，比较：

- shell 工具输出截断；
- 针对日志、文件和测试结果的结构化工具；
- context compression；
- 任务 Skill；
- 强制验证步骤；
- 最大步骤数；
- 失败反思与有限重试；
- reward、token 和运行时间之间的权衡。

该结果只运行了一个 Attempt，适合作为开发 baseline，不适合作为最终排名。正式比赛建议每个
Task 至少运行三次并使用平均 reward。

## 18. 长任务和 SSH 断线处理

显示器黑屏本身不会终止 EC2 进程，但 SSH 或网络中断可能使前台进程收到挂断信号。正式评测
应在 `tmux` 中运行。

```bash
sudo dnf install -y tmux
tmux new -s harbor-eval
```

在 tmux 中执行评测。分离会话：

```text
Ctrl-b d
```

重新连接：

```bash
tmux attach -t harbor-eval
```

检查会话：

```bash
tmux ls
```

## 19. 结果位置

直接执行 `harbor run` 时：

```text
jobs/<timestamp>/
```

执行 `devopsagent-eval` 时：

```text
evaluation/jobs/<timestamp>/
├── native/
├── langchain/
├── strands/
└── matrix-summary.json
```

查看 Harbor Job：

```bash
uv run harbor view jobs
```

命令会启动本地 Viewer。AWS Workshop 需要相应端口转发或通过预置 Web 访问方式打开。

## 20. 运行状态与资源检查

```bash
docker ps
docker images
docker system df
df -h
free -h
```

检查 Harbor 缓存：

```bash
du -sh "$HOME/.cache/harbor" 2>/dev/null
```

培训环境不要在任务运行期间执行 Docker 清理。清理镜像和缓存应作为课后运维操作，并先确认
没有正在运行的 Trial。

## 21. 常见故障

### 21.1 `docker: 'compose' is not a docker command`

原因：Compose CLI 插件未安装或路径不正确。

处理：重新执行第 7 节，并确认：

```bash
docker compose version
```

### 21.2 `compose build requires buildx 0.17.0 or later`

原因：系统内置 Buildx 版本过旧。

处理：执行第 8 节，确认实际加载路径位于：

```text
/usr/local/lib/docker/cli-plugins/docker-buildx
```

### 21.3 `no container found for service "main"`

通常是前面的 Docker Compose build 已经失败，不是根因。向上查找 Job 日志中第一次出现的
build 错误。

### 21.4 Bedrock `AccessDeniedException`

检查：

```bash
aws sts get-caller-identity
```

然后确认 EC2 Instance Profile 包含：

```text
bedrock:InvokeModel
bedrock:InvokeModelWithResponseStream
```

### 21.5 模型不存在或 Model ID 错误

使用已验证值：

```text
global.anthropic.claude-haiku-4-5-20251001-v1:0
```

并在：

```text
us-west-2
```

执行第 12.2 节的直接 Converse 测试。

### 21.6 GitHub 或 GHCR 下载超时

确认安全组、代理、NAT Gateway 和 DNS 允许出站 HTTPS。重新运行时 Git 和 Docker 通常会
复用已经下载的内容。

### 21.7 正式 Task 达到 Agent 超时

优先：

1. 保持 `--n-concurrent 1`；
2. 使用 `--max-steps 30`；
3. 使用 `--tool-timeout-seconds 300`；
4. 查看 Agent trace，确认不是无效循环；
5. 不要直接无限放大超时。

### 21.8 内存或磁盘不足

```bash
free -h
df -h
docker system df
```

先停止并发评测，再判断是否需要扩容。不要在不确认目标的情况下执行破坏性的 Docker 清理。

## 22. 最终验收清单

- [ ] `uname -m` 与下载的 Compose/Buildx 架构一致
- [ ] Docker daemon 为 `active`
- [ ] `docker compose version` 为 `v5.6.0`
- [ ] `docker buildx version` 为 `v0.36.0`
- [ ] `harbor --version` 或 `uv run harbor --version` 为 `0.24.0`
- [ ] `aws sts get-caller-identity` 成功
- [ ] Bedrock Converse 返回 `Haiku 4.5 is working`
- [ ] Harbor 官方 Oracle Smoke Test 得分 `1.000`
- [ ] `uv sync --all-extras` 成功
- [ ] 项目 Bedrock 检查成功
- [ ] 项目测试与 Ruff 检查成功
- [ ] 三个 Harbor Adapter Schema 可加载
- [ ] 课程内置 Task 得分 `1.000`
- [ ] `log-summary-date-ranges` 正式 Task 可以完成评分
- [ ] 长时间评测通过 tmux 启动

## 23. 培训镜像制作建议

正式培训前应将以下内容固化进 AWS Workshop AMI 或启动脚本：

1. Docker、Compose `v5.6.0` 和 Buildx `v0.36.0`；
2. `uv`；
3. 克隆后的 DevOpsAgent 项目；
4. `uv sync --all-extras` 生成的环境；
5. 预拉取的 Terminal-Bench Task 镜像；
6. 已下载的正式 Task 定义；
7. tmux；
8. 实例角色和 Bedrock 网络连通性检查。

不要把 AWS 长期 Access Key、Harbor 真值、verifier 私有测试或 solution 内容打包给学员。
