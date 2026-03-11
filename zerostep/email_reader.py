"""Read verification emails via IMAP to complete signup flows."""

from __future__ import annotations

import email
import imaplib
import logging
import re
import time
from typing import Any

logger = logging.getLogger("zerostep.email")


def wait_for_verification_email(
    imap_host: str,
    imap_user: str,
    imap_password: str,
    from_filter: str | None = None,
    subject_filter: str | None = None,
    timeout: int = 120,
    poll_interval: int = 5,
    imap_port: int = 993,
) -> dict[str, Any] | None:
    """Poll IMAP inbox for a verification email.

    Args:
        imap_host: IMAP server (e.g., "imap.gmail.com")
        imap_user: Email address
        imap_password: Email password or app password
        from_filter: Only match emails from this sender
        subject_filter: Only match emails with this in subject
        timeout: Max seconds to wait
        poll_interval: Seconds between polls
        imap_port: IMAP SSL port (default 993)

    Returns:
        Dict with: subject, from, body, links (list of URLs), verification_link
    """
    start = time.time()
    logger.info("Waiting for verification email (timeout=%ds)...", timeout)

    while time.time() - start < timeout:
        try:
            result = _check_inbox(
                imap_host,
                imap_user,
                imap_password,
                imap_port,
                from_filter,
                subject_filter,
            )
            if result:
                logger.info("Found verification email: %s", result.get("subject", ""))
                return result
        except Exception as e:
            logger.warning("IMAP check failed: %s", e)

        time.sleep(poll_interval)

    logger.warning("Timed out waiting for verification email")
    return None


def _check_inbox(
    host: str,
    user: str,
    password: str,
    port: int,
    from_filter: str | None,
    subject_filter: str | None,
) -> dict[str, Any] | None:
    """Check inbox for recent verification-like emails."""
    mail = imaplib.IMAP4_SSL(host, port)
    try:
        mail.login(user, password)
        mail.select("INBOX")

        # Search for recent unseen emails
        search_criteria = "(UNSEEN)"
        if from_filter:
            search_criteria = f'(UNSEEN FROM "{from_filter}")'

        _, message_ids = mail.search(None, search_criteria)
        ids = message_ids[0].split()

        if not ids:
            return None

        # Check most recent emails first (last 10)
        for msg_id in reversed(ids[-10:]):
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            raw = msg_data[0]
            if isinstance(raw, tuple):
                raw = raw[1]

            msg = email.message_from_bytes(raw)
            subject = _decode_header(msg.get("Subject", ""))
            sender = _decode_header(msg.get("From", ""))

            # Check subject filter
            if subject_filter and subject_filter.lower() not in subject.lower():
                continue

            # Check if it looks like a verification email
            verification_keywords = [
                "verify",
                "confirm",
                "activate",
                "welcome",
                "api key",
                "registration",
                "sign up",
                "signup",
            ]
            subject_lower = subject.lower()
            is_verification = any(kw in subject_lower for kw in verification_keywords)

            if not is_verification and not subject_filter:
                continue

            # Extract body
            body = _get_body(msg)
            links = _extract_links(body)

            # Find the verification link
            verification_link = _find_verification_link(links)

            return {
                "subject": subject,
                "from": sender,
                "body": body[:2000],  # Truncate
                "links": links,
                "verification_link": verification_link,
            }

        return None

    finally:
        try:
            mail.logout()
        except Exception:
            pass


def _decode_header(value: str) -> str:
    """Decode email header."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded)


def _get_body(msg: email.message.Message) -> str:
    """Extract text body from email."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
            elif content_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _extract_links(text: str) -> list[str]:
    """Extract all URLs from text/HTML."""
    # Match href="..." and plain URLs
    patterns = [
        r'href=["\']([^"\']+)["\']',
        r'(https?://[^\s<>"\']+)',
    ]
    links: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            url = match.group(1)
            if url not in seen and "unsubscribe" not in url.lower():
                seen.add(url)
                links.append(url)
    return links


def _find_verification_link(links: list[str]) -> str | None:
    """Find the most likely verification/confirmation link."""
    verification_patterns = [
        r"verify",
        r"confirm",
        r"activate",
        r"token",
        r"callback",
        r"auth",
        r"validate",
        r"registration",
    ]
    for link in links:
        link_lower = link.lower()
        if any(re.search(p, link_lower) for p in verification_patterns):
            return link

    # If no obvious verification link, return the first non-trivial link
    for link in links:
        if len(link) > 50:  # Long URLs are likely verification links
            return link

    return None
