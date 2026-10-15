# Disposable PostgreSQL migration tests

The PostgreSQL integration suite is opt-in and never reads `DATABASE_URL` as a
fallback. Provision a dedicated, disposable PostgreSQL database manually. Use a
database name with a delimited `test`, `testing`, `disposable`, or `tmp` marker,
for example `ai_interview_studio_test`. Do not point this suite at a production,
staging, or shared customer database.

Set these process environment variables only for the test shell:

```powershell
$env:TEST_POSTGRES_URL = 'postgresql://.../ai_interview_studio_test'
$env:TEST_POSTGRES_CONFIRM_DISPOSABLE = 'YES_I_CREATED_A_DISPOSABLE_TEST_DATABASE'
```

The URL must differ from `DATABASE_URL`. The test suite creates a uniquely
named `aisub_test_<random>` schema inside the explicitly supplied database,
sets each test connection's `search_path` to that schema, and drops only that
owned schema during teardown. It never creates or drops a database. If the test
process is forcibly stopped, inspect the disposable database and manually drop
only the abandoned `aisub_test_<random>` schema created by this suite.

Run the integration suite with:

```powershell
python -m unittest tests.test_subscription_migrations_postgres -v
```

Afterward, remove the process variables and destroy the disposable database
using the database administrator's normal tooling. No cleanup command in this
repository drops the database itself.
