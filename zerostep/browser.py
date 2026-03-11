"""Browser automation for signup and API key retrieval using Playwright."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import async_playwright, Page

from .registry import ServiceConfig

logger = logging.getLogger("zerostep.browser")

# Default password for new accounts (user can override)
DEFAULT_PASSWORD = None  # Must be provided by user


async def _wait_and_fill(
    page: Page, selector: str, value: str, timeout: int = 10000
) -> bool:
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


async def signup(
    service: ServiceConfig,
    email: str,
    password: str,
    name: str | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """Sign up for a service using browser automation.

    Returns:
        Dict with keys: success, needs_verification, api_key, error
    """
    result: dict[str, Any] = {
        "success": False,
        "needs_verification": False,
        "api_key": None,
        "error": None,
    }

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

            # Fill name if required
            if service.signup_name_selector and name:
                await _wait_and_fill(page, service.signup_name_selector, name)

            # Fill email
            filled = await _wait_and_fill(page, service.signup_email_selector, email)
            if not filled:
                result["error"] = (
                    f"Could not find email field: {service.signup_email_selector}"
                )
                return result

            # Fill password
            filled = await _wait_and_fill(
                page, service.signup_password_selector, password
            )
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

            # Run post-signup steps
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

            # Check if we need email verification
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
                await page.goto(
                    service.api_key_url, wait_until="networkidle", timeout=30000
                )
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
            result["error"] = (
                "Signup succeeded but could not find API key automatically"
            )

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
                await page.goto(
                    service.api_key_url, wait_until="networkidle", timeout=30000
                )
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
