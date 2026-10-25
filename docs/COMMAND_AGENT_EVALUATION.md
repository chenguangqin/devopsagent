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

## Run in the comparison matrix

`devopsagent-eval` accepts `--variant` (repeatable) and runs each Variant
through the Generic Harbor Adapter. With `--variant` alone, only external
Agents run. Add `--engines` to put built-in engines in the same comparison
table. `--max-steps`, `--max-tokens`, `--tool-timeout-seconds`, and
`--model-id` apply only to built-in engines; an external Agent takes its
budget, model, and tool timeout from its descriptor and Variant.

The sibling `my_strands_agent` repository is a worked example. Its adaptation
consists of `agent_eval_entry.py`, `config.eval.yaml`, `prompts/eval.md`,
`eval/agent.toml`, `eval/baseline.toml`, and an `extra_tools` parameter on
`build_agent`. The baseline Variant matches the built-in engine budget below
(30 turns, 4096 max tokens, 300 second tool timeout).

### Verify

1. Prerequisites: Docker is running, AWS credentials with Bedrock access to
   Claude Haiku 4.5 in `us-west-2` are available, and the Agent's changes are
   committed. The Adapter runs the committed snapshot, never the working tree.

   ```bash
   git -C /home/ec2-user/workspace/my-workspace/my_strands_agent status --short
   ```

   The output must be empty.

2. Smoke test with one task:

   ```bash
   uv run devopsagent-eval \
     --dataset terminal-bench-sample@2.0 \
     --variant /home/ec2-user/workspace/my-workspace/my_strands_agent/eval/baseline.toml \
     --include-task log-summary-date-ranges \
     --n-concurrent 1
   ```

   Expected: the `my-strands-baseline` row shows `errors = 0` and a non-empty
   `tokens` value. The reward can be 0 or 1. It reflects the Agent's answer,
   not the integration.

3. Full evaluation on the task set in
   `evaluation/presets/my-strands-agent.txt` (5 tasks from
   `terminal-bench-sample@2.0`):

   ```bash
   uv run devopsagent-eval \
     --dataset terminal-bench-sample@2.0 \
     --preset evaluation/presets/my-strands-agent.txt \
     --variant /home/ec2-user/workspace/my-workspace/my_strands_agent/eval/baseline.toml \
     --attempts 1 \
     --n-concurrent 1
   ```

   Expected: the `my-strands-baseline` row shows 5 trials and `errors = 0`.
   Raise `--n-concurrent` to run tasks in parallel. Raise `--attempts` to
   repeat each task and reduce the variance of the mean reward.

   To compare against the built-in native engine on the same tasks and
   budget, add:

   ```text
   --engines native --max-steps 30 --max-tokens 4096 --tool-timeout-seconds 300
   ```

   The comparison table then has a `native` row and a `my-strands-baseline`
   row.

4. Inspect a trial. Results go to
   `evaluation/jobs/<timestamp>/<job>/<task>__<id>/`:

   | Path | Content |
   |---|---|
   | `agent/stdout.log` | Agent output, tool calls, and final `stop_reason` |
   | `agent/stderr.log` | `uv` environment setup and Agent errors |
   | `agent/tool-calls.jsonl` | One line per `environment_exec` call |
   | `agent/agent-result.json` | Source commit, parameters, exit code, result |
   | `verifier/test-stdout.txt` | Verifier output that explains the reward |
   | `exception.txt` | Present only when the trial errored |

   `matrix-summary.json` in the run directory holds the comparison table as
   JSON.

### Update the task set

Edit `evaluation/presets/my-strands-agent.txt`. The command stays the same.

- Add or remove one task name per line. Lines starting with `#` are
  comments.
- Every name must exist in the dataset passed to `--dataset`. Check a new
  name with the step 2 smoke test (`--include-task <name>`) before adding it.
- To use tasks from the full `terminal-bench@2.0` dataset, change
  `--dataset` and update the header comment in the preset. A preset holds
  task names only, not the dataset.
- Repeated `--preset` flags are merged and deduplicated, and
  `--include-task` adds single tasks on top. Use either one to keep a
  private task set in a separate file.

### Data query task set

`evaluation/tasks/data-query/` holds 10 query tasks. Each one gives the Agent a
structured data source and a question, and grades one exact answer. Every task
directory is self-contained: `instruction.md`, `task.toml`, `environment/`,
`tests/`, and `solution/`.

| Task | Source dataset | Data and question | Answer file |
|---|---|---|---|
| `sparql-university` | `terminal-bench@2.0` | SPARQL over a university knowledge graph: full professors in EU departments with more than 10 enrolled students | `/app/solution.sparql` |
| `bird-california_schools__13` | `bird-bench@parity` | Top 3 schools by SAT excellence rate, with contact, charter, and poverty class | `/app/answer.sql` |
| `bird-thrombosis_prediction__1192` | `bird-bench@parity` | Outpatients tested in October 1991 with a bilirubin condition | `/app/answer.sql` |
| `bird-toxicology__229` | `bird-bench@parity` | Bond types of molecule TR000 by frequency, with element pair counts | `/app/answer.sql` |
| `bird-student_club__1457` | `bird-bench@parity` | Members who spent more than average on each expense | `/app/answer.sql` |
| `bird-superhero__786` | `bird-bench@parity` | Heroes with the highest strength attribute value | `/app/answer.sql` |
| `dabstep-178` | `dabstep@1.0` | Average transaction value by IP country for one merchant, scheme, and period | `/app/answer.txt` |
| `dabstep-1756` | `dabstep@1.0` | Fee IDs that apply to one merchant in June 2023 | `/app/answer.txt` |
| `dabstep-2057` | `dabstep@1.0` | Fee delta for one merchant if one fee rule changes | `/app/answer.txt` |
| `dabstep-2527` | `dabstep@1.0` | Merchants affected by one fee rule in 2023 | `/app/answer.txt` |

Grading:

- `sparql-university`: the query must run and return exactly the expected
  rows.
- `bird-*`: the verifier runs the Agent's SQL and the gold SQL on the same
  SQLite database and compares the result rows as sets. Row order is ignored,
  but every column must match the gold query, including column count and
  value formatting. The questions do not always state the expected columns,
  so these tasks also test how the Agent reads the question.
- `dabstep-*`: the answer is compared with the official DABstep scorer,
  which tolerates number formatting and close string matches. The Agent must
  read `manual.md` and `payments-readme.md` in `/app/data/` to apply the fee
  rules correctly.

Data sources:

- `bird-*` ship the SQLite database in `environment/db.sqlite` (24 MB for the
  whole folder). The registry stores these files in Git LFS. `harbor
  download` without `git-lfs` installed leaves 133-byte pointer files, so
  the databases here were fetched from the registry's pinned Hugging Face
  commit and verified against the pointer's sha256.
- `dabstep-*` download their data from the `adyen/DABstep` Hugging Face
  repository while the Docker image builds. That source is not pinned to a
  revision, and the build needs internet access.

Run the whole set with `--path` instead of `--dataset`:

```bash
uv run devopsagent-eval \
  --path evaluation/tasks/data-query \
  --variant /home/ec2-user/workspace/my-workspace/my_strands_agent/eval/baseline.toml \
  --attempts 1 \
  --n-concurrent 2
```

Expected: the `my-strands-baseline` row shows 10 trials and `errors = 0`.
`--include-task` and `--preset` still filter by task directory name, for
example `--include-task bird-superhero__786` for a single task.

Update the set by adding or removing task directories. To add a public task,
download its dataset into an empty scratch directory and copy the task
directory:

```bash
mkdir -p /tmp/harbor-candidates
uv run harbor download bird-bench@parity -o /tmp/harbor-candidates
uv run harbor download dabstep@1.0 -o /tmp/harbor-candidates
cp -r /tmp/harbor-candidates/dabstep/<task-name> evaluation/tasks/data-query/
```

For a `bird-bench` task, replace the LFS pointer before running it. Read the
`oid sha256:` line in the pointer, then download and verify the real file:

```bash
TASK=<task-name>
COMMIT=82d1fb0c144d28b1fd9852006cee0a39e74bd4a8
curl -fL -o db.sqlite \
  "https://huggingface.co/datasets/harborframework/harbor-datasets/resolve/$COMMIT/datasets/bird-bench/$TASK/environment/db.sqlite"
sha256sum db.sqlite
```

The commit comes from the dataset entry in Harbor's `registry.json`.
Some bird databases are large (`card_games` 250 MB, `codebase_community`
460 MB, `european_football_2` 570 MB). Avoid them unless the repository can
hold that size. Validate every new task with a single-task run before relying
on it.

To compare Agent changes, copy `eval/baseline.toml`, give it a new
`[variant].id`, change only `[parameters]` or `[source].commit`, and pass
both Variants with repeated `--variant` flags.

## Evaluate my_strands_agent on the data query task set

Run from the `devopsagent` repository root. Commit any `my_strands_agent`
changes first, because the Adapter runs the committed snapshot.

All 10 tasks in `evaluation/tasks/data-query/`:

```bash
uv run devopsagent-eval \
  --path evaluation/tasks/data-query \
  --variant /home/ec2-user/workspace/my-workspace/my_strands_agent/eval/baseline.toml \
  --attempts 1 \
  --n-concurrent 2
```

A single task, for example to check a newly added one:

```bash
uv run devopsagent-eval \
  --path evaluation/tasks/data-query \
  --variant /home/ec2-user/workspace/my-workspace/my_strands_agent/eval/baseline.toml \
  --include-task bird-superhero__786 \
  --n-concurrent 1
```

Expected: the `my-strands-baseline` row shows one trial per selected task and
`errors = 0`. Results go to `evaluation/jobs/<timestamp>/`. The task list,
grading rules, and update steps are in "Data query task set" above.
