"""Service registry — loads YAML configs for each supported service."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path

SERVICES_DIR = Path(__file__).parent.parent / "services"


@dataclass
class ServiceConfig:
    """Configuration for a single service's signup + API key flow."""

    name: str
    display_name: str
    signup_url: str
    api_key_url: str  # URL where API key is found after login
    env_var: str  # e.g. "EIA_API_KEY"

    # Signup form
    has_email_verification: bool = True
    has_captcha: bool = False
    has_phone_verification: bool = False
    requires_credit_card: bool = False

    # Selectors (CSS selectors for the signup flow)
    signup_email_selector: str = 'input[type="email"], input[name="email"]'
    signup_password_selector: str = 'input[type="password"], input[name="password"]'
    signup_name_selector: str | None = None
    signup_submit_selector: str = 'button[type="submit"]'

    # API key page selectors
    api_key_selector: str | None = None  # CSS selector for the key element
    api_key_button_selector: str | None = None  # "Generate API Key" button
    api_key_pattern: str | None = None  # Regex to extract key from page text

    # Login (for returning to get key after email verification)
    login_url: str | None = None
    login_email_selector: str = 'input[type="email"], input[name="email"]'
    login_password_selector: str = 'input[type="password"], input[name="password"]'
    login_submit_selector: str = 'button[type="submit"]'

    # Extra steps after signup (list of {action, selector, value?} dicts)
    post_signup_steps: list[dict[str, str]] = field(default_factory=list)

    # Metadata
    docs_url: str | None = None
    free_tier: str | None = None
    category: str = "general"
    difficulty: str = "easy"  # easy, medium, hard


def load_service(name: str) -> ServiceConfig:
    """Load a service config by name."""
    yaml_path = SERVICES_DIR / f"{name}.yaml"
    if not yaml_path.exists():
        # Try case-insensitive match
        for f in SERVICES_DIR.glob("*.yaml"):
            if f.stem.lower() == name.lower():
                yaml_path = f
                break
        else:
            raise ValueError(
                f"Unknown service: {name}. Available: {', '.join(list_services())}"
            )

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    return ServiceConfig(**data)


def list_services() -> list[str]:
    """List all available service names."""
    if not SERVICES_DIR.exists():
        return []
    return sorted(f.stem for f in SERVICES_DIR.glob("*.yaml"))


def search_services(query: str) -> list[ServiceConfig]:
    """Search services by name or category."""
    query = query.lower()
    results = []
    for name in list_services():
        try:
            svc = load_service(name)
            if (
                query in svc.name.lower()
                or query in svc.display_name.lower()
                or query in svc.category.lower()
                or (svc.free_tier and query in svc.free_tier.lower())
            ):
                results.append(svc)
        except Exception:
            pass
    return results
