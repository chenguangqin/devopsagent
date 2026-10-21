# AWS Security Agent 实验记录

## 1. 基本信息

| 项目 | 内容 |
|---|---|
| 小组/学员 | |
| 日期 | |
| 实验名称 | |
| Baseline commit | |
| Experiment commit | |
| Agent Descriptor | |
| Baseline Variant | |
| Experiment Variant | |
| Model/Region | |
| Dataset/Task | |

## 2. 授权范围与威胁模型

允许的目标、资源和操作：

```text

```

禁止访问或执行：

```text

```

不可信输入来源：

```text

```

Boundary Violation 定义：

```text

```

## 3. Baseline 观察

逐题现象：

```text

```

关键轨迹证据：

1.
2.

主要失败类型：

```text
Evidence / Scope / Tool Selection / Parameter / Injection Following /
Secret Exposure / Unsafe Action / Diagnosis / Remediation / Verification /
Recovery / Infrastructure
```

## 4. 实验假设

```text
如果改变……
那么……指标将……
原因是……
```

可能产生的 Utility、token、步骤、延迟或误拒绝副作用：

```text

```

## 5. 控制变量

| 固定项 | 值 |
|---|---|
| Model/Region | |
| Dataset/Task | |
| Tool 与权限 | |
| Max steps | |
| Max tokens | |
| Deadline | |
| Attempts | |
| Verifier | |

唯一主要改动：

```text

```

涉及文件：

```text

```

## 6. 运行命令与结果路径

Baseline：

```bash

```

Experiment：

```bash

```

结果目录：

```text

```

## 7. Utility 与安全结果

| 指标 | Baseline | Experiment | 变化 |
|---|---:|---:|---:|
| Task pass rate | | | |
| Clean Utility | | | |
| Attack Success Rate | | | |
| False Refusal Rate | | | |
| Boundary Violation | | | |
| Security regression pass | | | |
| Exceptions | | | |

尚不可测指标及原因：

```text

```

## 8. 成本与稳定性

| 指标 | Baseline | Experiment | 变化 |
|---|---:|---:|---:|
| Input token | | | |
| Output token | | | |
| Tool calls | | | |
| Runtime | | | |
| pass@3/三次结果 | | | |

## 9. 证据分析

支持假设的证据：

1.
2.

反对假设或无法解释的证据：

1.
2.

是否出现新的失败或安全风险：

```text

```

## 10. 决策

```text
保留 / 继续实验 / 回退
```

理由：

```text

```

下一轮只验证：

```text

```
