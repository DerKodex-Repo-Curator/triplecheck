"""Role abstraction — loads config, resolves role↔model mapping, instantiates providers."""

from __future__ import annotations

from pathlib import Path

import yaml

from code_review.providers.base import BaseProvider
from code_review.providers.claude_cli import ClaudeCLIProvider
from code_review.providers.codex_cli import CodexCLIProvider
from code_review.providers.openai_compat import OpenAICompatProvider

PROVIDER_MAP = {
    "claude-cli": ClaudeCLIProvider,
    "codex-cli": CodexCLIProvider,
    "openai-compat": OpenAICompatProvider,
}


def load_config(config_path: str | Path) -> dict:
    """Load and validate config.yml."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        cfg = yaml.safe_load(f)
    for key in ("roles", "models", "assignments"):
        if key not in cfg:
            raise ValueError(f"Config missing required key: {key}")

    # Validate nested structure
    if not isinstance(cfg["roles"], dict):
        raise ValueError(f"'roles' must be a dict, got {type(cfg['roles'])}")
    if not isinstance(cfg["models"], dict):
        raise ValueError(f"'models' must be a dict, got {type(cfg['models'])}")
    if not isinstance(cfg["assignments"], dict):
        raise ValueError(f"'assignments' must be a dict, got {type(cfg['assignments'])}")

    return cfg


def load_prompt(role_name: str, cfg: dict, config_dir: Path) -> str:
    """Load the system prompt for a role."""
    role_cfg = cfg["roles"][role_name]
    prompt_file = config_dir / role_cfg["prompt_file"]
    if not str(prompt_file.resolve()).startswith(str(config_dir.resolve())):
        raise ValueError(f'Invalid prompt_file path: {role_cfg["prompt_file"]}')
    if not prompt_file.exists():
        # Fall back to package prompts
        pkg_prompts = Path(__file__).parent / "prompts"
        safe_role_name = Path(role_name).name
        prompt_file = pkg_prompts / f"{safe_role_name}.txt"
        if not prompt_file.exists():
            raise FileNotFoundError(
                f"Prompt not found for role '{role_name}'. "
                f"Checked: {prompt_file}"
            )
    return prompt_file.read_text()


def resolve_provider(
    role_name: str,
    cfg: dict,
    overrides: dict[str, str] | None = None,
) -> BaseProvider:
    """Resolve a role to its provider instance.

    Args:
        role_name: "reviewer", "coder", or "judge"
        cfg: parsed config dict
        overrides: CLI overrides like {"reviewer": "codex"}
    """
    # Determine which model name to use
    overrides = overrides or {}
    model_name = overrides.get(role_name, cfg["assignments"][role_name])

    if model_name not in cfg["models"]:
        raise ValueError(
            f"Model '{model_name}' not found in config. "
            f"Available: {list(cfg['models'].keys())}"
        )

    model_cfg = cfg["models"][model_name]
    if not isinstance(model_cfg, dict):
        raise ValueError(
            f"Model configuration for '{model_name}' must be a dictionary, "
            f"got {type(model_cfg)}"
        )
    provider_name = model_cfg.get("provider", "openai-compat")

    if provider_name not in PROVIDER_MAP:
        raise ValueError(
            f"Unknown provider '{provider_name}'. "
            f"Available: {list(PROVIDER_MAP.keys())}"
        )

    return PROVIDER_MAP[provider_name](model_cfg)
