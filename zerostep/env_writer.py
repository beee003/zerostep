"""Write API keys to .env files safely."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("zerostep.env")


def write_to_env(
    key_name: str,
    key_value: str,
    env_path: str | Path | None = None,
) -> str:
    """Write or update an API key in a .env file.

    Args:
        key_name: Environment variable name (e.g., "EIA_API_KEY")
        key_value: The API key value
        env_path: Path to .env file (default: .env in current directory)

    Returns:
        Absolute path to the .env file that was written
    """
    if env_path is None:
        env_path = Path.cwd() / ".env"
    else:
        env_path = Path(env_path)

    # Read existing content
    lines: list[str] = []
    found = False

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{key_name}="):
                    lines.append(f"{key_name}={key_value}\n")
                    found = True
                    logger.info("Updated existing %s in %s", key_name, env_path)
                else:
                    lines.append(line)

    if not found:
        # Add to end with a newline separator if file has content
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append(f"{key_name}={key_value}\n")
        logger.info("Added %s to %s", key_name, env_path)

    # Write atomically
    tmp_path = env_path.with_suffix(".env.tmp")
    with open(tmp_path, "w") as f:
        f.writelines(lines)
    tmp_path.rename(env_path)

    return str(env_path.resolve())


def read_from_env(key_name: str, env_path: str | Path | None = None) -> str | None:
    """Read an API key from a .env file."""
    if env_path is None:
        env_path = Path.cwd() / ".env"
    else:
        env_path = Path(env_path)

    if not env_path.exists():
        return None

    with open(env_path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith(f"{key_name}="):
                return stripped[len(key_name) + 1 :].strip().strip("\"'")

    return None
