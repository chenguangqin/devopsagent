# `demomcp` Command Adapter spike

This directory contains the minimal shim and descriptor template for the sibling
`demomcp` repository. The evaluation core never imports Strands, MCP, or the
agent module. Copy `agent_eval_entry.py` and `agent.toml` into the `demomcp`
repository, set each variant's `[source].commit` to a fixed commit, and run it
with `command-agent-eval`.

The only required agent-side refactor is extracting the existing construction
from `main()` into:

```python
def build_agent(mode: str):
    ...
    return agent
```

The function remains in `demomcp`; the shim calls it without reconstructing the
model, MCP client, tools, skills, memory, or workflow.
