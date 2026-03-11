# ZeroStep — Get API keys automatically

Use this skill when the user needs an API key for a service. Instead of manually signing up, this skill automates the entire flow: signup → email verification → API key extraction → .env configuration.

## Usage

```
/get-api <service_name>
```

## How to execute

1. Check if the service is supported by looking in the `services/` directory for a matching YAML file
2. Ask the user for their email if not already known (check ZEROSTEP_EMAIL env var first)
3. Generate a secure password or ask the user
4. Run the ZeroStep CLI:

```bash
cd ~/zerostep && python3 -m zerostep.cli get <service> --email <email> --password <password>
```

5. If the service requires email verification and auto-verify fails, ask the user to verify manually
6. Report the result: which env var was set and where

## Supported services

Run `python3 -m zerostep.cli list` to see all supported services.

Easy services (fully automated): eia, supabase, resend, posthog, brave, firecrawl
Medium services (may need manual CAPTCHA): openai, anthropic

## Adding new services

If the user asks for a service that doesn't have a YAML config:
1. Search for the service's signup URL, API key settings page, and docs
2. Create a new YAML file in `~/zerostep/services/` following the template
3. Test with `--no-headless` to verify selectors work
4. Run the get command

## Environment variables

- `ZEROSTEP_EMAIL` — Default email for signups
- `ZEROSTEP_PASSWORD` — Default password for signups
- `ZEROSTEP_IMAP_HOST` — IMAP server (auto-detected from email domain)
- `ZEROSTEP_IMAP_PASSWORD` — IMAP password (defaults to signup password)
