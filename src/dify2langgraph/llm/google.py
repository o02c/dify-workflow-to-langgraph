"""Google Gemini LLM provider.

Closes a gap between the two places this project talks to an LLM. The generated
``llm.py`` has supported google all along -- it is even the run-time default --
but the converter's own registry did not, so someone holding only a Google API
key could run a generated workflow yet could not use ``--name-nodes`` or the
LLM node-body pass at all.
"""

import os
from typing import Any

from dotenv import find_dotenv, load_dotenv
from google import genai
from google.genai import types

from .base import LLMConfig, LLMProvider, LLMResponse, Message

# usecwd=True: search upward from the working directory, not from this file.
# Once installed (uv sync / pip install) this module lives inside the venv,
# so the default file-relative search never reaches the user's .env.
load_dotenv(find_dotenv(usecwd=True))


class GoogleProvider(LLMProvider):
    """Google Gemini provider.

    Example models:
    - gemini-2.5-flash
    - gemini-2.5-pro
    """

    def __init__(
        self,
        config: LLMConfig,
        api_key: str | None = None,
    ) -> None:
        """Initialize the Google provider.

        Args:
            config: LLM configuration.
            api_key: Google API key. Falls back to GOOGLE_API_KEY, then
                GEMINI_API_KEY -- the SDK accepts either, and the generated
                ``llm.py`` reads the same variables.
        """
        super().__init__(config)

        self.client = genai.Client(
            api_key=api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY"),
        )

    @property
    def name(self) -> str:
        """Provider name."""
        return "google"

    def generate(self, messages: list[Message]) -> LLMResponse:
        """Generate a response using Gemini.

        Args:
            messages: List of messages in the conversation.

        Returns:
            LLM response with generated content.
        """
        # Gemini takes the system prompt as a separate config field rather than
        # as a message, and only knows the roles "user" and "model".
        system_parts: list[str] = []
        contents: list[types.Content] = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
                continue
            role = "model" if msg.role == "assistant" else "user"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=msg.content)])
            )

        config_kwargs: dict[str, Any] = {
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_tokens,
            **self.config.extra,
        }
        if system_parts:
            config_kwargs["system_instruction"] = "\n\n".join(system_parts)

        response = self.client.models.generate_content(
            model=self.config.model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        usage = {}
        if response.usage_metadata:
            usage = {
                "input_tokens": response.usage_metadata.prompt_token_count or 0,
                "output_tokens": response.usage_metadata.candidates_token_count or 0,
            }

        return LLMResponse(
            content=response.text or "",
            model=self.config.model,
            usage=usage,
            raw=response,
        )


# Convenience model constants
GEMINI_FLASH = "gemini-2.5-flash"
GEMINI_PRO = "gemini-2.5-pro"
