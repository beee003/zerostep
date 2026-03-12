"""Browser Use agent — LLM-driven browser automation for signup flows.

Instead of hardcoded CSS selectors, this uses an AI agent that can see the page
and figure out what to click, type, and navigate. Much more robust against
layout changes, CAPTCHAs, and OAuth flows.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from .registry import ServiceConfig
from .setup import ensure_llm_configured

logger = logging.getLogger("zerostep.agent")


def _build_llm(config: dict) -> Any:
    """Build LLM instance from config."""
    env_var = config["env_var"]
    model = config["model"]
    base_url = config.get("base_url")

    if env_var == "ASTRAI_API_KEY":
        from browser_use import ChatOpenAI

        # Astrai uses OpenAI-compatible API
        return ChatOpenAI(
            model=model,
            api_key=os.environ.get("ASTRAI_API_KEY"),
            base_url=base_url or "https://astrai-compute.fly.dev/v1",
        )
    elif env_var == "ANTHROPIC_API_KEY":
        from browser_use import ChatAnthropic

        return ChatAnthropic(model=model)
    elif env_var == "OPENAI_API_KEY":
        from browser_use import ChatOpenAI

        return ChatOpenAI(model=model)
    elif env_var == "GOOGLE_API_KEY":
        from browser_use import ChatOpenAI

        # Gemini through OpenAI-compatible API
        return ChatOpenAI(
            model=f"gemini/{model}",
            api_key=os.environ.get("GOOGLE_API_KEY"),
        )
    elif env_var == "MOONSHOT_API_KEY":
        from browser_use import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=os.environ.get("MOONSHOT_API_KEY"),
            base_url=base_url or "https://api.moonshot.cn/v1",
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {env_var}")


def _build_task(
    service: ServiceConfig,
    email: str,
    password: str,
    method: str = "email",
    oauth_email: str | None = None,
    oauth_password: str | None = None,
) -> str:
    """Build the natural language task for the Browser Use agent."""
    method_instructions = {
        "email": f"""
Sign up using email and password:
- Email: {email}
- Password: {password}
- Fill in the signup form and submit it""",
        "google": f"""
Sign up using Google OAuth:
- Click the "Sign up with Google" or "Continue with Google" button
- On the Google login page, enter email: {oauth_email or email}
- Enter password: {oauth_password or password}
- Complete any 2FA or consent screens
- Wait to be redirected back to the service""",
        "github": f"""
Sign up using GitHub OAuth:
- Click the "Sign up with GitHub" or "Continue with GitHub" button
- On the GitHub login page, enter username/email: {oauth_email or email}
- Enter password: {oauth_password or password}
- If asked to authorize, click "Authorize"
- Wait to be redirected back to the service""",
    }

    task = f"""You are signing up for {service.display_name} and getting an API key.

STEP 1: SIGN UP
Go to {service.signup_url}
{method_instructions.get(method, method_instructions["email"])}

STEP 2: HANDLE VERIFICATION
- If the page says "verify your email" or "check your email", report that email verification is needed.
- If you see a CAPTCHA, pause and wait (the human will solve it).
- If signup succeeded, continue to step 3.

STEP 3: GET THE API KEY
- Navigate to the API key page: {service.api_key_url}
- Look for an API key on the page. It might be in a code block, input field, or settings panel.
- The key pattern looks like: {service.api_key_pattern or "a long alphanumeric string"}
- The env var name is: {service.env_var}
- If there's a "Generate API Key" or "Create API Key" button, click it first.
- If you need to create a project first (e.g., Supabase), create one with name "zerostep-default".

IMPORTANT:
- Do NOT make up or hallucinate an API key. Only return a key you actually see on the page.
- If you cannot find the key, say "NO_KEY_FOUND" and describe what you see instead.
- Return ONLY the API key value as your final result, nothing else.
"""
    return task


async def agent_signup(
    service: ServiceConfig,
    email: str,
    password: str,
    method: str = "email",
    oauth_email: str | None = None,
    oauth_password: str | None = None,
    headless: bool = True,
    proxy: str | None = None,
    max_steps: int = 20,
) -> dict[str, Any]:
    """Run the Browser Use agent to sign up and get an API key.

    Returns:
        Dict with keys: success, needs_verification, api_key, error
    """
    result: dict[str, Any] = {
        "success": False,
        "needs_verification": False,
        "api_key": None,
        "error": None,
    }

    # Ensure LLM is configured
    try:
        llm_config = ensure_llm_configured()
    except SystemExit:
        result["error"] = "LLM not configured. Run 'zerostep setup' first."
        return result

    logger.info("Using %s (%s) for browser agent", llm_config["name"], llm_config["model"])

    try:
        from browser_use import Agent, Browser
    except ImportError:
        result["error"] = "browser-use not installed. Run: pip install 'zerostep[agent]'"
        return result

    # Build LLM and browser
    llm = _build_llm(llm_config)

    # Disable vision for free/open-source models (they're too slow for screenshots)
    # Vision is only fast enough with GPT-4o, Claude, or Gemini with their own API keys
    use_vision = llm_config["env_var"] in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")

    browser_kwargs: dict[str, Any] = {
        "headless": headless,
        "chromium_sandbox": False,
    }
    if proxy:
        browser_kwargs["proxy"] = {"server": proxy}

    browser = Browser(**browser_kwargs)

    # Build the task
    task = _build_task(service, email, password, method, oauth_email, oauth_password)

    logger.info("Starting Browser Use agent for %s (vision=%s)", service.name, use_vision)

    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            use_vision=use_vision,
            max_actions_per_step=5,
            step_timeout=120,
        )

        history = await agent.run(max_steps=max_steps)
        raw_result = history.final_result() or ""

        logger.info("Agent finished. Result: %s", raw_result[:200])

        # Parse result
        if "NO_KEY_FOUND" in raw_result:
            result["success"] = True
            result["error"] = f"Agent could not find API key: {raw_result}"
        elif "verify" in raw_result.lower() and "email" in raw_result.lower():
            result["success"] = True
            result["needs_verification"] = True
        else:
            # Try to extract an API key from the result
            api_key = _extract_key_from_result(raw_result, service)
            if api_key:
                result["success"] = True
                result["api_key"] = api_key
            else:
                result["success"] = True
                result["error"] = (
                    f"Agent finished but could not parse API key from result: {raw_result[:200]}"
                )

    except Exception as e:
        result["error"] = f"Agent error: {e}"
        logger.exception("Browser Use agent failed for %s", service.name)
    finally:
        try:
            await browser.stop()
        except Exception:
            pass

    return result


def _extract_key_from_result(text: str, service: ServiceConfig) -> str | None:
    """Try to extract an API key from the agent's result text."""
    # Try service-specific pattern first
    if service.api_key_pattern:
        match = re.search(service.api_key_pattern, text)
        if match:
            return match.group(1) if match.lastindex else match.group(0)

    # Generic patterns
    patterns = [
        r"(sk-ant-[a-zA-Z0-9_\-]{20,})",  # Anthropic
        r"(sk-[a-zA-Z0-9]{20,})",  # OpenAI
        r"(eyJ[a-zA-Z0-9_\-]{100,})",  # JWT (Supabase)
        r"(phc_[a-zA-Z0-9]{20,})",  # PostHog
        r"(re_[a-zA-Z0-9_]{20,})",  # Resend
        r"(fc-[a-zA-Z0-9_\-]{20,})",  # Firecrawl
        r"(BSA[a-zA-Z0-9_\-]{20,})",  # Brave
        r"(xai-[a-zA-Z0-9]{20,})",  # xAI
        r"\b([a-zA-Z0-9]{32,64})\b",  # Generic hex/alphanum
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            key = match.group(1) if match.lastindex else match.group(0)
            # Sanity check — skip if it looks like a hash or UUID
            if len(key) >= 20 and not key.startswith("0000"):
                return key

    # Last resort: if the result is just a key-like string
    text = text.strip()
    if len(text) >= 20 and len(text) <= 200 and " " not in text:
        return text

    return None
