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
