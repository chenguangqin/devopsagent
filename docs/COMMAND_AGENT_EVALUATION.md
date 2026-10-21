# Command Agent Evaluation MVP

Iteration 1 implements the v0.2 command boundary for trusted local and Workshop
agents. The evaluation framework treats the Agent as an external process: the
Agent continues to own its model, prompt, loop, tools, MCP clients, skills,
memory, and workflow.

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
