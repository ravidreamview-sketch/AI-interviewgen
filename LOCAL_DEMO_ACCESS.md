# Temporary local demo access

`LOCAL_DEMO_ACCESS` is an opt-in, temporary development setting. It is off by default. When enabled, signed-in active candidate accounts can use candidate features without an approved subscription. The subscription service and payment records are unchanged; no subscription, verification, or audit rows are created by this setting.

The policy only activates when all of these are true:

- `ENV` is `local`, `development`, `dev`, or `test`.
- `LOCAL_DEMO_ACCESS` is `true` (also accepts `1` or `yes`).
- The configured application engine uses SQLite.
- No supported hosted-runtime marker is present, and `DEV_AUTH_BYPASS` is not enabled.
- Both the request client and host must be loopback (`localhost` or `127.0.0.1`), including in test mode.

To run the local app from the project root in PowerShell:

```powershell
$env:ENV = 'local'
$env:DATABASE_URL = 'sqlite:///./interview.db'
$env:LOCAL_DEMO_ACCESS = 'true'
$env:DEV_AUTH_BYPASS = 'false'
$env:VERCEL = ''
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Sign in through the normal candidate login page. In a fresh local SQLite database, the existing local seed provides `candidate@example.com` with password `CandidatePass123!`; an existing account with different credentials is preserved by the seed and must use its own password.

To restore normal subscription checks, stop the server and restart it with `LOCAL_DEMO_ACCESS` set to `false` or unset. Restarting is required because the database engine is selected during application startup. Do not set this flag on a hosted or production deployment; hosted-runtime and non-SQLite checks fail closed even if it is set.
