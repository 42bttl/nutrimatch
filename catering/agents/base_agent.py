from __future__ import annotations

import os

import anthropic


class BaseAgent:
    _client: anthropic.Anthropic | None = None

    @classmethod
    def _get_client(cls) -> anthropic.Anthropic:
        if cls._client is None:
            cls._client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY", "")
            )
        return cls._client

    @classmethod
    def _call_claude(
        cls,
        system: str,
        user: str,
        max_tokens: int = 4096,
        model: str = "claude-sonnet-4-6",
    ) -> str:
        msg = cls._get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text
