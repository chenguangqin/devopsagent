from pathlib import Path


def test_production_package_does_not_import_harbor():
    source_root = Path(__file__).parents[1] / "src" / "devopsagent"
    offenders = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import harbor" in text or "from harbor" in text:
            offenders.append(path)

    assert offenders == []


def test_command_evaluation_core_does_not_import_agent_sdks():
    source_root = (
        Path(__file__).parents[1] / "evaluation" / "command_framework"
    )
    forbidden = ("strands", "langchain", "mcp")
    offenders = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        if any(
            f"import {name}" in text or f"from {name}" in text
            for name in forbidden
        ):
            offenders.append(path)

    assert offenders == []
