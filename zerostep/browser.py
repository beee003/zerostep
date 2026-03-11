"""Browser automation for signup and API key retrieval using Playwright."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import Page, async_playwright

from .registry import ServiceConfig

logger = logging.getLogger("zerostep.browser")

# Default password for new accounts (user can override)
DEFAULT_PASSWORD = None  # Must be provided by user


async def _wait_and_fill(page: Page, selector: str, value: str, timeout: int = 10000) -> bool:
    """Wait for a selector and fill it."""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.fill(selector, value)
        return True
    except Exception as e:
        logger.warning("Could not fill %s: %s", selector, e)
        return False


async def _wait_and_click(page: Page, selector: str, timeout: int = 10000) -> bool:
    """Wait for a selector and click it."""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.click(selector)
        return True
    except Exception as e:
        logger.warning("Could not click %s: %s", selector, e)
        return False


async def _handle_oauth_popup(
    page: Page,
    context: Any,
    oauth_email: str,
    oauth_password: str,
    provider: str = "google",
) -> bool:
    """Handle OAuth popup or redirect for Google/GitHub signup.

    Handles both popup windows and same-page redirects.
    Returns True if OAuth flow completed successfully.
    """
    # Google OAuth selectors
    google_email_sel = 'input[type="email"], input#identifierId'
    google_email_next = "#identifierNext, button:has-text('Next')"
    google_pass_sel = 'input[type="password"], input[name="Passwd"]'
    google_pass_next = "#passwordNext, button:has-text('Next')"

    # GitHub OAuth selectors
    github_email_sel = 'input#login_field, input[name="login"]'
    github_pass_sel = 'input#password, input[name="password"]'
    github_submit_sel = 'input[type="submit"], button[type="submit"]'
    github_authorize_sel = 'button#js-oauth-authorize-btn, button:has-text("Authorize")'

    async def _fill_oauth(oauth_page: Page) -> bool:
        """Fill credentials on the OAuth page."""
        await asyncio.sleep(2)  # Let OAuth page load

        if provider == "google":
            # Google multi-step: email → next → password → next
            filled = await _wait_and_fill(oauth_page, google_email_sel, oauth_email, timeout=8000)
            if not filled:
                logger.warning("Could not find Google email field")
                return False
            await asyncio.sleep(0.5)
            await _wait_and_click(oauth_page, google_email_next, timeout=5000)
            await asyncio.sleep(2)

            filled = await _wait_and_fill(oauth_page, google_pass_sel, oauth_password, timeout=8000)
            if not filled:
                logger.warning("Could not find Google password field")
                return False
            await asyncio.sleep(0.5)
            await _wait_and_click(oauth_page, google_pass_next, timeout=5000)
            await asyncio.sleep(3)

        elif provider == "github":
            # GitHub single page: email + password + submit
            filled_email = await _wait_and_fill(
                oauth_page, github_email_sel, oauth_email, timeout=8000
            )
            filled_pass = await _wait_and_fill(
                oauth_page, github_pass_sel, oauth_password, timeout=5000
            )
            if not filled_email or not filled_pass:
                logger.warning("Could not find GitHub login fields")
                return False
            await asyncio.sleep(0.5)
            await _wait_and_click(oauth_page, github_submit_sel, timeout=5000)
            await asyncio.sleep(3)

            # Click "Authorize" if prompted
            await _wait_and_click(oauth_page, github_authorize_sel, timeout=5000)
            await asyncio.sleep(2)

        return True

    # Try popup first: listen for new page event
    try:
        popup_page = await context.wait_for_event("page", timeout=5000)
        logger.info("OAuth opened in popup window")
        await popup_page.wait_for_load_state("networkidle", timeout=15000)
        success = await _fill_oauth(popup_page)
        # Popup should close automatically after auth; wait for redirect back
        await asyncio.sleep(3)
        return success
    except Exception:
        pass

    # No popup — OAuth probably redirected in the same page
    logger.info("OAuth redirected in same page")
    current_url = page.url.lower()
    if "accounts.google.com" in current_url or "github.com/login" in current_url:
        return await _fill_oauth(page)

    # Neither popup nor redirect detected
    logger.warning("Could not detect OAuth flow — may need --no-headless")
    return False


async def signup(
    service: ServiceConfig,
    email: str,
    password: str,
    name: str | None = None,
    headless: bool = True,
    method: str = "email",
    oauth_email: str | None = None,
    oauth_password: str | None = None,
) -> dict[str, Any]:
    """Sign up for a service using browser automation.

    Args:
        method: "email", "google", or "github"
        oauth_email: Google/GitHub email (defaults to email)
        oauth_password: Google/GitHub password (defaults to password)

    Returns:
        Dict with keys: success, needs_verification, api_key, error
    """
    result: dict[str, Any] = {
        "success": False,
        "needs_verification": False,
        "api_key": None,
        "error": None,
    }

    # Validate OAuth method is supported
    if method == "google" and not service.supports_google:
        result["error"] = f"{service.display_name} does not support Google signup"
        return result
    if method == "github" and not service.supports_github:
        result["error"] = f"{service.display_name} does not support GitHub signup"
        return result

    oauth_email = oauth_email or email
    oauth_password = oauth_password or password

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Navigate to signup page
            logger.info("Navigating to %s", service.signup_url)
            await page.goto(service.signup_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(1)  # Let JS settle

            # --- OAuth signup ---
            if method in ("google", "github"):
                logger.info("Using %s OAuth signup", method)
                btn_sel = (
                    service.google_button_selector
                    if method == "google"
                    else service.github_button_selector
                )

                clicked = await _wait_and_click(page, btn_sel, timeout=8000)
                if not clicked:
                    result["error"] = (
                        f"Could not find {method.title()} signup button. Tried: {btn_sel}"
                    )
                    return result

                await asyncio.sleep(2)

                # Handle OAuth login flow
                oauth_ok = await _handle_oauth_popup(
                    page, context, oauth_email, oauth_password, provider=method
                )
                if not oauth_ok:
                    result["error"] = (
                        f"{method.title()} OAuth flow failed. "
                        "Try --no-headless to complete manually."
                    )
                    return result

                # OAuth done — wait for redirect back to service
                await asyncio.sleep(3)
                logger.info("OAuth complete, now on: %s", page.url)

            # --- Email/password signup ---
            else:
                # Fill name if required
                if service.signup_name_selector and name:
                    await _wait_and_fill(page, service.signup_name_selector, name)

                # Fill email
                filled = await _wait_and_fill(page, service.signup_email_selector, email)
                if not filled:
                    result["error"] = f"Could not find email field: {service.signup_email_selector}"
                    return result

                # Fill password
                filled = await _wait_and_fill(page, service.signup_password_selector, password)
                if not filled:
                    result["error"] = (
                        f"Could not find password field: {service.signup_password_selector}"
                    )
                    return result

                # Submit
                await asyncio.sleep(0.5)
                clicked = await _wait_and_click(page, service.signup_submit_selector)
                if not clicked:
                    result["error"] = (
                        f"Could not find submit button: {service.signup_submit_selector}"
                    )
                    return result

                # Wait for navigation
                await asyncio.sleep(3)

            # Run post-signup steps (applies to both email and OAuth)
            for step in service.post_signup_steps:
                action = step.get("action", "click")
                selector = step.get("selector", "")
                value = step.get("value", "")

                if action == "click":
                    await _wait_and_click(page, selector)
                elif action == "fill":
                    await _wait_and_fill(page, selector, value)
                elif action == "wait":
                    await asyncio.sleep(int(value) if value else 2)
                elif action == "goto":
                    await page.goto(value, wait_until="networkidle", timeout=30000)

                await asyncio.sleep(1)

            # Check if we need email verification (usually not for OAuth)
            if method == "email":
                page_text = await page.inner_text("body")
                verification_phrases = [
                    "verify your email",
                    "check your email",
                    "confirmation email",
                    "verify your account",
                    "activation link",
                    "confirm your email",
                ]
                if any(phrase in page_text.lower() for phrase in verification_phrases):
                    result["success"] = True
                    result["needs_verification"] = True
                    logger.info("Email verification required for %s", service.name)
                    return result

            # Try to get API key immediately (some services show it right after signup)
            api_key = await _extract_api_key(page, service)
            if api_key:
                result["success"] = True
                result["api_key"] = api_key
                return result

            # If no key found, try navigating to API key page
            if service.api_key_url:
                await page.goto(service.api_key_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

                # Click "Generate" button if needed
                if service.api_key_button_selector:
                    await _wait_and_click(page, service.api_key_button_selector)
                    await asyncio.sleep(2)

                api_key = await _extract_api_key(page, service)
                if api_key:
                    result["success"] = True
                    result["api_key"] = api_key
                    return result

            result["success"] = True
            result["error"] = "Signup succeeded but could not find API key automatically"

        except Exception as e:
            result["error"] = f"Browser error: {e}"
            logger.exception("Signup failed for %s", service.name)

        finally:
            await browser.close()

    return result


async def login_and_get_key(
    service: ServiceConfig,
    email: str,
    password: str,
    headless: bool = True,
) -> str | None:
    """Log in to an existing account and retrieve the API key."""
    login_url = service.login_url or service.signup_url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(login_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(1)

            await _wait_and_fill(page, service.login_email_selector, email)
            await _wait_and_fill(page, service.login_password_selector, password)
            await asyncio.sleep(0.5)
            await _wait_and_click(page, service.login_submit_selector)
            await asyncio.sleep(3)

            # Navigate to API key page
            if service.api_key_url:
                await page.goto(service.api_key_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(2)

            if service.api_key_button_selector:
                await _wait_and_click(page, service.api_key_button_selector)
                await asyncio.sleep(2)

            return await _extract_api_key(page, service)

        except Exception:
            logger.exception("Login failed for %s", service.name)
            return None

        finally:
            await browser.close()


async def _extract_api_key(page: Page, service: ServiceConfig) -> str | None:
    """Extract API key from the current page."""
    # Try CSS selector first
    if service.api_key_selector:
        try:
            el = await page.wait_for_selector(service.api_key_selector, timeout=5000)
            if el:
                # Try input value first, then text content
                value = await el.get_attribute("value")
                if value and len(value) > 8:
                    return value.strip()
                text = await el.inner_text()
                if text and len(text) > 8:
                    return text.strip()
        except Exception:
            pass

    # Try regex pattern on page text
    if service.api_key_pattern:
        try:
            page_text = await page.inner_text("body")
            match = re.search(service.api_key_pattern, page_text)
            if match:
                return match.group(1) if match.lastindex else match.group(0)
        except Exception:
            pass

    # Generic: look for common API key patterns on page
    try:
        page_text = await page.inner_text("body")
        # Common API key patterns (32+ char hex, prefixed keys, etc.)
        patterns = [
            r"(?:api[_-]?key|token|secret)[:\s]*['\"]?([a-zA-Z0-9_\-]{20,})['\"]?",
            r"\b(sk-[a-zA-Z0-9]{20,})\b",  # OpenAI-style
            r"\b(key-[a-zA-Z0-9]{20,})\b",
            r"\b(xai-[a-zA-Z0-9]{20,})\b",
            r"\b([a-f0-9]{32,64})\b",  # Hex keys
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                key = match.group(1) if match.lastindex else match.group(0)
                if len(key) >= 20:
                    return key
    except Exception:
        pass

    return None
