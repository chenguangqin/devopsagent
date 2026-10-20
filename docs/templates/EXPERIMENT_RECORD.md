# Agent Engineering 实验记录

## 1. 基本信息

| 项目 | 内容 |
|---|---|
| 小组/学员 | |
| 日期 | |
| 实验名称 | |
| Baseline commit | |
| Experiment commit | |
| Agent engine | |
| Model | `global.anthropic.claude-haiku-5-5` |
| Suite/Track | |

## 2. 观察与问题

Baseline 出现了什么现象？

```text
填写逐题现象，不要只写总分。
```

关键轨迹证据：

1. 
2. 

主要失败类型：

```text
探索不足 / 假设错误 / Tool 使用错误 / 输出淹没 / 执行不完整 /
验证不足 / 过早终止 / 步骤耗尽 / 上下文丢失 / 基础设施
```

## 3. 实验假设

```text
如果改变……
那么……任务/阶段将……
原因是……
```

可能产生的副作用：

```text
例如 token 增长、步骤增长、简单任务退化或错误恢复过度。
```

## 4. 控制变量

### 固定项

| 变量 | 值 |
|---|---|
| Model | |
| Region | |
| Max steps | |
| Max tokens | |
| Tool timeout | |
| Attempts | |
| Task set | |
| Verifier | |

### 唯一主要改动

```text
只描述本轮主要变量。
```

涉及文件：

```text
path/to/file:line
```

## 5. 运行命令

Baseline：

```bash

```

Experiment：

```bash

```

## 6. 结果

### Track 汇总

| Variant | Track | Mean | Pass/Trials | Errors | Infra failures | Input tokens | Output tokens | Runtime |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | | | | | | | | |
| Experiment | | | | | | | | |

### 逐题结果

| Task | Baseline reward | Experiment reward | 行为差异 | 结论 |
|---|---:|---:|---|---|
| | | | | |

## 7. 轨迹分析

支持假设的证据：

1. 
2. 

反对假设或无法解释的证据：

1. 
2. 

是否出现新的失败模式？

```text

```

## 8. 成本与稳定性

- Reward 是否稳定：
- Token 变化：
- Tool Call 变化：
- 运行时间变化：
- 异常变化：
- 是否完成三次 Attempts：

## 9. 决策

选择：

```text
保留 / 继续实验 / 回退
```

理由：

```text

```

下一轮只验证：

```text

```
