# SECURITY.md

**Project:** FloodPulse
**Status:** Planning document. No authentication, authorization, or security controls are currently implemented beyond `.gitignore` protection.

---

## Current security controls

### Git protection (implemented — P0.2)

- `.env` and `.env.*` are in `.gitignore`.
- Secret file types (`*.pem`, `*.key`, `*.crt`) are in `.gitignore`.
- `secrets/` directory is in `.gitignore`.

### Known security issues

- **Telegram bot token in Trash:** A `TELEGRAM_BOT_TOKEN` was found in deleted `.env` files in the system Trash. The token may still be active. It should be considered potentially compromised. See DECISIONS.md D-009.
- **Database password in Trash:** A database password was found in the same deleted `.env` files. The current Docker container may be using this password.

---

## Planned security controls

### Secrets management

- `.env` files must never be committed to Git.
- Telegram bot tokens must be treated as secrets and stored only in `.env`.
- Database passwords must not be hardcoded in source code.
- API credentials for external data sources must remain outside Git.
- `.env.example` files may be committed as templates — they must contain only variable names, never real values.

### Credential rotation

- The Telegram bot token discovered in Trash must be rotated via BotFather before Telegram integration begins.
- Any secret that has been exposed (even in deleted files or logs) should be considered compromised and rotated.

### Authentication and authorization

- Authentication will be designed before any admin functionality is implemented.
- Token-based authentication is the planned approach (per ARCHITECTURE.md).
- Role-based access control will separate citizen and admin capabilities.
- Exact authentication mechanism (JWT, session, etc.) will be decided during implementation.

### Audit logging

- Important administrative actions (alert configuration, shelter management, user management) will require audit logs.
- Audit logs will record: actor, action, target, timestamp, details.

### API security

- Admin endpoints will require authentication.
- Public endpoints will have rate limiting (to be designed).
- Input validation via Pydantic models.
- CORS configuration will restrict allowed origins.

### Database security

- The application database user should have only the privileges required for application operations.
- Database connections will use environment-variable-based credentials, not hardcoded strings.

### Data handling

- Community reports containing location data are privacy-sensitive.
- No PII should be logged unnecessarily.
- Official government data must be used in accordance with its license/terms.
