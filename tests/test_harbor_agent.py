from pathlib import Path

from devopsagent.harbor_agent import DevOpsAgent, DevOpsAgentOptions


def test_harbor_agent_parses_options(tmp_path: Path):
    agent = DevOpsAgent(
        logs_dir=tmp_path,
        model_name="global.anthropic.claude-haiku-5-5",
        max_steps="7",
        region="us-west-2",
    )

    assert isinstance(agent.options, DevOpsAgentOptions)
    assert agent.options.max_steps == 7
    assert agent.options.region == "us-west-2"
    assert agent.to_agent_info().model_info.name == (
        "global.anthropic.claude-haiku-5-5"
    )

