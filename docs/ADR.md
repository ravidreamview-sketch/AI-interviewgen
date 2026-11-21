# Architecture Decision Records (ADR)
## AI Interview Studio — Agentic Platform Transformation

### ADR 001: Modular Core & Router Decoupling
* **Status:** Accepted (Phase 0 / Phase 1)
* **Context:** The monolithic `app/main.py` contained authentication, routing, HTML rendering, database calls, and AI logic in a single file exceeding 1,800 lines. This created high regression risks and prevented clean agentic expansion.
* **Decision:** Extract configuration into `app/core/config.py`, database setup into `app/core/database.py`, security utilities into `app/core/security.py`, and security middlewares into `app/core/middleware.py`. Route all API endpoints through `/api/v1` routers mounted modularly in `app/main.py`.
* **Consequences:** Existing legacy routes remain operational on `/` for backwards compatibility, while all new agentic features and standard APIs are versioned under `/api/v1`.

### ADR 002: PBKDF2 Password Hashing with 600,000 Iterations
* **Status:** Accepted (Phase 1)
* **Context:** NIST SP 800-63B recommends PBKDF2 with HMAC-SHA256 at >= 600,000 iterations for password hashing when Argon2id is not native.
* **Decision:** Implement standard PBKDF2-HMAC-SHA256 with 600,000 iterations and 16-byte random salt in `app/core/security.py`. Provide backwards compatibility with existing legacy hashes using constant-time comparisons.
* **Consequences:** High brute-force resistance with zero third-party C-extensions required.

### ADR 003: 5-Tier Competency Taxonomy & Skill Gap Model
* **Status:** Accepted (Phase 1)
* **Context:** Skills were previously stored as raw unstandardized scores without consistent leveling, evidence categorization, or deterministic gap metrics.
* **Decision:** Adopt a 5-tier taxonomy:
  - Level 1: Beginner (0-39.9)
  - Level 2: Basic (40.0-59.9)
  - Level 3: Intermediate (60.0-74.9)
  - Level 4: Advanced (75.0-89.9)
  - Level 5: Expert (90.0-100.0)
  Evidence is strictly categorized into `SELF_REPORTED`, `ASSESSED`, and `VERIFIED`. Skill gaps are calculated deterministically against curated role competency profiles.
* **Consequences:** Future AI agents (Agents 2–6) receive structured, explainable, and hallucination-free competency data.

