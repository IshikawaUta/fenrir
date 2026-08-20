# Security Policy

Fenrir takes the security of the framework and the applications built on top
of it seriously. Thank you for helping keep the project and its users safe.

## Supported Versions

We provide security fixes for the latest stable release and the previous
minor release:

| Version | Supported          |
| ------- | ------------------ |
| 4.2.x   | :white_check_mark: |
| 4.1.x   | :white_check_mark: (security fixes only) |
| < 4.1   | :x:                |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, report them privately using one of these channels:

- **GitHub private vulnerability reporting** (preferred):
  <https://github.com/IshikawaUta/fenrir/security/advisories/new>
- **Email**: open a private advisory above, or reach the maintainers through
  the repository's GitHub contact settings.

Please include as much of the following as possible:

- The affected version(s) and Python version.
- A minimal, self-contained reproduction (code or steps to trigger the issue).
- A description of the impact and any exploit scenario you identified.
- Suggested fix, if you have one.

You will receive an acknowledgment within **72 hours**. We aim to provide a
first assessment within **5 business days** and will keep you informed of
progress toward a fix and disclosure.

## Disclosure Policy

We follow a coordinated disclosure process:

1. The report is triaged and validated.
2. A fix is prepared and released in the latest supported version.
3. The vulnerability is disclosed publicly after a reasonable grace period to
   allow users to upgrade — typically within 30 days of the fix being
   available, or sooner if the issue is already public.

We ask reporters to wait for our public disclosure before sharing details
publicly.

## Security Posture

Fenrir bakes security features in rather than bolting them on:

- **CSRF protection** via `CSRFMiddleware` (constant-time token comparison,
  signed tokens, cookie-overwrite prevention).
- **Rate limiting** (`RateLimitMiddleware`) per IP/user, with optional Redis
  backend for distributed deployments.
- **Body size limits** (`BodyLimitMiddleware`) to mitigate DoS via oversized
  request bodies.
- **Password hashing** with **bcrypt** for the monitoring dashboard and any
  application auth.
- **WebSocket authentication** (`WebSocketTokenAuth`) via headers or query
  parameters.
- **SQL injection prevention** in the built-in ORM (parameterized queries and
  sanitized table/column names).
- **Secure session cookies** (`SESSION_COOKIE_SECURE`), plus HTTP auth
  schemes (Basic, Bearer, Digest, OAuth2, OpenID Connect).

If you find a flaw in any of these — or anything else — please report it
through the channels above rather than opening an issue.