from pathlib import Path

from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths

from evaluation.host_environment import TrustedHostEnvironment


def make_environment(tmp_path: Path) -> TrustedHostEnvironment:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir(parents=True)
    trial_paths = TrialPaths(tmp_path / "trial")
    trial_paths.mkdir()
    return TrustedHostEnvironment(
        environment_dir=environment_dir,
        environment_name="host-test",
        session_id="host-test-session",
        trial_paths=trial_paths,
        task_env_config=EnvironmentConfig(workdir="/workspace"),
    )


async def test_host_environment_exec_and_virtual_paths(tmp_path: Path):
    environment = make_environment(tmp_path)
    await environment.start(force_build=False)

    result = await environment.exec("printf 'HOST_OK\\n' > answer.txt")
    verifier = await environment.exec(
        "test -f /workspace/answer.txt && "
        "printf '1\\n' > /logs/verifier/reward.txt"
    )

    assert result.return_code == 0
    assert verifier.return_code == 0
    assert (environment.workspace / "answer.txt").read_text() == "HOST_OK\n"
    assert environment.trial_paths.reward_text_path.read_text() == "1\n"


async def test_host_environment_upload_and_download(tmp_path: Path):
    environment = make_environment(tmp_path)
    await environment.start(force_build=False)
    source = tmp_path / "source"
    source.mkdir()
    (source / "test.sh").write_text("#!/bin/bash\n")

    await environment.upload_dir(source, "/tests")
    target = tmp_path / "downloaded"
    await environment.download_dir("/tests", target)

    assert (environment.root / "tests" / "test.sh").exists()
    assert (target / "test.sh").exists()


async def test_host_environment_resolves_relative_trial_paths(
    tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    environment = make_environment(Path("jobs"))
    await environment.start(force_build=False)

    result = await environment.exec(
        "printf 'relative\\n' > /logs/verifier/reward.txt"
    )

    assert result.return_code == 0
    assert environment.trial_paths.reward_text_path.read_text() == "relative\n"
