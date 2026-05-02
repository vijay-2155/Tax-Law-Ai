# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` branch | ✅ |
| Older releases | ❌ |

## Reporting a Vulnerability

**Please do not file a public GitHub Issue for security vulnerabilities.**

Instead, use [GitHub's private security advisory](https://github.com/vijay-2155/Tax-Law-Ai/security/advisories/new) to report vulnerabilities privately.

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You'll receive a response within 48 hours. We'll coordinate a fix and disclosure timeline with you.

---

## Security Notes

- **Never commit `.env` files** — they contain API keys. `.env` is in `.gitignore`.
- This app connects to external LLM APIs (Ollama Cloud, OpenAI, etc.) — your queries are sent to those providers.
- TaxIQ is not a substitute for professional legal advice.
