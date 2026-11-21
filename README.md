# Agentic AI-Powered Adaptive Learning & Career-Readiness Platform

An enterprise-grade, Google Cloud-targeted platform designed to empower college students, fresh graduates, job seekers, career switchers, and working professionals with continuous, personalized skill acquisition, simulated project mentoring, context-aware tutoring, adaptive mock interviews, and objective competency intelligence.

---

## 🏗️ Architecture Overview

The platform is designed around a decoupled, modular full-stack architecture optimized for Google Cloud Run:

```
+----------------------------------------------------------------------------------------------------+
|                                    CLIENT / PRESENTATION TIER                                      |
|  Responsive, Accessible Web Application (Next.js / TypeScript / Tailwind CSS / Radix UI)           |
|  - Learner Dashboard       - Adaptive Learning Paths    - Interactive AI Tutor Chat & Sandbox      |
|  - Scenario Workspace      - Real-Time Mock Interview   - Competency Intelligence Analytics        |
+----------------------------------------------------------------------------------------------------+
                                                  | HTTPS / REST / SSE Streaming
                                                  v
+----------------------------------------------------------------------------------------------------+
|                       EDGE ROUTING, SECURITY & GOOGLE CLOUD RUN INGRESS                            |
|  [Cloud Armor / Cloud Load Balancing -> Cloud Run Fully Managed Container Instance]               |
|  - Least-Privilege IAM Service Accounts    - HTTPS Enforcement / Strict CORS                       |
|  - Cloud Run Autoscaling (0 to N instances) - Integrated Health Probes (/api/v1/health)            |
+----------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                               FASTAPI ASYNC APPLICATION CORE (ASGI)                                |
|  - Core: Pydantic Settings, Cryptographic JWT, PBKDF2 Hashing, Tracing Middleware                  |
|  - Routers (/api/v1): /health, /auth, /learners, /paths, /tutor, /scenarios, /interviews,           |
|                       /competency, /resumes, /admin                                                |
|  - Multi-Agent Orchestration Layer: Context routing, Pydantic schemas, token budgets               |
+----------------------------------------------------------------------------------------------------+
                               |                                              |
                               v                                              v
+------------------------------------------+    +----------------------------------------------------+
|          PERSISTENCE & STORAGE           |    |             GOOGLE AI / VERTEX AI TIER             |
|  1. Cloud SQL for PostgreSQL (Alembic)   |    |  1. Google Gemini 2.5 Flash (Generative Language)  |
|  2. Google Cloud Storage (Private)       |    |  2. Google Cloud Secret Manager (Credentials)      |
|  3. Cloud Logging & Cloud Monitoring     |    |  3. Deterministic Scorer (match-v1.1.0)            |
+------------------------------------------+    +----------------------------------------------------+
```

---

## 🚀 Quick Start Guide

### Prerequisites
* Python 3.12+ (or Python 3.14 on Windows)
* Node.js v18+ and npm
* Git

### 1. Environment Configuration
Copy `.env.example` to `.env` and configure local variables:
```bash
cp .env.example .env
```
Key configuration items:
* `ENV`: `development` (or `production` for Cloud Run)
* `DATABASE_URL`: Leave blank for local SQLite (`./interview.db`) or set PostgreSQL DSN
* `ADMIN_JWT_SECRET`: Random 32+ character string (mandatory in production)
* `GEMINI_API_KEY`: Google Gemini API key from Google AI Studio

### 2. Backend Execution
From the `AI-interviewgen/` directory:
```bash
# Run FastAPI server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
API endpoints will be live at:
* OpenAPI Swagger UI: `http://127.0.0.1:8000/docs`
* API v1 Health Probe: `http://127.0.0.1:8000/api/v1/health`
* API v1 Readiness Probe: `http://127.0.0.1:8000/api/v1/readiness`

### 3. Frontend Execution
From the `AI-interviewgen/frontend/` directory:
```bash
npm install
npm run dev
```
Open `http://localhost:3000` to access the modernized Next.js dashboard shell.

---

## 🧪 Testing & Validation

Execute the automated test suite:
```bash
python -m unittest tests/test_phase1_foundation.py
```
To run targeted algorithmic regression tests:
```bash
python -m unittest tests/test_ai_provider_config.py tests/test_subscores_import.py
```

---

## 🚀 Deployment to Google Cloud Run

To deploy RaviGen AI Interview Studio to Google Cloud Run in the `asia-south1` region:

```bash
gcloud run deploy idea-interview-studio \
  --source . \
  --region asia-south1 \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --cpu-boost \
  --allow-unauthenticated \
  --startup-probe=httpGet.path=/health
```

### Deployment Configuration Guidelines
- **Port:** The container listens on `0.0.0.0` and reads the `$PORT` environment variable assigned by Cloud Run (default: `8080`). Do **not** set `PORT` in `--set-env-vars` as Cloud Run sets and manages this variable automatically.
- **Region:** Deployments are standardized on `asia-south1`.
- **Health Probes:** Cloud Run startup and liveness probes target `--startup-probe=httpGet.path=/health`.
- **Secrets Management:** Sensitive keys and secrets (`DATABASE_URL`, `ADMIN_JWT_SECRET`, `GEMINI_API_KEY`, `GROQ_API_KEY`) must always be configured through Google Secret Manager using `--set-secrets`, never committed to source or hardcoded.

---

## 🔒 Security & Governance

1. **Production Guardrails:** `app/core/config.py` enforces that in production (`ENV=production`), `ADMIN_JWT_SECRET` must be set and >= 32 characters. Fallback salts are strictly rejected.
2. **SSRF Defense:** `app/jd_service.py` protects all outbound job description URL fetching by verifying DNS IP spaces against loopback, private RFC-1918, cloud metadata (`169.254.169.254`, `metadata.google.internal`), and carrier-grade NAT.
3. **Multi-Tenant Scoping:** All candidate database queries filter strictly by authenticated user ID (`user_id == current_user.id`).
4. **Agent Permissions:** AI agents have zero direct access to filesystem, cloud deployment, or database DDL operations. Refer to `docs/AGENT_PERMISSIONS.md`.
5. **Architecture Decision Records:** Full architectural choices and trade-offs are documented in `docs/ADR.md`.

---

## 📋 Development Phases Roadmap

* [x] **Phase 0:** Architecture, Google Cloud Strategy & System Planning (**PASS**)
* [x] **Phase 1:** Application Foundation & Modular Refactoring (**PASS**)
* [ ] **Phase 2:** Learner Intelligence & Competency Framework (Agent 1)
* [ ] **Phase 3:** Adaptive Learning Path Engine (Agent 2)
* [ ] **Phase 4:** Context-Aware AI Tutor & Coding Mentor (Agent 3)
* [ ] **Phase 5:** Real-World Scenario Generation Workspace (Agent 4)
* [ ] **Phase 6:** Adaptive Mock Interview & Project Mentor (Agent 5)
* [ ] **Phase 7:** Competency Intelligence Analytics & Readiness Dashboard (Agent 6)
* [ ] **Phase 8:** Agent Orchestration, Shared State & Telemetry Monitoring
* [ ] **Phase 9:** Google Cloud Deployment Preparation & CI/CD Pipelines
* [ ] **Phase 10:** Staging Deployment & Multi-Tier Validation
* [ ] **Phase 11:** Production Readiness, Security Review & Launch
