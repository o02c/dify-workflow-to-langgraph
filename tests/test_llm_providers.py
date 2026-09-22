"""Tests for LLM provider wiring (AWS region/profile resolution, .env discovery)."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dify2langgraph.cli import _credential_hint, _provider_kwargs
from dify2langgraph.llm import LLMConfig, Message
from dify2langgraph.llm.anthropic import AnthropicProvider
from dify2langgraph.llm.bedrock import BedrockProvider

CONFIG = LLMConfig(model="anthropic.claude-3-5-haiku-20241022-v1:0")

AWS_ENV_VARS = ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE")


@pytest.fixture
def no_aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove AWS environment variables so tests do not read the dev machine's config."""
    for name in AWS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def mock_session():
    """Patch boto3.Session and yield the mock so call kwargs can be asserted."""
    with patch("dify2langgraph.llm.bedrock.boto3.Session") as session:
        session.return_value = MagicMock()
        yield session


def session_kwargs(mock_session: MagicMock) -> dict:
    """Return the keyword arguments boto3.Session was constructed with."""
    assert mock_session.call_count == 1
    return mock_session.call_args.kwargs


class TestBedrockRegionResolution:
    """Region must come from the caller or the environment, never a hardcoded default."""

    def test_no_region_anywhere_passes_no_region_name(self, no_aws_env, mock_session):
        """With nothing configured, boto3 resolves the profile's region itself."""
        provider = BedrockProvider(CONFIG)

        assert "region_name" not in session_kwargs(mock_session)
        assert provider.region is None

    def test_aws_default_region_is_used(self, no_aws_env, mock_session, monkeypatch):
        """botocore's own variable is honoured."""
        monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")

        BedrockProvider(CONFIG)

        assert session_kwargs(mock_session)["region_name"] == "eu-central-1"

    def test_aws_region_is_used(self, no_aws_env, mock_session, monkeypatch):
        """AWS_REGION works too, even though botocore alone would ignore it."""
        monkeypatch.setenv("AWS_REGION", "ap-northeast-1")

        BedrockProvider(CONFIG)

        assert session_kwargs(mock_session)["region_name"] == "ap-northeast-1"

    def test_aws_region_wins_over_aws_default_region(
        self, no_aws_env, mock_session, monkeypatch
    ):
        """AWS_REGION is checked first, matching langchain-aws's precedence."""
        monkeypatch.setenv("AWS_REGION", "ap-northeast-1")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

        BedrockProvider(CONFIG)

        assert session_kwargs(mock_session)["region_name"] == "ap-northeast-1"

    def test_explicit_region_wins_over_environment(
        self, no_aws_env, mock_session, monkeypatch
    ):
        """--aws-region overrides both environment variables."""
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

        BedrockProvider(CONFIG, region="ap-northeast-1")

        assert session_kwargs(mock_session)["region_name"] == "ap-northeast-1"


class TestBedrockProfile:
    """profile_name must only be passed when explicitly requested."""

    def test_profile_omitted_when_not_requested(self, no_aws_env, mock_session):
        """Naming a profile drops EnvProvider from the credential chain, so don't."""
        BedrockProvider(CONFIG)

        assert "profile_name" not in session_kwargs(mock_session)

    def test_profile_passed_when_requested(self, no_aws_env, mock_session):
        """An explicit --aws-profile does reach boto3."""
        BedrockProvider(CONFIG, profile="sso-dev")

        assert session_kwargs(mock_session)["profile_name"] == "sso-dev"


class TestProviderKwargs:
    """CLI flags reach create_provider only for the provider they apply to."""

    @staticmethod
    def args(**overrides):
        """Build a namespace-like object with the AWS CLI flags."""
        import argparse

        defaults = {"llm_provider": "bedrock", "aws_region": None, "aws_profile": None}
        return argparse.Namespace(**{**defaults, **overrides})

    def test_non_bedrock_provider_gets_nothing(self):
        """OpenAI's constructor has no region/profile parameters."""
        assert _provider_kwargs(self.args(llm_provider="openai", aws_region="us-east-1")) == {}

    def test_unset_flags_are_omitted(self):
        """Absent flags must not become None kwargs that override env resolution."""
        assert _provider_kwargs(self.args()) == {}

    def test_flags_are_forwarded(self):
        assert _provider_kwargs(
            self.args(aws_region="ap-northeast-1", aws_profile="sso-dev")
        ) == {"region": "ap-northeast-1", "profile": "sso-dev"}


class TestCredentialHint:
    """Opaque botocore credential errors get an actionable follow-up message."""

    @staticmethod
    def args(**overrides):
        import argparse

        return argparse.Namespace(**{"aws_profile": None, **overrides})

    def test_expired_sso_token_suggests_sso_login(self, monkeypatch):
        """botocore's own message never mentions `aws sso login`; ours must."""
        from botocore.exceptions import TokenRetrievalError

        monkeypatch.delenv("AWS_PROFILE", raising=False)
        exc = TokenRetrievalError(provider="sso", error_msg="Token has expired")

        hint = _credential_hint(exc, self.args(aws_profile="sso-dev"))

        assert hint is not None
        assert "aws sso login --profile sso-dev" in hint

    def test_profile_falls_back_to_environment(self, monkeypatch):
        from botocore.exceptions import UnauthorizedSSOTokenError

        monkeypatch.setenv("AWS_PROFILE", "from-env")

        hint = _credential_hint(UnauthorizedSSOTokenError(), self.args())

        assert hint is not None
        assert "aws sso login --profile from-env" in hint

    def test_missing_region_is_explained(self, monkeypatch):
        """The removed us-east-1 default must fail with usable advice."""
        from botocore.exceptions import NoRegionError

        hint = _credential_hint(NoRegionError(), self.args())

        assert hint is not None
        assert "--aws-region" in hint

    def test_unrelated_error_gets_no_hint(self):
        assert _credential_hint(ValueError("boom"), self.args()) is None


class TestAnthropicTemperature:
    """temperature is only sent to SDKs that still accept it.

    anthropic 1.x removed temperature (and top_p) from ``messages.create()``.
    pyproject declares ``anthropic>=0.75.0``, a range that spans both APIs, so the
    provider asks the installed SDK instead of assuming. Passing it to 1.x fails
    the entire call with "unexpected keyword argument 'temperature'" -- which
    reads like a credentials problem and is easy to misdiagnose.
    """

    def _capture_kwargs(self, monkeypatch, create_params: set[str]) -> dict:
        """Build a provider against a faked SDK surface and return the call kwargs."""
        monkeypatch.setattr(
            "dify2langgraph.llm.anthropic._CREATE_PARAMS", frozenset(create_params)
        )
        provider = AnthropicProvider(LLMConfig(model="claude-x", temperature=0.25), api_key="k")

        response = MagicMock()
        response.content = []
        response.usage.input_tokens = 1
        response.usage.output_tokens = 2
        provider.client = MagicMock()
        provider.client.messages.create.return_value = response

        provider.generate([Message(role="user", content="hi")])
        return provider.client.messages.create.call_args.kwargs

    def test_temperature_sent_when_the_sdk_accepts_it(self, monkeypatch):
        """Older SDKs still get the configured sampling temperature."""
        kwargs = self._capture_kwargs(monkeypatch, {"model", "messages", "max_tokens", "temperature"})

        assert kwargs["temperature"] == 0.25

    def test_temperature_omitted_when_the_sdk_rejects_it(self, monkeypatch):
        """anthropic 1.x: the call goes out without it rather than failing."""
        kwargs = self._capture_kwargs(monkeypatch, {"model", "messages", "max_tokens"})

        assert "temperature" not in kwargs
        assert kwargs["model"] == "claude-x"


class TestDotenvDiscovery:
    """An installed converter must find the .env of the directory it is run from."""

    @pytest.mark.parametrize("module", ["openai", "anthropic"])
    def test_env_file_in_cwd_is_loaded(self, tmp_path: Path, module: str) -> None:
        """find_dotenv(usecwd=True) walks up from the working directory, not from
        the provider module -- which lives inside the venv once installed."""
        (tmp_path / ".env").write_text(
            "DIFY2LANGGRAPH_DOTENV_PROBE=loaded\n", encoding="utf-8"
        )

        # A subprocess with cwd=tmp_path is the only faithful check: load_dotenv
        # runs at import time, so it cannot be re-triggered in this process.
        # It must be a script *file*, not `python -c`: without __main__.__file__
        # python-dotenv considers the session interactive and falls back to the
        # working directory on its own, which would pass either way.
        probe = tmp_path / "probe.py"
        probe.write_text(
            textwrap.dedent(
                f"""
                import os
                import dify2langgraph.llm.{module}  # noqa: F401
                print(os.environ.get("DIFY2LANGGRAPH_DOTENV_PROBE", ""))
                """
            ),
            encoding="utf-8",
        )
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")}
        env.pop("DIFY2LANGGRAPH_DOTENV_PROBE", None)

        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "loaded"
