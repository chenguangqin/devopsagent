# Command Agent Evaluation

Iteration 1 implements the v0.2 command boundary and state isolation. Iteration
2 adds an authenticated per-trial MCP Environment Gateway. The evaluation
framework treats the Agent as an external process: the Agent continues to own
its model, prompt, loop, SDK, MCP client, skills, memory, and workflow.

## Configuration

An Agent descriptor declares one argv command, isolated state, artifact globs,
capabilities, and the parameters that a Variant may change. All descriptor
paths are relative to `source.repository`; absolute paths and paths that escape
the repository are rejected.

```toml
[agent]
schema_version = "0.2"
id = "my-agent"
title = "My Agent"

[source]
repository = "."
revision = "git"

[launcher]
adapter = "command"
command = ["uv", "run", "python", "agent_eval_entry.py"]
input = "jsonl-stdin"
result = "json-file"
result_path = "run/result.json"
startup_timeout_seconds = 30
run_timeout_seconds = 600

[environment]
access = "mcp"
tools = ["environment_exec"]
tool_timeout_seconds = 120
max_output_chars = 16000

[state]
mode = "isolated-copy"
snapshot_paths = ["memory"]
empty_paths = ["reports", "run"]

[artifacts]
paths = ["reports/**", "run/**"]

[parameters.mode]
type = "enum"
values = ["baseline", "skill"]
default = "baseline"
delivery = "argv"
flag = "--mode"

[parameters.max_steps]
type = "integer"
minimum = 1
maximum = 50
default = 20
delivery = "env"
name = "AGENT_MAX_STEPS"
```

A Variant fixes the Git revision and supplies only declared parameter values:

```toml
[variant]
schema_version = "0.2"
id = "my-agent-skill"
agent = "agent.toml"

[source]
commit = "0123456789abcdef..."

[parameters]
mode = "skill"
max_steps = 20
```

`HEAD` is useful during local development, but comparison records always store
the resolved commit. A dirty source repository is marked
`reproducible = false`; the Agent still runs from the committed snapshot rather
than from dirty working-tree files.

## Agent protocol

The Adapter sends one `AgentRunRequest` JSON object followed by a newline on
stdin. It also provides:

- `AGENT_EVAL_RUN_ID`
- `AGENT_EVAL_INPUT`
- `AGENT_EVAL_RESULT`
- `AGENT_EVAL_ARTIFACT_DIR`

Only parameters declared with `delivery = "env"` are added to that environment.
An Agent that loads `.env` must use non-overriding semantics, such as
`load_dotenv(..., override=False)`.

The host pass-through allowlist is limited to process basics, proxy settings,
and standard AWS credential/profile variables. Their values are never written
to result metadata or logs by the harness.

When `[environment].access = "mcp"`, the Generic Harbor Adapter also provides:

- `AGENT_EVAL_MCP_TRANSPORT=streamable-http`
- `AGENT_EVAL_MCP_URL`
- `AGENT_EVAL_MCP_TOKEN`
- `AGENT_EVAL_MCP_HEADERS`

The URL is bound to loopback and exists only for the current Harbor trial.
Every request requires the per-trial bearer token. `environment_exec` is
resolved through a Tool Registry, capped by the descriptor timeout and output
limit, traced to `tool-calls.jsonl`, and then delegated to Harbor's
`BaseEnvironment.exec()`.

For example, a Strands shim can load the gateway without the evaluation
framework importing Strands:

```python
import json
import os

from strands.tools.mcp import MCPClient

gateway = MCPClient(
    url=os.environ["AGENT_EVAL_MCP_URL"],
    headers=json.loads(os.environ["AGENT_EVAL_MCP_HEADERS"]),
)
with gateway:
    gateway_tools = gateway.list_tools_sync()
    agent = build_agent(extra_tools=gateway_tools)
    result = agent(instruction)
```

The Agent must deliberately consume this standard contract. A completely
opaque Agent that supports neither MCP nor the evaluation protocol cannot
operate a remote Harbor environment.

The Agent writes the descriptor's `launcher.result_path`:

```json
{
  "schema_version": "0.2",
  "status": "completed",
  "final_text": "done",
  "structured_output": null,
  "usage": {
    "input_tokens": null,
    "output_tokens": null,
    "source": "unavailable"
  },
  "artifacts": []
}
```

Unavailable metrics are `null`, never zero. Agent-reported usage is diagnostic
and is not a ranking tie-break.

## Run

After committing the descriptor, shim, and Agent source:

```bash
uv run command-agent-eval \
  --variant path/to/baseline.toml \
  --task-id case-001 \
  --instruction "Produce the requested report" \
  --attempts 2 \
  --n-concurrent 2
```

Every attempt receives a separate source copy, memory copy, result directory,
logs, and artifact directory. The harness terminates the process group at the
deadline. Partial artifacts remain available to a diagnostic verifier, while
the official timeout score is always zero.

The deterministic fixture under
`evaluation/fixtures/agents/deterministic-agent/` exercises this full path.
The `demomcp` shim and descriptor template are under
`evaluation/spikes/demomcp/`; they call `demomcp`'s own `build_agent(mode)`
without importing Strands into the evaluation core.

## Run inside Harbor

An external Variant can operate a Harbor Docker environment through the MCP
Gateway:

```bash
uv run harbor run \
  --dataset terminal-bench@2.0 \
  --include-task-name git-leak-recovery \
  --agent evaluation.generic_harbor_adapter:GenericCommandHarborAgent \
  --ak variant_path=/absolute/path/to/agent/baseline.toml \
  --env docker \
  --n-concurrent 1 \
  --yes
```

The Generic Harbor Adapter runs the Variant's pinned Git snapshot on the host.
Only its declared MCP tools can affect the Harbor environment. Agent stdout and
stderr, the structured result, artifacts, source metadata, and tool-call trace
are stored under the Harbor trial's `agent/` directory.
