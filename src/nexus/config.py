"""Central configuration. Pulls from .env via pydantic-settings.

Also loads .env into `os.environ` at import time so non-pydantic env reads
(NEXUS_FRONTIER_*, NEXUS_BANNER, NEXUS_RECORD, NEXUS_HOOKS, etc.) see the
values. Without this, .env would only populate the Settings object, not the
process environment, and `os.environ.get('NEXUS_FRONTIER_API_KEY')` elsewhere
would silently return None.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor .env to the repo root so `nexus` works from any CWD.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"

# Load .env into os.environ (never overwrite vars already present).
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        # Hand-rolled minimal .env parser as a fallback
        for _line in _ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ:
                os.environ[_k] = _v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
    )

    # Models
    oracle_primary_model: str = Field(default="qwen3:4b")
    oracle_fast_model: str = Field(default="qwen3:4b")
    # qwen3:30b is the intended primary once VRAM co-hosting with bge-m3 is
    # resolved (either bigger GPU or forced keep_alive=0). Override via .env.
    oracle_embed_model: str = Field(default="bge-m3")
    oracle_ollama_host: str = Field(default="http://localhost:11434")
    oracle_num_ctx: int = Field(default=16384)
    oracle_llm_timeout_sec: float = Field(default=600.0)
    # Embedder keep_alive passed to Ollama. "0s" = unload after each call
    # (good for 24GB GPUs running a big primary). "5m" = default hot.
    oracle_embed_keepalive: str = Field(default="5m")

    # Teacher (optional)
    deepseek_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    # local → use ORACLE_PRIMARY_MODEL as teacher (good enough + no API keys).
    # Switch to "deepseek" or "anthropic" once keys are set.
    oracle_teacher_provider: str = Field(default="local")

    # Storage — default lives inside the repo, so every machine that clones
    # the repo gets a self-contained install. Override via .env if you want
    # memory + skills to live elsewhere (e.g. a synced folder).
    oracle_home: Path = Field(default=_PROJECT_ROOT / "data")
    oracle_log_dir: Path = Field(default=_PROJECT_ROOT / "logs")

    # Identity — safe generic defaults; override per-machine in .env.
    oracle_device_name: str = Field(default="nexus")
    oracle_user: str = Field(default="user")
    # Optional working instance name (§05). Example: "Auctor", "Prime", "Core".
    oracle_instance: str = Field(default="Nexus")

    # Feature flags
    oracle_enable_mesh: bool = Field(default=False)
    oracle_enable_distillation: bool = Field(default=False)
    oracle_sandbox_provider: str = Field(default="docker")


settings = Settings()
settings.oracle_home.mkdir(parents=True, exist_ok=True)
settings.oracle_log_dir.mkdir(parents=True, exist_ok=True)
