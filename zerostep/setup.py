"""First-run setup — prompts user to configure an LLM API key for Browser Use agent."""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".zerostep"
CONFIG_FILE = CONFIG_DIR / "config"

# Supported LLM providers in priority order
PROVIDERS = [
    {
        "name": "Astrai (recommended)",
        "env_var": "ASTRAI_API_KEY",
        "model": "meta-llama/llama-4-maverick",
        "prefix": "astr-",
        "url": "https://astrai-compute.fly.dev",
        "base_url": "https://astrai-compute.fly.dev/v1",
        "note": "Sign up at astrai-compute.fly.dev — ZeroStep can do this for you!",
    },
    {
        "name": "Anthropic",
        "env_var": "ANTHROPIC_API_KEY",
        "model": "claude-sonnet-4-5-20250514",
        "prefix": "sk-ant-",
        "url": "https://console.anthropic.com/settings/keys",
    },
    {
        "name": "OpenAI",
        "env_var": "OPENAI_API_KEY",
        "model": "gpt-4o",
        "prefix": "sk-",
        "url": "https://platform.openai.com/api-keys",
    },
    {
        "name": "Google (Gemini)",
        "env_var": "GOOGLE_API_KEY",
        "model": "gemini-2.0-flash",
        "prefix": "AI",
        "url": "https://aistudio.google.com/apikey",
    },
    {
        "name": "Moonshot AI (Kimi)",
        "env_var": "MOONSHOT_API_KEY",
        "model": "moonshot-v1-auto",
        "prefix": "",
        "url": "https://platform.moonshot.ai/console/account",
        "base_url": "https://api.moonshot.cn/v1",
    },
]


def get_llm_config() -> dict | None:
    """Get the configured LLM provider. Returns dict with env_var, model, name or None."""

    def _make_config(provider: dict, api_key: str) -> dict:
        config = {
            "env_var": provider["env_var"],
            "api_key": api_key,
            "model": provider["model"],
            "name": provider["name"],
        }
        if "base_url" in provider:
            config["base_url"] = provider["base_url"]
        return config

    # Check env vars first (highest priority)
    for provider in PROVIDERS:
        key = os.environ.get(provider["env_var"])
        if key and len(key) > 10:
            return _make_config(provider, key)

    # Check config file
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                var, val = line.split("=", 1)
                var, val = var.strip(), val.strip()
                for provider in PROVIDERS:
                    if var == provider["env_var"] and val and len(val) > 10:
                        # Also set in env so browser-use can find it
                        os.environ[var] = val
                        return _make_config(provider, val)

    return None


def run_setup(force: bool = False) -> dict:
    """Interactive setup — prompts user to pick an LLM provider and enter API key.

    Returns config dict with env_var, api_key, model, name.
    """
    existing = get_llm_config()
    if existing and not force:
        return existing

    print()
    print("  ZeroStep Setup")
    print("  ─────────────────────────────────────────")
    print("  ZeroStep uses an AI agent (Browser Use) to navigate")
    print("  signup pages. This requires an LLM API key.")
    print()
    print("  You only need to do this once.")
    print()
    print("  Pick your LLM provider:")
    print()

    for i, p in enumerate(PROVIDERS, 1):
        print(f"    {i}. {p['name']:20s} (model: {p['model']})")
        note = p.get("note", f"Get key: {p['url']}")
        print(f"       {note}")
    print()

    n = len(PROVIDERS)
    choices = "/".join(str(i) for i in range(1, n + 1))
    while True:
        try:
            choice = input(f"  Choice [{choices}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < n:
                break
        except (ValueError, EOFError):
            pass
        print(f"  Please enter a number from 1 to {n}")

    provider = PROVIDERS[idx]
    print()
    print(f"  Selected: {provider['name']}")
    print(f"  Get your key at: {provider['url']}")
    print()

    while True:
        try:
            api_key = input(f"  Paste your {provider['env_var']}: ").strip()
        except EOFError:
            print("\n  Setup cancelled.")
            raise SystemExit(1)

        if api_key and len(api_key) > 10:
            break
        print("  Key looks too short. Please paste the full key.")

    # Save to config file
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    if CONFIG_FILE.exists():
        lines = CONFIG_FILE.read_text().splitlines()

    # Update or add the key
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith(provider["env_var"]):
            lines[i] = f"{provider['env_var']}={api_key}"
            updated = True
            break
    if not updated:
        lines.append(f"{provider['env_var']}={api_key}")

    CONFIG_FILE.write_text("\n".join(lines) + "\n")
    CONFIG_FILE.chmod(0o600)  # Restrict permissions

    # Set in current env
    os.environ[provider["env_var"]] = api_key

    print()
    print(f"  Saved to {CONFIG_FILE}")
    print(f"  {provider['env_var']} is now configured.")
    print()

    config = {
        "env_var": provider["env_var"],
        "api_key": api_key,
        "model": provider["model"],
        "name": provider["name"],
    }
    if "base_url" in provider:
        config["base_url"] = provider["base_url"]
    return config


def ensure_llm_configured() -> dict:
    """Check if LLM is configured, run setup if not. Returns config dict."""
    config = get_llm_config()
    if config:
        return config
    return run_setup()
