# ZeroStep

**4 steps → 0.** AI agent that signs up for services and gets your API keys automatically.

Every developer hits this: you need an API key, so you find the signup page, create an account, verify your email, navigate to settings, generate a key, copy it, paste it into `.env`. ZeroStep does all of that in one command.

```bash
zerostep get eia --email you@example.com --password MyP@ss123
# → Signs up, verifies email, extracts API key, writes to .env
# → EIA_API_KEY=abc123... written to /path/to/.env
```

## How it works

1. **You run one command** with the service name and your email
2. **Browser automation** (Playwright) navigates the signup flow
3. **IMAP reader** checks your inbox for verification emails
4. **Key extractor** finds the API key on the settings page
5. **Writes to `.env`** — ready to use immediately

Each service has a YAML config defining its signup flow, selectors, and key patterns. Adding a new service is as simple as creating a new YAML file.

## Install

```bash
pip install zerostep
playwright install chromium
```

## Quick start

```bash
# Set defaults (optional)
export ZEROSTEP_EMAIL="you@example.com"
export ZEROSTEP_PASSWORD="YourSecurePassword123!"

# Get an API key (email+password signup)
zerostep get eia
zerostep get supabase
zerostep get resend
zerostep get brave

# Sign up with GitHub (faster, skips email verification)
zerostep get supabase --method=github --github-email=you@github.com --github-password=ghpass

# Sign up with Google
zerostep get posthog --method=google --google-email=you@gmail.com --google-password=gpass

# List supported services
zerostep list

# Show service details (including supported signup methods)
zerostep info posthog

# Watch the browser (useful for debugging or CAPTCHAs)
zerostep get openai --no-headless
```

## Supported services

| Service | Env var | Difficulty | Google | GitHub | Free tier |
|---------|---------|------------|--------|--------|-----------|
| EIA | `EIA_API_KEY` | Easy | | | Unlimited (government) |
| Supabase | `SUPABASE_KEY` | Easy | Y | Y | 2 projects, 500MB |
| Resend | `RESEND_API_KEY` | Easy | | Y | 100 emails/day |
| PostHog | `POSTHOG_API_KEY` | Easy | Y | Y | 1M events/month |
| Brave Search | `BRAVE_API_KEY` | Easy | | | 2,000 queries/month |
| Firecrawl | `FIRECRAWL_API_KEY` | Easy | Y | Y | 500 credits |
| OpenAI | `OPENAI_API_KEY` | Medium | | | $5 credits (has CAPTCHA) |
| Anthropic | `ANTHROPIC_API_KEY` | Medium | | | $5 credits (phone verify) |

**Signup methods:**
- **email** (default) — Creates a new account with email + password
- **google** — Signs up via Google OAuth (skips email verification)
- **github** — Signs up via GitHub OAuth (skips email verification)

**Difficulty levels:**
- **Easy** — Email + password signup, no CAPTCHA, no phone
- **Medium** — Has CAPTCHA or phone verification (use `--no-headless` to solve manually)
- **Hard** — Requires credit card or complex OAuth flows

## OAuth signup (Google/GitHub)

Many dev tools let you sign up with Google or GitHub — faster and skips email verification entirely.

```bash
# Set OAuth credentials (optional — defaults to ZEROSTEP_EMAIL/PASSWORD)
export ZEROSTEP_GOOGLE_EMAIL="you@gmail.com"
export ZEROSTEP_GOOGLE_PASSWORD="your-google-password"
export ZEROSTEP_GITHUB_EMAIL="you@github.com"
export ZEROSTEP_GITHUB_PASSWORD="your-github-password"

# Use OAuth
zerostep get supabase --method=github
zerostep get posthog --method=google
```

**Note:** Google may block automated login if you have 2FA enabled. Use `--no-headless` to complete the login manually in that case.

## Email verification

ZeroStep auto-detects your IMAP server from your email domain. For Gmail, use an [App Password](https://myaccount.google.com/apppasswords):

```bash
export ZEROSTEP_IMAP_HOST=imap.gmail.com
export ZEROSTEP_IMAP_PASSWORD=your-app-password
```

## Adding a new service

Create a YAML file in `services/`:

```yaml
name: myservice
display_name: My Service
signup_url: https://myservice.com/signup
api_key_url: https://myservice.com/settings/api
env_var: MYSERVICE_API_KEY
category: general
difficulty: easy
free_tier: "1000 requests/month"

has_email_verification: true
has_captcha: false
has_phone_verification: false
requires_credit_card: false

signup_email_selector: 'input[type="email"]'
signup_password_selector: 'input[type="password"]'
signup_submit_selector: 'button[type="submit"]'

api_key_selector: 'code, input[readonly]'
api_key_pattern: 'ms_[a-zA-Z0-9]{20,}'
```

PRs adding new services are welcome.

## As a Claude Code skill

Copy the `skill/` directory to `~/.claude/skills/zerostep/` and use `/get-api eia` from Claude Code.

## Security

- Passwords are never logged or stored (only used in the browser session)
- API keys are written only to your local `.env` file
- Browser sessions are ephemeral (closed after each run)
- IMAP connections use SSL
- No data is sent to any third party

## License

MIT
