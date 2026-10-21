from __future__ import annotations

import io
from pathlib import Path

from devopsagent.protocol import JsonlChannel, LocalToolClient, StdioToolClient


def test_stdio_tool_client_round_trip():
    reader = io.StringIO(
        '{"type":"tool_result","id":"fixed","status":"success","output":"ok"}\n'
    )
    writer = io.StringIO()
    channel = JsonlChannel(reader, writer)
    client = StdioToolClient(channel)

    import uuid

    original = uuid.uuid4
    uuid.uuid4 = lambda: type("Id", (), {"hex": "fixed"})()
    try:
        result = client.call("shell", {"command": "true"})
    finally:
        uuid.uuid4 = original

    assert result["output"] == "ok"
    assert '"type":"tool_call"' in writer.getvalue()
    assert '"id":"fixed"' in writer.getvalue()


def test_local_tool_client_executes_in_workdir(tmp_path: Path):
    client = LocalToolClient(workdir=tmp_path)

    result = client.call("shell", {"command": "pwd"})

    assert result["status"] == "success"
    assert str(tmp_path) in result["output"]


def test_format_exec_result_keeps_head_and_tail():
    from devopsagent.protocol import format_exec_result

    output = format_exec_result(1, "START" + "x" * 5000 + "END", "", 1000)

    assert output.startswith("exit_code: 1")
    assert "START" in output
    assert output.endswith("END\nstderr:\n")
    assert "<truncated" in output
