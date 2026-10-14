# DevOpsAgent

A minimal Harbor External Agent that uses Amazon Bedrock Converse with
`global.anthropic.claude-haiku-5-5`.

The first version intentionally contains only:

- a Bedrock Converse adapter;
- one Harbor-bound `shell` tool;
- a model → tool → result agent loop;
- max-step and tool-timeout limits;
- Harbor `AgentContext` usage and a JSON trace.

It is the baseline for later experiments with structured tools, skills, RAG,
subagents, dynamic workflows, policies, and memory.

## Architecture

```text
Harbor Trial
  └── DevOpsAgent (host process)
      ├── BedrockConverseAdapter
      │   └── Claude Haiku 5.5
      └── AgentLoop
          └── ShellTool
              └── BaseEnvironment.exec()
                  └── isolated task container
```

Bedrock calls run on the host, so an EC2 instance profile can provide AWS
credentials without mounting them into the benchmark container.

## Setup

Requires Python 3.12+, `uv`, Docker, Docker Compose, and Buildx.

```bash
git clone <your-repository-url> devopsagent
cd devopsagent
uv sync
```

Validate the custom Harbor options:

```bash
uv run harbor agent schema devopsagent.harbor_agent:DevOpsAgent
```

Validate Bedrock independently of Docker:

```bash
uv run python scripts/check_bedrock.py
```

Run unit tests:

```bash
uv run pytest -q
uv run ruff check .
```

## Run the included Harbor task

```bash
uv run harbor run \
  -p examples/tasks/hello-devopsagent \
  -a devopsagent.harbor_agent:DevOpsAgent \
  -m global.anthropic.claude-haiku-5-5 \
  --ak region=us-west-2 \
  --ak max_steps=8 \
  --ak max_tokens=2048 \
  -e docker
```

Expected result:

```text
Trials: 1
Exceptions: 0
Mean: 1.000
```

The agent writes its trace into the Harbor trial's agent logs as
`agent-result.json`.

## Configuration

Inspect the authoritative schema:

```bash
uv run harbor agent schema devopsagent.harbor_agent:DevOpsAgent
```

Current options:

| Option | Default | Meaning |
|---|---:|---|
| `region` | `us-west-2` | Bedrock Runtime region |
| `max_steps` | `12` | Maximum model turns |
| `max_tokens` | `4096` | Maximum output tokens per model call |
| `tool_timeout_seconds` | `120` | Shell command timeout |
| `max_tool_output_chars` | `50000` | Maximum tool result size |
| `system_prompt` | built in | Agent system instruction |

Claude Haiku 5.5 rejects the `temperature` parameter, so this adapter does not
send it.

