# Agent 改造赛：Terminal-Bench 公开开发赛集

## 目标

学员在相同模型、任务、资源和评分器下修改 Agent，实现更高的任务通过率。允许调整 Agent
loop、system prompt、tools、skills、上下文管理、反思、验证策略和动态 workflow。

固定以下变量：

- 模型：`global.anthropic.claude-haiku-5-5`
- Region：`us-west-2`
- 数据集：`terminal-bench@2.0`
- Attempt：开发阶段 1 次，正式阶段建议 3 次
- Task 容器和 Harbor verifier

## 公开开发赛集

| 层级 | Task | 主要能力 | Expert 时间 |
|---|---|---|---:|
| 基础 | `fix-git` | Git 状态恢复、分支理解 | 5 分钟 |
| 基础 | `openssl-selfsigned-cert` | 命令组合、证书验证、文件权限 | 20 分钟 |
| 基础 | `log-summary-date-ranges` | 文件探索、日期边界、精确 CSV | 75 分钟 |
| 工程 | `regex-log` | 约束解析、正则构造、隐藏边界 | 45 分钟 |
| 工程 | `sqlite-with-gcov` | 源码构建、编译参数、PATH、验证 | 30 分钟 |
| 工程 | `nginx-request-logging` | 安装、配置、服务启动、HTTP 验证 | 20 分钟 |
| 工程 | `multi-source-data-merger` | 多格式 ETL、冲突处理、Parquet | 30 分钟 |
| 工程 | `db-wal-recovery` | 数据库恢复、二进制诊断、结果校验 | 45 分钟 |
| 挑战 | `configure-git-webserver` | Git hook、部署链和后台服务 | 15 分钟 |
| 挑战 | `fix-code-vulnerability` | 仓库理解、CWE、代码修复、测试 | 120 分钟 |

这里的 Expert 时间来自 Task metadata，仅表示人类专家估计，不是 Agent 的预期运行时间。

## 选择原则

入选任务全部满足：

- CPU 和 Docker 可运行；
- 不要求 GPU；
- 不要求视觉、音频或浏览器模型；
- 不需要外部账号；
- 可以仅使用 shell 工具完成；
- verifier 能提供客观结果；
- 能覆盖不同失败模式，而不是十道相似编码题。

本轮排除：

- `chess-best-move`、`code-from-image`：当前 Agent 没有视觉工具；
- QEMU 任务：容易把 Agent 能力和虚拟化、后台进程稳定性混在一起；
- GPU、训练和大模型推理任务：不适合 Workshop 宿主机；
- 强依赖公网下载的任务：培训现场稳定性风险较高。

## 开发阶段运行

只评测一个正在修改的 Agent：

```bash
uv run devopsagent-eval \
  --dataset terminal-bench@2.0 \
  --preset evaluation/presets/terminal-bench-competition.txt \
  --engines native \
  --model-id global.anthropic.claude-haiku-5-5 \
  --region us-west-2 \
  --max-steps 40 \
  --max-tokens 4096 \
  --tool-timeout-seconds 300 \
  --attempts 1 \
  --n-concurrent 2
```

如果学员改造的是 LangChain 或 Strands 实现，修改 `--engines`：

```text
--engines langchain
```

或者：

```text
--engines strands
```

## 预热和验收

讲师应在培训前用 Oracle 跑一次全部任务，完成镜像预拉取并确认 verifier 可用：

```bash
uv run harbor run \
  -d terminal-bench@2.0 \
  -a oracle \
  -i fix-git \
  -i openssl-selfsigned-cert \
  -i log-summary-date-ranges \
  -i regex-log \
  -i sqlite-with-gcov \
  -i nginx-request-logging \
  -i multi-source-data-merger \
  -i db-wal-recovery \
  -i configure-git-webserver \
  -i fix-code-vulnerability \
  -n 2 \
  -e docker
```

所有 Oracle Trial 应无异常且 reward 为满分。若某一 Task 因镜像或基础设施问题失败，应在
开课前替换，不能让学员在比赛中排查平台故障。

## 计分

公开开发榜采用：

```text
主分：10 个 Task 的 reward 总和，满分 10
第一 tie-break：异常数更少
第二 tie-break：总输出 token 更少
第三 tie-break：总运行时间更短
```

开发阶段每题运行 1 次以控制反馈时间。正式评分建议每题运行 3 次，使用平均 reward，降低
随机性影响。

不建议按单次运行结果决定冠军。

## 防止过拟合和作弊

公开任务适合快速实验，但不应该单独决定最终名次。建议：

1. 学员在上述 10 题上查看即时反馈；
2. 讲师另外准备 3～5 道不公开名称的 retention Task；
3. 最终成绩由公开集和隐藏集共同组成；
4. 禁止按任务名或 instruction 文本硬编码答案；
5. 禁止读取 Harbor verifier、tests、solution 或宿主机 Task 缓存；
6. 最终代码由讲师在干净环境重新运行。

当前 Harbor Adapter 在宿主机启动学员 Agent CLI。技术上，恶意修改的 Python 代码能够尝试
读取宿主机文件。因此这套方案适合教学竞赛，不是强对抗安全沙箱。正式排名必须结合代码审查
和干净环境复跑；若需要对抗性隔离，应进一步把 Agent Runtime 容器化。

## 推荐课程节奏

1. 讲师发布 Native baseline 分数；
2. 学员先跑 3 道基础题，确认 Agent 修改没有破坏工具链；
3. 加入 tools、skills、反思或验证策略；
4. 跑完整 10 题；
5. 分析失败轨迹，而不是只看总分；
6. 提交代码和配置；
7. 讲师在公开集三次复跑；
8. 最后运行隐藏 retention set。
