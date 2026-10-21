# Agent 改造赛设计规范

## 1. 比赛目标

学员在相同模型、任务环境和 Harbor Verifier 下改造 Agent，通过实验提高任务通过率，同时
控制 token、运行时间和异常数。

允许调整：

- agent loop；
- system prompt；
- tools 及工具返回格式；
- skills；
- 上下文裁剪和压缩；
- 反思与有限重试；
- subagent；
- 动态 workflow；
- 完成条件和验证策略。

固定变量：

| 变量 | 固定值 |
|---|---|
| 模型 | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Region | `us-west-2` |
| 数据集 | `terminal-bench@2.0` |
| 环境 | Docker |
| 最大步骤 | 40 |
| 单次最大输出 | 4096 tokens |
| 工具超时 | 300 秒 |
| 并发 | 2 |

## 2. 赛题结构

最终使用 10 道 Task：

```text
7 道公开开发题
+ 3 道讲师隐藏保留题
= 10 道正式评分题
```

公开题供学员反复运行、诊断和优化。隐藏题只在最终评分时由讲师加载，用于判断改进是否能
迁移到未见任务，并降低针对任务名称或 instruction 的硬编码风险。

## 3. 公开开发集

公开 preset：

```text
evaluation/presets/terminal-bench-competition.txt
```

### 3.1 基础题

| Task | 主要能力 |
|---|---|
| `log-summary-date-ranges` | 文件探索、日期边界、精确 CSV |
| `sqlite-with-gcov` | 源码构建、编译参数、PATH 和验证 |

基础题用于确认 Agent 改造没有破坏基本工具调用和任务交付能力。

### 3.2 挑战题

| Task | 主要能力 | Native 单次 baseline |
|---|---|---:|
| `cancel-async-tasks` | 异步并发、取消语义、资源清理 | 0 |
| `custom-memory-heap-crash` | C++ Release/Debug 差异、内存调试 | 1 |
| `git-leak-recovery` | Git 对象恢复和敏感信息清理 | 1 |
| `llm-inference-batching-scheduler` | 约束优化、成本模型、迭代实验 | 0 |
| `write-compressor` | 理解解压算法、逆向生成压缩数据 | 0 |

五道挑战题的 Native 单次 baseline 为：

```text
2/5 = 40%
```

该分数位于适合教学比赛的区间：基础 Agent 可以完成部分任务，同时保留足够优化空间。

### 3.3 未进入主赛的候选

`query-optimize` 在 Native baseline 中失败，且 verifier 接近 15 分钟，严重影响课堂反馈
速度。因此将其移出主赛，可作为课后 Bonus。

此前的 10 道公开题在三次 Attempts 的运行中间结果已接近 `0.95`，出现明显天花板效应，
不再适合承担主要排名功能。

## 4. 公开开发集运行

```bash
uv run devopsagent-eval \
  --dataset terminal-bench@2.0 \
  --preset evaluation/presets/terminal-bench-competition.txt \
  --engines native \
  --model-id global.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --region us-west-2 \
  --max-steps 40 \
  --max-tokens 4096 \
  --tool-timeout-seconds 300 \
  --attempts 1 \
  --n-concurrent 2
```

开发阶段使用一次 Attempt，以缩短反馈周期。学员应关注逐题失败原因，不应只观察总分。

如果学员选择其他实现：

```text
--engines langchain
```

或：

```text
--engines strands
```

## 5. 隐藏保留集

公开仓库不保存隐藏 Task 名称。讲师应在独立安全目录中维护一个相同格式的 preset：

```text
/secure/instructor/terminal-bench-hidden.txt
```

文件格式：

```text
# Instructor-only
<hidden-task-1>
<hidden-task-2>
<hidden-task-3>
```

隐藏题选择要求：

- 与公开题考查相近的可迁移能力；
- CPU 和 Docker 可运行；
- 不需要 GPU、视觉、音频、浏览器或外部账号；
- 仅使用 shell 工具即可完成；
- 不依赖不稳定公网资源；
- Oracle 可以通过；
- Native baseline 最好能通过 1～2 题；
- 单题 Agent 和 verifier 时间适合培训现场。

隐藏题名称不得：

- 提交到公开 Git 仓库；
- 写入学员版 AMI；
- 出现在公开课件或命令历史；
- 在最终评分前发送给学员。

## 6. 多 Preset 支持

`devopsagent-eval` 支持重复使用 `--preset`。多个文件中的 Task 会合并并自动去重：

```bash
uv run devopsagent-eval \
  --dataset terminal-bench@2.0 \
  --preset evaluation/presets/terminal-bench-competition.txt \
  --preset /secure/instructor/terminal-bench-hidden.txt \
  --engines native
```

也可以在 preset 之外追加单题：

```text
--include-task another-task
```

## 7. 最终评分

建议每道题运行三次：

```bash
uv run devopsagent-eval \
  --dataset terminal-bench@2.0 \
  --preset evaluation/presets/terminal-bench-competition.txt \
  --preset /secure/instructor/terminal-bench-hidden.txt \
  --engines native \
  --model-id global.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --region us-west-2 \
  --max-steps 40 \
  --max-tokens 4096 \
  --tool-timeout-seconds 300 \
  --attempts 3 \
  --n-concurrent 2
```

总规模：

```text
10 Task × 3 Attempts = 30 Trials
```

### 7.1 主分

每个 Trial 使用 Harbor 原始 reward：

```text
总分 = 30 个 Trial 的 reward 总和
满分 = 30
```

如果需要十分制：

```text
十分制得分 = mean reward × 10
```

评测汇总会显示：

- `mean`：平均 reward；
- `score`：reward 总和；
- `full`：得到 `1.0` 的 Trial 数；
- `trials`：已完成 Trial 数；
- `errors`：异常数；
- `tokens`：累计输入和输出 token。

### 7.2 Tie-break

同分时依次比较：

1. 异常数更少；
2. 输出 token 更少；
3. 总 token 更少；
4. 总运行时间更短。

不建议把 token 直接混入主分，否则学员可能为了节省 token 而牺牲任务可靠性。

## 8. 比赛流程

### 阶段 A：Baseline

讲师发布 Native baseline 的公开题结果。学员运行一次公开集，确认自己的环境和结果一致。

### 阶段 B：单变量实验

学员每轮只改变一个主要变量，例如：

- 强制完成前验证；
- 工具输出截断；
- 新增 Skill；
- context compression；
- 失败反思；
- 动态 workflow。

每轮保存代码 commit、运行参数、逐题 reward、token 和实验结论。

### 阶段 C：公开榜

使用公开 7 题运行一次 Attempt，快速更新成绩。公开榜只用于反馈，不作为唯一最终成绩。

### 阶段 D：提交冻结

学员提交：

- Git commit；
- Agent engine；
- 配置参数；
- 设计说明；
- 已知失败模式；
- 实验记录。

提交后不得继续修改代码。

### 阶段 E：讲师复跑

讲师在干净 EC2 环境中检出提交 commit，同时加载公开和隐藏 preset，执行三次 Attempts。

## 9. 防止过拟合和作弊

禁止：

- 根据 Task 名称选择专用答案；
- 匹配 instruction 文本并输出预制结果；
- 读取 Harbor `tests/`、`solution/` 或 verifier；
- 读取宿主机 Harbor Task 缓存；
- 修改评分器或 Task 定义；
- 为隐藏题添加专用分支。

当前 Harbor Adapter 在宿主机启动学员 Agent CLI，因此它不是强对抗安全沙箱。最终评分必须：

1. 在讲师控制的干净环境运行；
2. 进行代码审查；
3. 检查文件系统访问和硬编码；
4. 保存完整 Job 目录；
5. 记录 Git commit 和所有运行参数。

如果需要更强隔离，应将 Agent Runtime 放入独立容器，只开放明确的模型和工具协议。

## 10. 讲师预演

开课前分别对公开集和隐藏集执行：

1. Oracle 验收；
2. Native baseline 单次运行；
3. Native baseline 三次稳定性运行；
4. verifier 时间检查；
5. 镜像和磁盘占用检查。

验收目标：

| 项目 | 目标 |
|---|---|
| 公开挑战题 baseline | 20%～60% |
| 隐藏题 baseline | 通过 1～2 题 |
| Harbor Exceptions | 0 |
| 单题最长时间 | 不影响课堂反馈 |
| 全部公开题单次反馈 | 约 5～10 分钟 |

如果某题持续满分，降低其排名权重或替换；如果所有实现持续失败，则作为 Bonus，而不是主赛题。

## 11. 课程实验价值

当前公开挑战题的失败轨迹已经表现出明显模式：

- 失败任务往往只执行 2～4 个步骤；
- 成功任务执行 6～9 个步骤；
- 失败原因不是 `max_steps` 不足，而是过早判断完成；
- 优化类任务缺少 Measure → Patch → Measure 循环；
- 调试任务成功但可能产生过多上下文和 token。

因此比赛分数可以直接反映以下 Agent 工程能力：

- 完成条件；
- 验证策略；
- 工具设计；
- 上下文管理；
- Skill 设计；
- 反思和重试；
- 动态工作流；
- 成本与可靠性的权衡。
