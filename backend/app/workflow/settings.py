"""LLM settings for the audit workflow, sourced from the environment.

Per the team plan (`docs/00_setup/plans/2026-08-15-backend-mvp-agent-team-plan.md`):
endpoint, model and key come from `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` /
`DEEPSEEK_API_KEY`. Real keys live only in `backend/.env`; loading that file
is the application entrypoint's responsibility (services/main), this module
only reads `os.environ`. Never log or persist the key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

ENV_BASE_URL = "DEEPSEEK_BASE_URL"
ENV_MODEL = "DEEPSEEK_MODEL"
ENV_API_KEY = "DEEPSEEK_API_KEY"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class WorkflowLLMSettings:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: Optional[str] = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(
        cls, environ: Optional[Mapping[str, str]] = None
    ) -> "WorkflowLLMSettings":
        env = environ if environ is not None else os.environ
        return cls(
            base_url=env.get(ENV_BASE_URL, DEFAULT_BASE_URL),
            model=env.get(ENV_MODEL, DEFAULT_MODEL),
            api_key=env.get(ENV_API_KEY) or None,
        )
