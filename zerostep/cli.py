"""CLI entry point for ZeroStep."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from .browser import login_and_get_key, signup
from .email_reader import wait_for_verification_email
from .env_writer import write_to_env
from .registry import list_services, load_service, search_services


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="zerostep",
        description="AI agent that signs up for services and gets your API keys.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- get ---
    get_parser = sub.add_parser("get", help="Sign up and get an API key")
    get_parser.add_argument("service", help="Service name (e.g., eia, supabase)")
    get_parser.add_argument("--email", help="Email to sign up with")
    get_parser.add_argument("--password", help="Password for the account")
    get_parser.add_argument("--name", help="Full name (if required)")
    get_parser.add_argument(
        "--method",
        choices=["email", "google", "github"],
        default="email",
        help="Signup method: email (default), google, or github",
    )
    get_parser.add_argument("--google-email", help="Google account email (if different)")
    get_parser.add_argument("--google-password", help="Google account password")
    get_parser.add_argument("--github-email", help="GitHub account email (if different)")
    get_parser.add_argument("--github-password", help="GitHub account password")
    get_parser.add_argument(
        "--proxy", help="Proxy URL (e.g. http://user:pass@host:port, socks5://host:port)"
    )
    get_parser.add_argument("--env-file", default=".env", help="Path to .env file")
    get_parser.add_argument("--no-headless", action="store_true", help="Show browser")
    get_parser.add_argument("--skip-email-verify", action="store_true")
    get_parser.add_argument("--imap-host", help="IMAP server for email verification")
    get_parser.add_argument("--imap-password", help="IMAP password (or app password)")

    # --- list ---
    sub.add_parser("list", help="List all supported services")

    # --- search ---
    search_parser = sub.add_parser("search", help="Search services")
    search_parser.add_argument("query", help="Search query")

    # --- info ---
    info_parser = sub.add_parser("info", help="Show service details")
    info_parser.add_argument("service", help="Service name")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s %(levelname)s %(message)s",
    )

    if args.command == "list":
        _cmd_list()
    elif args.command == "search":
        _cmd_search(args.query)
    elif args.command == "info":
        _cmd_info(args.service)
    elif args.command == "get":
        asyncio.run(_cmd_get(args))
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_list() -> None:
    services = list_services()
    if not services:
        print("No services configured. Add YAML files to services/ directory.")
        return

    print(f"\n  {len(services)} supported services:\n")
    for name in services:
        try:
            svc = load_service(name)
            difficulty_icon = {"easy": "+", "medium": "~", "hard": "!"}
            icon = difficulty_icon.get(svc.difficulty, "?")
            captcha = " [CAPTCHA]" if svc.has_captcha else ""
            free = f" ({svc.free_tier})" if svc.free_tier else ""
            print(f"  [{icon}] {svc.name:20s} {svc.display_name}{free}{captcha}")
        except Exception:
            print(f"  [?] {name:20s} (config error)")
    print()
    print("  Difficulty: [+] easy  [~] medium  [!] hard (CAPTCHA/phone)")
    print()


def _cmd_search(query: str) -> None:
    results = search_services(query)
    if not results:
        print(f"No services matching '{query}'")
        return

    print(f"\n  {len(results)} services matching '{query}':\n")
    for svc in results:
        print(f"  {svc.name:20s} {svc.display_name}")
        if svc.free_tier:
            print(f"  {'':20s} Free tier: {svc.free_tier}")
    print()


def _cmd_info(service_name: str) -> None:
    try:
        svc = load_service(service_name)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"\n  {svc.display_name} ({svc.name})")
    print(f"  {'─' * 40}")
    print(f"  Env var:        {svc.env_var}")
    print(f"  Signup URL:     {svc.signup_url}")
    print(f"  API key page:   {svc.api_key_url}")
    print(f"  Category:       {svc.category}")
    print(f"  Difficulty:     {svc.difficulty}")
    print(f"  Email verify:   {'Yes' if svc.has_email_verification else 'No'}")
    print(f"  CAPTCHA:        {'Yes' if svc.has_captcha else 'No'}")
    print(f"  Phone verify:   {'Yes' if svc.has_phone_verification else 'No'}")
    print(f"  Credit card:    {'Yes' if svc.requires_credit_card else 'No'}")
    methods = ["email"]
    if svc.supports_google:
        methods.append("google")
    if svc.supports_github:
        methods.append("github")
    print(f"  Signup methods: {', '.join(methods)}")
    if svc.free_tier:
        print(f"  Free tier:      {svc.free_tier}")
    if svc.docs_url:
        print(f"  Docs:           {svc.docs_url}")
    print()


async def _cmd_get(args: argparse.Namespace) -> None:
    try:
        svc = load_service(args.service)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    email_addr = args.email or os.environ.get("ZEROSTEP_EMAIL")
    password = args.password or os.environ.get("ZEROSTEP_PASSWORD")

    if not email_addr:
        print("Error: --email required (or set ZEROSTEP_EMAIL)")
        sys.exit(1)
    if not password:
        print("Error: --password required (or set ZEROSTEP_PASSWORD)")
        sys.exit(1)

    method = args.method

    # Resolve OAuth credentials
    oauth_email = None
    oauth_password = None
    if method == "google":
        if not svc.supports_google:
            print(f"Error: {svc.display_name} does not support Google signup")
            print("  Use --method=email or --method=github instead")
            sys.exit(1)
        oauth_email = args.google_email or os.environ.get("ZEROSTEP_GOOGLE_EMAIL") or email_addr
        oauth_password = (
            args.google_password or os.environ.get("ZEROSTEP_GOOGLE_PASSWORD") or password
        )
    elif method == "github":
        if not svc.supports_github:
            print(f"Error: {svc.display_name} does not support GitHub signup")
            print("  Use --method=email or --method=google instead")
            sys.exit(1)
        oauth_email = args.github_email or os.environ.get("ZEROSTEP_GITHUB_EMAIL") or email_addr
        oauth_password = (
            args.github_password or os.environ.get("ZEROSTEP_GITHUB_PASSWORD") or password
        )

    if svc.has_captcha:
        print(f"Warning: {svc.display_name} has CAPTCHA. Use --no-headless to solve manually.")

    method_label = {"email": "email+password", "google": "Google OAuth", "github": "GitHub OAuth"}
    print(f"\n  ZeroStep: Getting API key for {svc.display_name}")
    print(f"  {'─' * 40}")
    print(f"  Email:    {email_addr}")
    print(f"  Method:   {method_label[method]}")
    print(f"  Env var:  {svc.env_var}")
    print(f"  Env file: {args.env_file}")
    print()

    # Step 1: Sign up
    print(f"  [1/3] Signing up via {method_label[method]}...")
    proxy = args.proxy or os.environ.get("ZEROSTEP_PROXY")
    result = await signup(
        svc,
        email=email_addr,
        password=password,
        name=args.name,
        headless=not args.no_headless,
        method=method,
        oauth_email=oauth_email,
        oauth_password=oauth_password,
        proxy=proxy,
    )

    if not result["success"]:
        print(f"  FAILED: {result['error']}")
        sys.exit(1)

    # Step 2: Email verification
    if result["needs_verification"] and not args.skip_email_verify:
        print("  [2/3] Waiting for verification email...")

        imap_host = args.imap_host or os.environ.get("ZEROSTEP_IMAP_HOST")
        imap_pass = args.imap_password or os.environ.get("ZEROSTEP_IMAP_PASSWORD", password)

        if not imap_host:
            # Auto-detect from email domain
            domain = email_addr.split("@")[1]
            imap_hosts = {
                "gmail.com": "imap.gmail.com",
                "outlook.com": "imap-mail.outlook.com",
                "hotmail.com": "imap-mail.outlook.com",
                "yahoo.com": "imap.mail.yahoo.com",
                "icloud.com": "imap.mail.me.com",
            }
            imap_host = imap_hosts.get(domain, f"imap.{domain}")

        email_result = wait_for_verification_email(
            imap_host=imap_host,
            imap_user=email_addr,
            imap_password=imap_pass,
            timeout=120,
        )

        if email_result and email_result.get("verification_link"):
            print("  Found verification link, clicking...")
            # Use browser to click verification link
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=not args.no_headless)
                page = await browser.new_page()
                await page.goto(email_result["verification_link"], timeout=30000)
                import asyncio

                await asyncio.sleep(3)
                await browser.close()
            print("  Email verified.")
        else:
            print("  Could not find verification email automatically.")
            print("  Please verify manually, then press Enter to continue...")
            input()

        # Step 3: Log in and get API key
        print("  [3/3] Logging in to get API key...")
        api_key = await login_and_get_key(
            svc,
            email=email_addr,
            password=password,
            headless=not args.no_headless,
        )
    elif result["api_key"]:
        api_key = result["api_key"]
        print("  [2/3] No email verification needed.")
        print("  [3/3] Got API key directly from signup.")
    else:
        print("  [2/3] Skipped email verification.")
        print("  [3/3] Logging in to get API key...")
        api_key = await login_and_get_key(
            svc,
            email=email_addr,
            password=password,
            headless=not args.no_headless,
        )

    if api_key:
        env_path = write_to_env(svc.env_var, api_key, args.env_file)
        print("\n  SUCCESS")
        print(f"  {svc.env_var}={api_key[:8]}...{api_key[-4:]}")
        print(f"  Written to {env_path}")
    else:
        print("\n  Signup succeeded but could not extract API key automatically.")
        print(f"  Try logging in manually at: {svc.api_key_url}")

    print()


if __name__ == "__main__":
    main()
