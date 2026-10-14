from pathlib import Path


def test_production_package_does_not_import_harbor():
    source_root = Path(__file__).parents[1] / "src" / "devopsagent"
    offenders = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import harbor" in text or "from harbor" in text:
            offenders.append(path)

    assert offenders == []
