from pathlib import Path

from evaluation.harbor_adapter import (
    CliAgentOptions,
    LangChainCliHarborAgent,
    NativeCliHarborAgent,
    StrandsCliHarborAgent,
)


def test_harbor_adapters_parse_options_and_select_engine(tmp_path: Path):
    classes = [
        (NativeCliHarborAgent, "native"),
        (LangChainCliHarborAgent, "langchain"),
        (StrandsCliHarborAgent, "strands"),
    ]

    for adapter_class, engine in classes:
        agent = adapter_class(
            logs_dir=tmp_path / engine,
            model_name="global.anthropic.claude-haiku-4-5-20251001-v1:0",
            max_steps="7",
            region="us-west-2",
        )
        assert isinstance(agent.options, CliAgentOptions)
        assert agent.options.max_steps == 7
        assert agent.engine == engine
        assert agent.to_agent_info().model_info.name == (
            "global.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
