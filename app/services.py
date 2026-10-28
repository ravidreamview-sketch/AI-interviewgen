import os
import re
import logging
from pathlib import Path
from typing import List, Optional
from datetime import timezone

# Difficulty to temperature mapping (single source of truth)
DIFFICULTY_TEMPERATURE = {
    "Beginner": 0.3,
    "Intermediate": 0.5,
    "Advanced": 0.6,
}

def get_temperature(difficulty: str) -> float:
    """Return temperature based on difficulty, normalizing input.
    Falls back to Intermediate (0.5) for missing/invalid values.
    """
    # Reuse existing normalize_difficulty from prompts to keep logic consistent
    try:
        from .prompts import normalize_difficulty
    except Exception:
        # Fallback if import fails – simple lower‑case normalization
        def normalize_difficulty(val: str) -> str:
            v = (val or "").strip().lower()
            if v in {"beginner", "entry", "junior", "low"}:
                return "Beginner"
            if v in {"intermediate", "medium", "mid", "average"}:
                return "Intermediate"
            if v in {"advanced", "senior", "expert", "high"}:
                return "Advanced"
            return "Intermediate"
    norm = normalize_difficulty(difficulty)
    return DIFFICULTY_TEMPERATURE.get(norm, DIFFICULTY_TEMPERATURE["Intermediate"])

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")


import json
import urllib.request

logger = logging.getLogger("ravi.ai_provider")


def get_ai_provider_status() -> tuple[str, bool]:
    """Return the preferred configured provider without exposing its key."""
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "Gemini", True
    if os.getenv("GROQ_API_KEY", "").strip():
        return "Groq", True
    return "Not configured", False


def generate_ai_questions(prompt: str, temperature: Optional[float] = None) -> str:
    # Gemini is preferred; Groq remains the configured fallback.
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
            temp = temperature if temperature is not None else 0.65
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temp, "maxOutputTokens": 3000}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text:
                    return text
            logger.warning("Gemini provider returned an empty response; trying Groq if configured")
        except Exception as gemini_err:
            logger.warning(
                "Gemini provider request failed (%s); trying Groq if configured",
                type(gemini_err).__name__,
            )

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            models_to_try = [
                "openai/gpt-oss-120b",
                "qwen/qwen3.8-27b",
            ]
            for model_name in models_to_try:
                try:
                    temp_groq = temperature if temperature is not None else 0.6
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temp_groq,
                        max_tokens=3000,
                    )
                    text = response.choices[0].message.content
                    if text and text.strip():
                        return text
                    logger.warning("Groq model %s returned an empty response", model_name)
                except Exception as groq_err:
                    logger.warning(
                        "Groq model %s request failed (%s)",
                        model_name,
                        type(groq_err).__name__,
                    )
        except Exception as groq_err:
            logger.warning("Groq provider is unavailable (%s)", type(groq_err).__name__)

    if not gemini_key and not groq_key:
        logger.error(
            "AI provider is not configured. "
            "Set GEMINI_API_KEY or GROQ_API_KEY in the server environment."
        )
        raise RuntimeError(
            "AI provider is not configured. "
            "Set GEMINI_API_KEY or GROQ_API_KEY in the server environment."
        )
    raise RuntimeError(
        "Configured AI provider request failed. "
        "Check the server-side provider configuration and try again."
    )


# Rich fallback questions bank (25+ questions per discipline)
PYTHON_ROLE_BANKS = {
    "ux": [
        "How do you design and execute a mixed-methods user research plan for an ambiguous feature definition?",
        "Walk through how you construct a task-based usability testing protocol and analyze the System Usability Scale (SUS) results.",
        "How do you organize information architecture and mental models for an enterprise application with dense navigation hierarchy?",
        "Describe your approach to wireframing and low-fidelity prototyping to align cross-functional teams early.",
        "How do you ensure interaction design patterns meet WCAG 2.2 AA accessibility standards for keyboard and screen-reader navigation?",
        "Scenario: User drop-off spikes at step 2 of a multi-step onboarding wizard. How do you diagnose whether the issue is cognitive load, usability friction, or value communication?",
        "How do you handle a situation where a Product Manager pushes for a dark pattern to temporarily boost conversion numbers?",
        "Explain how you synthesize generative research findings into actionable personas and journey maps without introducing confirmation bias.",
        "What quantitative metrics (SEQ, time-on-task, error rate) do you pair with qualitative observations during unmoderated user tests?",
        "How do you design an intuitive search and filter experience for a dataset with over 50 multi-faceted dimensions?",
        "Describe how you conduct tree testing and closed card sorting to validate a restructured taxonomy.",
        "How do you balance aesthetic delight and micro-interactions with cognitive accessibility and task velocity?",
        "Walk through your strategy for conducting accessibility audits across legacy web interfaces.",
        "How do you facilitate co-design design thinking workshops with non-designer engineering and business stakeholders?",
        "Scenario: Usability testing reveals users misunderstand a critical action button label. How do you rapidly test copy and icon variations?",
        "How do you define UX guardrail metrics when product teams run high-velocity multivariate experiments?",
        "Describe how you structure user interview discussion guides to avoid leading questions and uncover latent user needs.",
        "How do you manage design handoff and annotate Figma files with edge cases, error states, and responsive breakpoints?",
        "What is your approach to designing error recovery and empty states that guide users toward constructive resolution?",
        "How do you evaluate user feedback from in-app CSAT/NPS micro-surveys alongside session replay analytics?",
        "Scenario: A critical client requires an immediate custom workflow that compromises the core navigation UX. How do you navigate this trade-off?",
        "How do you prototype high-fidelity motion and micro-interactions in Figma or ProtoPie to validate user feedback loops?",
        "Explain how you create design tokens in Figma Variables to support dynamic theming and WCAG contrast compliance.",
        "How do you measure the long-term ROI and business impact of UX research on product adoption and churn reduction?",
        "What strategies do you use to continuously test and iterate on design system components based on real user behavior?"
    ],
    "product": [
        "How do you frame a product problem statement to balance business viability (e.g. ARR, retention) with core user needs?",
        "Walk through a product feature you designed: what North Star metric and secondary guardrail metrics did you track?",
        "How do you navigate discovery vs delivery when working in fast two-week agile sprint cycles with engineering?",
        "Describe a scenario where A/B test data showed positive revenue metrics but qualitative customer feedback was negative. What did you do?",
        "How do you determine when a design system component should be added to the core library vs remaining feature-specific?",
        "Scenario: You are designing a zero-to-one product in a competitive space. How do you identify the minimum lovable product (MLP) scope?",
        "How do you prioritize competing feature requests from high-value enterprise sales leads against core consumer user experience?",
        "Explain how you design monetization and paywall trigger moments without degrading user engagement and product trust.",
        "What frameworks (e.g., RICE, Kano Model, ICE) do you apply to evaluate product design trade-offs and roadmap initiatives?",
        "How do you partner with Product Managers and Data Scientists to define funnel conversion milestones and event instrumentation?",
        "Walk through your approach to sunsetting a legacy product feature that has passionate but low-volume user adoption.",
        "How do you align multi-disciplinary squads across mobile, desktop web, and email notification touchpoints?",
        "Describe a time you used cohort retention curves to identify where new users experience their initial 'aha!' value moment.",
        "How do you design self-service onboarding flows that maximize Day-1 product activation and minimize time-to-value (TTV)?",
        "Scenario: Product leadership wants to launch an AI feature quickly. How do you ensure it solves real customer pain rather than being a gimmick?",
        "How do you evaluate whether to build custom bespoke components or adopt standard off-the-shelf design patterns for speed to market?",
        "Walk through how you defend controversial design decisions using qualitative insights and quantitative benchmark metrics.",
        "How do you run rapid customer advisory board (CAB) sessions to de-risk high-stakes strategic roadmap bets?",
        "Describe how you architect omni-channel user experiences connecting web apps, mobile apps, and physical operational workflows.",
        "How do you build business cases for investing engineering sprint capacity into foundational design debt refactoring?",
        "Scenario: Key user engagement drops 15% after a major redesign rollout. Walk through your step-by-step diagnostic and remediation plan.",
        "How do you ensure enterprise administrative permission models and role-based access control (RBAC) remain easy to configure?",
        "What methods do you use to map out end-to-end customer service blueprints across support, sales, and automated product systems?",
        "How do you balance immediate conversion rate optimization (CRO) quick-wins with long-term brand equity and UX integrity?",
        "Describe your methodology for conducting post-launch product retrospectives and feeding user telemetry back into the roadmap."
    ],
    "uiux": [
        "How do you establish typographic scale, 8pt/4pt spatial rhythm, and contrast ratios across multi-density screens?",
        "Explain how you architect multi-brand design tokens (Global -> Semantic -> Component) in Figma Variables.",
        "How do you design state machines for complex interactive UI components (hover, focus-visible, active, error, loading, skeleton)?",
        "Walk through your approach to micro-interactions and motion design to provide clear user feedback without causing distraction.",
        "Scenario: An existing design system has 40+ inconsistent button variants. How do you audit, consolidate, and roll out a refactored component set?",
        "How do you ensure visual accessibility for color-blind users across complex statistical charts and status badges?",
        "Describe how you build responsive auto-layout components in Figma that fluidly resize across 320px mobile to 2560px ultra-wide screens.",
        "What is your strategy for implementing dark mode theming with semantic color tokens while preserving hierarchy and depth?",
        "How do you prototype realistic user input validation states and multi-field inline error messages in Figma?",
        "Walk through how you organize component libraries in Figma using variants, nested instances, and boolean property toggles.",
        "How do you collaborate with frontend engineers to ensure CSS custom properties match Figma token definitions precisely?",
        "Describe how you design accessible keyboard navigation focus indicators that blend with brand aesthetics.",
        "How do you maintain visual harmony when incorporating dense data tables, graphs, and action toolbars on a single dashboard viewport?",
        "Scenario: Marketing requires large hero imagery, but engineering reports severe performance impacts on mobile. How do you solve this visually?",
        "How do you create unified iconography guidelines (stroke weight, corner radius, optical volume) for a product suite?",
        "Explain your approach to designing toast notifications, banners, and modal dialogs with strict visual z-index hierarchies.",
        "How do you test UI components across high-contrast mode, browser font-size zoom (up to 200%), and RTL language scripts?",
        "Describe how you design skeletal loading states that match actual layout geometries to reduce perceived latency.",
        "What methods do you use to audit UI components for WCAG 2.2 target size requirements (minimum 24x24px / 44x44px)?",
        "How do you design fluid bottom sheets, drawer navigation, and gesture-driven interactions for modern mobile apps?",
        "Scenario: A critical user workflow requires dense multi-step configuration. How do you design progressive disclosure without visual clutter?",
        "How do you document component usage guidelines and 'Do / Don't' visual specifications in Storybook or Zeroheight?",
        "Describe your approach to designing micro-copy and typographic emphasis within tight interface constraints.",
        "How do you handle visual degradation and responsive fallbacks for users on low-resolution or legacy display hardware?",
        "What is your process for creating interactive prototypes to pitch high-concept visual UI innovations to executive leadership?"
    ],
    "frontend": [
        "Explain how the React 19 concurrent renderer and Server Components (RSC) change data fetching and hydration performance.",
        "How do you profile, identify, and eliminate memory leaks and unnecessary re-renders in a complex component tree?",
        "Compare client-side state architectures (Zustand/Redux) vs server cache state (TanStack Query/SWR) in high-frequency apps.",
        "Describe how you build a custom accessible dropdown component compliant with WAI-ARIA authoring practices from scratch.",
        "Scenario: A live trading dashboard receives 100 WebSocket price updates per second. How do you prevent UI freezing and DOM thrashing?",
        "How do you optimize Core Web Vitals (LCP, INP, CLS) in Next.js applications using script prioritization and image optimization?",
        "Explain how the JavaScript Event Loop coordinates the microtask queue (Promises), macrotask queue (setTimeout), and animation frames (rAF).",
        "How do you implement code splitting, dynamic imports, and route-level bundle chunking to keep initial JS bundles under 100KB?",
        "Describe your strategy for optimistic UI mutations, rollback on error, and background cache synchronization in TanStack Query.",
        "How do you architect end-to-end type safety between backend OpenAPI/tRPC schemas and frontend TypeScript models?",
        "Walk through how you create virtualized lists (e.g. react-virtual/tanstack-virtual) to render 50,000+ items smoothly at 60 FPS.",
        "How do you handle offline sync, service worker caching, and IndexedDB persistence in Progressive Web Apps (PWAs)?",
        "Scenario: A third-party analytics script is causing severe Interaction to Next Paint (INP) degradation. How do you isolate and fix it?",
        "Compare CSS Modules, Tailwind CSS, and CSS-in-JS (e.g. styled-components) regarding runtime overhead and build-time zero-runtime extraction.",
        "How do you design robust frontend error boundaries with fallback UI, telemetry logging (Sentry), and retry mechanisms?",
        "Explain how you use Web Workers to offload heavy computational algorithms (e.g. large JSON parsing or image filtering) from the main thread.",
        "How do you build responsive, high-performance canvas/SVG data visualizer components using D3 or PixiJS in React?",
        "Describe how you implement secure JWT token storage (httpOnly cookies vs memory) and handle silent token refresh cycles.",
        "What is your approach to testing frontend applications across Unit (Vitest/Jest), Integration (React Testing Library), and E2E (Playwright)?",
        "Scenario: Layout shifts occur when custom web fonts and hero banners load asynchronously. How do you eliminate CLS completely?",
        "How do you implement internationalization (i18n), right-to-left (RTL) layout switching, and localized number/date formatting cleanly?",
        "Explain how modern browser rendering engines handle reflow, repaint, and GPU compositing layers.",
        "How do you structure shared Monorepo architectures (Turborepo/Nx) with reusable UI component packages across multiple web apps?",
        "Describe how you enforce strict accessibility linting (eslint-plugin-jsx-a11y) and automated axe-core audits in CI/CD pipelines.",
        "How do you architect real-time collaborative document editing using CRDTs (Yjs/Automerge) and WebSockets?"
    ],
    "backend": [
        "How do you structure database indexes (B-Tree, GIN, composite) in PostgreSQL and interpret EXPLAIN ANALYZE output?",
        "Explain concurrency control mechanisms: compare optimistic locking vs pessimistic locking with concrete SQL examples.",
        "How do you design distributed caching with Redis (Cache-Aside, Write-Through) and prevent cache stampedes (dogpiling)?",
        "Describe how you implement token bucket or leaky bucket rate limiting across distributed API gateway instances.",
        "Scenario: A distributed payment endpoint experiences intermittent database timeouts under heavy load. How do you implement circuit breakers and dead-letter queue retry mechanisms?",
        "Compare RESTful APIs, GraphQL, and gRPC with Protobuf regarding schema evolution, latency overhead, and client flexibility.",
        "How do you design idempotent API endpoints using unique idempotency keys, Redis locks, and atomic database commits?",
        "Explain database transaction isolation levels (Read Committed, Repeatable Read, Serializable) and the anomalies they prevent.",
        "How do you architect event-driven microservices using Apache Kafka or RabbitMQ, ensuring at-least-once or exactly-once message delivery?",
        "Describe how you implement secure OAuth2 + OpenID Connect authentication with JWT signing (RS256) and token revocation lists.",
        "How do you manage database connection pooling (HikariCP, PgBouncer) and prevent pool starvation during traffic spikes?",
        "Scenario: A monolithic PostgreSQL database table has reached 500 million rows. How do you plan and execute zero-downtime partitioning/sharding?",
        "How do you structure asynchronous background task workers using Celery/BullMQ with exponential backoff and dead-letter queues?",
        "Explain how you design structured logging, distributed tracing (OpenTelemetry/Jaeger), and metrics (Prometheus) across microservices.",
        "How do you guard backend APIs against SQL injection, SSRF, broken object-level authorization (BOLA), and ReDoS attacks?",
        "Walk through your strategy for zero-downtime database schema migrations with zero locks on live production tables.",
        "How do you implement database read-replicas with replication lag monitoring and read-after-write consistency guarantees?",
        "Scenario: Microservices communication experiences cascading network failures during an AWS AZ outage. How do you build resilience?",
        "How do you architect secure multi-tenant data isolation (Row-Level Security vs schema-per-tenant vs database-per-tenant)?",
        "Explain how modern asynchronous runtimes (Python asyncio, Node.js libuv, Go goroutines) handle 50,000+ concurrent network sockets.",
        "How do you design distributed locks in Redis using Redlock and ensure safety during unexpected process pauses or clock drift?",
        "Describe how you implement webhook delivery systems with HMAC-SHA256 signature verification and retry backoff policies.",
        "How do you optimize slow SQL queries with heavy JOINs and aggregations using materialized views and covering indexes?",
        "Scenario: A memory leak in a backend microservice causes OOM crashes every 6 hours. Walk through how you profile heap dumps and resolve it.",
        "How do you architect high-volume data ingestion pipelines using CDC (Change Data Capture) with Debezium and Kafka Connect?"
    ],
    "genai": [
        "Compare chunking strategies (semantic chunking, parent-document retrieval, sentence windowing) for dense domain-specific documents.",
        "How do you implement hybrid search combining dense vector embeddings with sparse BM25 keyword search using reciprocal rank fusion (RRF)?",
        "Describe how you build a multi-step agentic workflow with LangGraph/AutoGen that executes deterministic tool calls safely.",
        "How do you quantitatively benchmark and monitor hallucination rates in production using Ragas or LLM-as-a-judge frameworks?",
        "Scenario: Your production LLM service suffers high TTFT (Time to First Token) and token cost. How do you optimize latency and throughput using semantic caching and model quantization?",
        "Explain how Multi-Head Attention, RoPE (Rotary Position Embedding), and KV-caching operate inside transformer decoder architectures.",
        "How do you design vector database index configurations (HNSW parameters M and efConstruction vs IVFFlat) for sub-20ms search latency?",
        "Describe your methodology for fine-tuning open-weights models (e.g. LLaMA-3) using QLoRA, LoRA ranks, and target modules.",
        "How do you implement multi-tenant RAG security to guarantee strict document-level Access Control Lists (ACLs) during vector retrieval?",
        "Compare ReAct (Reason + Act), Plan-and-Solve, and Reflexion agentic frameworks regarding reliability and token consumption.",
        "How do you design guardrails (NeMo Guardrails, Llama-Guard) to prevent prompt injections, jailbreaks, and sensitive PII exfiltration?",
        "Scenario: Retrieval returns 20 relevant chunks but LLM context degradation causes 'lost in the middle' syndrome. How do you solve this with rerankers (Cohere/BGE)?",
        "How do you implement streaming token output via Server-Sent Events (SSE) while preserving structured JSON schema validation?",
        "Explain how speculative decoding and vLLM PagedAttention optimize GPU throughput and vRAM memory bandwidth.",
        "How do you architect synthetic data generation pipelines with strict diversity filtering to train specialized domain models?",
        "Describe how you benchmark embeddings models (MTEB leaderboard) for specialized legal, medical, or multilingual enterprise corpora.",
        "How do you build self-correcting agent loops that validate SQL/code output against schemas and retry with error feedback?",
        "Scenario: An agent gets caught in an infinite tool-calling loop or exhibits oscillatory tool behavior. How do you detect and safely terminate it?",
        "How do you implement dynamic few-shot prompt exemplar selection using semantic similarity vector search?",
        "Explain how Direct Preference Optimization (DPO) and RLHF align model responses with human feedback and domain safety guidelines.",
        "How do you design observability tracing (Langfuse, Arize Phoenix, OpenInference) across multi-step LLM chains and tool calls?",
        "What strategies do you use for cost-performance routing between frontier models (GPT-4o, Claude 3.5 Sonnet) and fast SLMs (Llama-3-8B)?",
        "How do you handle contextual document updates, deletions, and real-time vector re-indexing in production RAG systems?",
        "Describe your approach to evaluating agentic reasoning trajectories when there is no single deterministic ground truth answer.",
        "Scenario: Multi-modal LLM applications process complex scanned PDFs with mixed tables and charts. How do you structure the OCR and vision ingestion pipeline?"
    ]
}


def generate_seed_derived_questions(seed_q: str, role: str, count: int) -> List[str]:
    """Generates deep-probing, role-specific questions branching from a user seed."""
    clean_seed = re.sub(r"[?.\s]+$", "", seed_q).strip()
    r = (role or "").lower()

    if "ux" in r and "product" not in r and "ui/ux" not in r:
        pool = [
            f'Regarding "{clean_seed}" — What user research methodology (moderated interviews vs unmoderated usability testing) would you use to define baseline user needs?',
            f'In Figma, how would you architect wireframes, user flow diagrams, and Auto Layout interactive components to prototype: "{clean_seed}"?',
            f'What usability friction points, accessibility (WCAG 2.2 AA) edge cases, and cognitive load hurdles must be solved in: "{clean_seed}"?',
            f'How would you design a usability testing protocol (tasks, completion metrics like SUS/time-on-task) to validate your prototype for: "{clean_seed}"?',
            f'How do you defend your UX decisions for "{clean_seed}" when engineering or product managers raise technical constraints or timeline trade-offs?',
            f'Scenario: User testing on "{clean_seed}" shows a 40% task abandonment rate at step 2. Walk through how you diagnose and iterate on the mental model.',
            f'How do you establish design system tokens, component variants, and interactive states in Figma to standardize: "{clean_seed}"?',
            f'Describe how you would map the end-to-end customer journey and identify emotional touchpoints for: "{clean_seed}".',
            f'How do you ensure "{clean_seed}" remains accessible for screen-reader users, keyboard navigators, and high-contrast display modes?',
            f'What qualitative insights and quantitative benchmark metrics would you present to executive stakeholders to justify launching: "{clean_seed}"?',
            f'How do you conduct tree testing and card sorting to structure navigation hierarchy and information architecture for: "{clean_seed}"?',
            f'Describe how you prepare developer handoff specs, annotations, and motion prototypes for: "{clean_seed}".',
            f'How do you incorporate continuous user feedback loops (micro-surveys, session replays) post-launch for: "{clean_seed}"?',
            f'Scenario: Stakeholders demand adding 3 new promotional widgets into "{clean_seed}". How do you prevent visual clutter and protect the core user task?',
            f'How do you test and iterate on the micro-copy, button labels, and empty states of "{clean_seed}" to maximize task clarity?'
        ]
    elif "product" in r:
        pool = [
            f'Regarding "{clean_seed}" — How do you define the product hypothesis and balance core business metrics (conversion/retention) with user friction?',
            f'How do you conduct rapid user discovery for "{clean_seed}" while keeping engineering delivery on track during sprint cycles?',
            f'What North Star metric and secondary guardrail metrics would you track post-launch for: "{clean_seed}"?',
            f'Describe how you facilitate a cross-functional alignment workshop with PM and Engineering leads to scope the MVP for: "{clean_seed}".',
            f'Scenario: 30 days after launching "{clean_seed}", user adoption is high but customer support tickets increased by 25%. How do you diagnose and iterate?',
            f'How do you prioritize feature trade-offs and roadmap sequencing when building: "{clean_seed}"?',
            f'What frameworks (RICE, Kano) would you apply to evaluate feature enhancements for: "{clean_seed}"?',
            f'Describe how you design monetization or upgrade triggers within "{clean_seed}" without alienating active users.',
            f'How do you align multi-platform user experiences across web, mobile, and automated communications for: "{clean_seed}"?',
            f'Scenario: An A/B test on "{clean_seed}" shows statistically significant revenue growth but a 5% drop in CSAT. What decision do you make?',
            f'How do you define user onboarding milestones and time-to-value (TTV) metrics for: "{clean_seed}"?',
            f'Walk through your strategy for sunsetting competing legacy workflows when introducing: "{clean_seed}".',
            f'How do you run customer advisory sessions to de-risk high-stakes design decisions in: "{clean_seed}"?',
            f'Describe how you instrument telemetry funnels and event tracking with data engineers for: "{clean_seed}".',
            f'What is your retrospective process for evaluating whether "{clean_seed}" achieved its quarterly business objectives?'
        ]
    elif "ui/ux" in r or "ui designer" in r or "visual" in r:
        pool = [
            f'Regarding "{clean_seed}" — How do you establish typographic hierarchy, 8pt/4pt spatial grids, and color contrast tokens in Figma?',
            f'Explain how you architect component variants, boolean properties, and variable modes to build: "{clean_seed}".',
            f'How do you design realistic micro-interactions, hover states, and motion feedback loops for: "{clean_seed}"?',
            f'How do you ensure responsive layout adaptability across mobile (375px), tablet, and desktop (1440px+) for: "{clean_seed}"?',
            f'Describe how you prepare design token specs and Storybook handoff in Figma to guarantee pixel-perfect implementation of: "{clean_seed}".',
            f'How do you design accessible dark mode theming and high-contrast color token palettes for: "{clean_seed}"?',
            f'Scenario: An interface audit shows inconsistent visual patterns in "{clean_seed}". Walk through your component consolidation plan.',
            f'How do you design skeleton loading animations and error recovery states that feel seamless in: "{clean_seed}"?',
            f'What techniques do you use to ensure WCAG 2.2 touch target compliance and keyboard focus indicators in: "{clean_seed}"?',
            f'Describe how you prototype complex multi-step interactive state machines in Figma or ProtoPie for: "{clean_seed}".',
            f'How do you handle visual information density and tabular data visualization within: "{clean_seed}"?',
            f'Scenario: Marketing requires bold branding in "{clean_seed}" that conflicts with accessibility contrast. How do you resolve this?',
            f'How do you design cohesive custom iconography and vector asset systems for: "{clean_seed}"?',
            f'Explain your approach to testing visual rendering across different operating systems and browser rendering engines for: "{clean_seed}".',
            f'How do you document component usage rules and visual constraints for design team members working on: "{clean_seed}"?'
        ]
    elif "front" in r or "react" in r:
        pool = [
            f'Regarding "{clean_seed}" — Explain how you architect the component hierarchy, client/server state, and DOM rendering in React 19/Next.js.',
            f'How do you optimize Core Web Vitals (LCP, INP, CLS) and prevent unnecessary re-renders when implementing: "{clean_seed}"?',
            f'How do you implement keyboard navigation, focus traps, and WAI-ARIA attributes to make "{clean_seed}" 100% WCAG accessible?',
            f'Describe your error boundary, optimistic UI update, and offline cache invalidation strategy for: "{clean_seed}".',
            f'Scenario: Performance profiling reveals high JavaScript main-thread blocking time in "{clean_seed}". Walk through your optimization plan.',
            f'How do you structure client state (Zustand) vs server cache (TanStack Query) for: "{clean_seed}"?',
            f'Explain how you implement code-splitting, dynamic imports, and lazy loading for: "{clean_seed}".',
            f'How do you handle real-time WebSocket event streams and UI throttling/debouncing in: "{clean_seed}"?',
            f'Describe your automated testing strategy (Unit, Component Integration, E2E via Playwright) for: "{clean_seed}".',
            f'How do you manage type safety between backend API responses and frontend TypeScript models in: "{clean_seed}"?',
            f'Scenario: Memory leaks occur when users navigate away and return to "{clean_seed}". How do you profile and eliminate them?',
            f'How do you architect reusable UI library components and design tokens using CSS variables/Tailwind for: "{clean_seed}"?',
            f'Explain how you handle internationalization (i18n) and RTL layout direction in: "{clean_seed}".',
            f'How do you implement progressive enhancement and graceful degradation for users on slow network connections in: "{clean_seed}"?',
            f'Describe how you configure CI/CD bundle size budgets and automated accessibility checks for: "{clean_seed}".'
        ]
    elif "back" in r or "python" in r or "fastapi" in r:
        pool = [
            f'Regarding "{clean_seed}" — Explain the API schema design, idempotency safeguards, and database transaction boundaries (ACID).',
            f'How would you architect the database indexes, query plan, and Redis caching layer to handle high throughput in: "{clean_seed}"?',
            f'What concurrency race conditions, deadlocks, and partial failure modes must be guarded against in: "{clean_seed}"?',
            f'Describe how you implement distributed rate limiting, authentication (JWT/OAuth2), and background worker queues for: "{clean_seed}".',
            f'Scenario: Under 5x peak traffic, the database connection pool saturates for "{clean_seed}". How do you diagnose and resolve the bottleneck?',
            f'How do you structure database schema migrations with zero downtime while serving live traffic to: "{clean_seed}"?',
            f'Explain how you design event-driven messaging with Kafka/RabbitMQ for decoupled services interacting with: "{clean_seed}".',
            f'How do you implement distributed tracing (OpenTelemetry) and structured JSON logging to monitor: "{clean_seed}"?',
            f'Describe your strategy for securing "{clean_seed}" against SQL injection, broken object-level authorization (BOLA), and SSRF.',
            f'How do you handle data partitioning, sharding, and read-replica replication lag for: "{clean_seed}"?',
            f'Scenario: A downstream third-party service dependency fails intermittently in "{clean_seed}". How do you build circuit breaker resiliency?',
            f'How do you design idempotent webhook ingestion with HMAC signature verification for: "{clean_seed}"?',
            f'Explain how you manage database connection lifecycle and async I/O loops in FastAPI/Node for: "{clean_seed}"?',
            f'What automated load testing (k6/Locust) and chaos engineering tests would you run against: "{clean_seed}"?',
            f'How do you structure multi-tenant data isolation (RLS vs separate databases) for: "{clean_seed}"?'
        ]
    else:
        pool = [
            f'Regarding "{clean_seed}" — Explain the chunking strategy, embedding model selection, and hybrid vector search pipeline.',
            f'How do you implement semantic caching, prompt templating, and guardrails to minimize latency and token cost for: "{clean_seed}"?',
            f'How do you architect a multi-step agentic workflow (LangGraph/ReAct) with deterministic tool validation for: "{clean_seed}"?',
            f'Describe how you benchmark and prevent hallucination rates in production using quantitative evaluation frameworks for: "{clean_seed}".',
            f'Scenario: Streaming tokens degrade and experience high TTFT under multi-tenant load for "{clean_seed}". How do you optimize inference?',
            f'How do you enforce document-level Access Control Lists (ACLs) and metadata filtering in vector retrieval for: "{clean_seed}"?',
            f'Explain how you evaluate retrieval precision and context recall (e.g. Ragas) for: "{clean_seed}".',
            f'How do you handle prompt injection attacks and malicious jailbreaks in: "{clean_seed}"?',
            f'Describe your strategy for fine-tuning or domain adaptation vs Retrieval-Augmented Generation for: "{clean_seed}".',
            f'How do you implement rerankers (e.g. Cohere/BGE) to optimize relevance without exceeding latency budgets in: "{clean_seed}"?',
            f'Scenario: An LLM agent in "{clean_seed}" enters an unproductive tool-calling loop. How do you detect and recover safely?',
            f'How do you design structured JSON schema validation and deterministic output parsing for: "{clean_seed}"?',
            f'Explain how you monitor cost, token drift, and latency anomalies across LLM endpoints serving: "{clean_seed}".',
            f'How do you implement synthetic evaluation datasets to continuously test edge cases in: "{clean_seed}"?',
            f'What is your approach to handling multi-modal inputs (PDFs, images, tables) within: "{clean_seed}"?'
        ]

    # If count exceeds pool, dynamically synthesize numbered variants
    result = pool[:count]
    while len(result) < count:
        idx = len(result) + 1
        result.append(f'Deep-Dive Scenario {idx}: In the context of "{clean_seed}", describe how you measure operational trade-offs, edge-case failure modes, and stakeholder alignment.')

    return result[:count]


def get_fallback_questions(role: str, skills: List[str], count: int, custom_q: str = "") -> List[str]:
    """Provides a guaranteed list of exactly `count` role-specific questions."""
    if custom_q and len(custom_q.strip()) > 5:
        return generate_seed_derived_questions(custom_q.strip(), role, count)

    role_lower = (role or "").lower()
    if any(k in role_lower for k in ["ux designer", "user experience", "ux researcher", "interaction designer"]) and "product" not in role_lower and "ui/ux" not in role_lower:
        key = "ux"
    elif "product designer" in role_lower or "lead product designer" in role_lower:
        key = "product"
    elif "ui/ux" in role_lower or "ui designer" in role_lower or "visual designer" in role_lower:
        key = "uiux"
    elif "frontend" in role_lower or "front-end" in role_lower or "react" in role_lower:
        key = "frontend"
    elif "backend" in role_lower or "back-end" in role_lower or "python" in role_lower or "fastapi" in role_lower or "java" in role_lower:
        key = "backend"
    elif "genai" in role_lower or "ai" in role_lower or "llm" in role_lower or "rag" in role_lower:
        key = "genai"
    else:
        key = "ux"

    pool = PYTHON_ROLE_BANKS.get(key, PYTHON_ROLE_BANKS["ux"])

    # If requested count is within pool
    if count <= len(pool):
        return pool[:count]

    # If count exceeds pool, cycle or generate high quality variants
    result = list(pool)
    while len(result) < count:
        idx = len(result) + 1
        skill_name = skills[(idx - 1) % len(skills)] if skills else role
        result.append(f"Practical Execution & System Scenario #{idx}: How do you design, test, and optimize {skill_name} under strict production performance constraints?")

    return result[:count]


def parse_raw_questions(raw_text: str, target_count: Optional[int] = None) -> List[str]:
    """
    Parses LLM output into a clean, robust list of questions.
    Handles numbered formats (1., 1), Q1:, etc.), multi-line questions,
    and strips out category headers and preamble noise.
    """
    if not raw_text:
        return []

    lines = raw_text.strip().split("\n")
    questions = []
    current_q = ""

    # Patterns for question prefixes: '1.', '1)', '1 -', 'Q1:', 'Question 1:', etc.
    q_start_pattern = re.compile(r"^(?:q(?:uestion)?\s*\d+[\.\:\)]|\d+[\.\:\)\-]|\[\d+\]|\*\*\d+[\.\:\)]\*\*)\s*", re.IGNORECASE)
    
    # Patterns for non-question noise lines
    noise_header_pattern = re.compile(r"^(#+\s*|(?:\*\*|\*|__|_))?(theory|coding|scenario|hr|technical|behavioral|general|system design|user research|usability testing|information architecture|interaction design|product strategy|business impact|visual design|design systems|core javascript|performance|distributed systems|llm & rag|agents|evaluation|core principles|advanced methodology|here is|here are|questions strictly|strictly tailored|strictly focused|required topic|format:|output:|instructions:)", re.IGNORECASE)

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # Skip obvious markdown headers or category titles (e.g. '### User Research', '**Core JavaScript:**')
        clean_no_md = re.sub(r"[\*\_#:]", "", cleaned).strip()
        if noise_header_pattern.match(cleaned) or (cleaned.endswith(":") and len(cleaned.split()) <= 6 and not cleaned.endswith("?:")):
            # If line is pure header/category without a number, skip
            if not q_start_pattern.match(cleaned):
                continue

        # Check if this line starts a new numbered question
        if q_start_pattern.match(cleaned):
            # Save previous accumulated question if present
            if current_q:
                clean_prev = re.sub(r"^\*\*(.*?)\*\*$", r"\1", current_q).strip()
                if len(clean_prev) > 8:
                    questions.append(clean_prev)
            # Start new question (strip leading numbering)
            current_q = q_start_pattern.sub("", cleaned).strip()
        else:
            # Continuation line of current question
            if current_q:
                # Append to current question text
                current_q += " " + cleaned
            else:
                # Plain line that might be a question (e.g., if LLM didn't number)
                clean_line = re.sub(r"^[\-\*\•]\s*", "", cleaned).strip()
                if len(clean_line) > 15 and not clean_line.lower().startswith(("here are", "sure,", "below is", "note:", "let me know")):
                    current_q = clean_line

    # Append the last accumulated question
    if current_q:
        clean_prev = re.sub(r"^\*\*(.*?)\*\*$", r"\1", current_q).strip()
        if len(clean_prev) > 8:
            questions.append(clean_prev)

    # Final cleanup on each question
    cleaned_questions = []
    for q in questions:
        # Strip remaining markdown bold wrapping or leading bullet characters
        q_clean = re.sub(r"^\*\*(.*?)\*\*$", r"\1", q).strip()
        q_clean = re.sub(r"^[\-\*\•\>\#]+\s*", "", q_clean).strip()
        q_clean = re.sub(r"^\"(.*?)\"$", r"\1", q_clean).strip()
        if len(q_clean) > 8 and not q_clean.lower().startswith(("here are", "below is", "i hope this")):
            cleaned_questions.append(q_clean)

    # If target_count is specified and we have more, slice to exact count
    if target_count is not None and target_count > 0:
        if len(cleaned_questions) > target_count:
            cleaned_questions = cleaned_questions[:target_count]

    return cleaned_questions

def generate_question_bundle(role: str, difficulty: str, count: int, custom_question: str = "", temperature: Optional[float] = None) -> List[dict]:
    """Generate a structured question bundle.
    Returns a list of dictionaries each containing the keys:
        question, difficulty, model_answer, explanation, key_points, common_mistakes.
    Handles JSON parsing, markdown fences, and missing/invalid fields gracefully.
    """
    from .prompts import question_bundle_prompt
    # Build the prompt using the existing prompt builder
    prompt = question_bundle_prompt(role, difficulty, count, custom_question)
    try:
        raw = generate_ai_questions(prompt, temperature=temperature)
    except Exception as exc:
        logger.warning("Failed to generate question bundle: %s", exc)
        return []
    # Strip potential markdown code fences
    if raw.strip().startswith("```"):
        # Remove leading/trailing fences
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw.strip())
        raw = re.sub(r"\n?```$", "", raw)
    try:
        bundle = json.loads(raw)
    except json.JSONDecodeError as jde:
        logger.warning("Question bundle JSON decode error: %s; raw: %s", jde, raw[:200])
        return []
    if not isinstance(bundle, list):
        logger.warning("Question bundle is not a list; got %s", type(bundle))
        return []
    # Validate required fields for each item
    required_keys = {"question", "difficulty", "model_answer", "explanation", "key_points", "common_mistakes"}
    valid_items = []
    for item in bundle:
        if not isinstance(item, dict):
            continue
        if not required_keys.issubset(item.keys()):
            missing = required_keys - item.keys()
            logger.warning("Bundle item missing keys %s: %s", missing, item)
            continue
        # Ensure lists for key_points and common_mistakes
        if not isinstance(item.get("key_points"), list):
            item["key_points"] = []
        if not isinstance(item.get("common_mistakes"), list):
            item["common_mistakes"] = []
        valid_items.append(item)
    return valid_items


def build_contextual_sample_answer(
    question: str,
    role: str = "",
    skills: Optional[List[str]] = None,
    difficulty: str = "Intermediate"
) -> dict:
    """
    Constructs a rich, domain-relevant sample answer, key concepts, and practical example
    specifically tailored to the question prompt and role context without hallucinating personal credentials.
    """
    q_lower = (question or "").lower()
    skills_list = skills or []
    role_name = role or "Technical Lead"

    # 1. WCAG / Accessibility / Keyboard Navigation
    if any(k in q_lower for k in ["wcag", "accessib", "keyboard", "screen reader", "wai-aria", "focus trap", "skip link"]) or re.search(r"\baria\b", q_lower):
        return {
            "sample_answer": (
                "When designing accessible interfaces, I anchor the implementation directly to WCAG 2.2 AA standards. "
                "I establish a predictable tab order with visible, high-contrast focus indicators and implement focus management "
                "so modal dialogs and nested drawers trap focus while active and return focus to the trigger upon dismissal. "
                "All interactive elements utilize semantic HTML or appropriate ARIA roles like aria-expanded and aria-controls, "
                "and keyboard listeners handle Tab, Shift+Tab, Escape, and Arrow keys according to WAI-ARIA authoring practices. "
                "Finally, I combine automated axe-core audits with manual screen-reader testing to guarantee compliance."
            ),
            "key_points": [
                "Strict adherence to WCAG 2.2 AA standards (focus indicators, 4.5:1 text contrast, 24x24px target sizes)",
                "Focus trapping within modal overlays and returning focus to the triggering element upon close",
                "Accurate semantic HTML and WAI-ARIA states (aria-expanded, aria-controls, aria-live for dynamic updates)",
                "Dual verification using automated linting (axe-core) and hands-on screen-reader navigation (NVDA/VoiceOver)"
            ],
            "practical_example": (
                "In a multi-level configuration drawer, binding an Escape key listener to close the panel and immediately refocus "
                "the initiating button ensures keyboard-only users never lose their navigational context."
            )
        }

    # 2. Design Systems / Design Tokens / Figma / Auto-layout
    elif any(k in q_lower for k in ["design token", "figma", "design system", "spatial rhythm", "typography", "auto-layout", "component library", "variables"]):
        return {
            "sample_answer": (
                "A scalable design system relies on a three-tier token hierarchy: Global reference tokens (e.g., color palette primitives and a 4pt/8pt spacing base), "
                "Semantic tokens that capture intent (such as surface-primary or pen-accent), and Component-scoped tokens that govern specific element states. "
                "In tooling like Figma, I organize variables with mode switches to seamlessly support light, dark, and high-contrast themes. "
                "I construct components using auto-layout with min/max constraints so they resize fluidly across viewports. "
                "To ensure design-engineering parity, token naming follows a standardized JSON schema that directly exports to CSS custom properties in the codebase."
            ),
            "key_points": [
                "Three-tier token structure (Global primitives -> Semantic intent -> Component-scoped tokens)",
                "Figma Variables mode switching for zero-drift light and dark theme adaptation",
                "Auto-layout geometry with fluid min-width and max-width responsive rules",
                "Automated token compilation syncing Figma design definitions directly to CSS custom properties"
            ],
            "practical_example": (
                "Mapping color primitives to semantic aliases like var(--pen) and var(--paper) allows an enterprise application "
                "to toggle between light and dark themes instantaneously without writing component-level style overrides."
            )
        }

    # 3. User Research / Usability Testing / Discovery / Personas
    elif any(k in q_lower for k in ["user research", "usability test", "discovery", "persona", "journey map", "user drop-off", "interviews", "card sorting"]):
        return {
            "sample_answer": (
                "I approach user research through a mixed-methods framework, triangulating qualitative user observations with quantitative product telemetry. "
                "When investigating friction or drop-off, I first analyze analytics funnels to pinpoint where drop-offs occur, then conduct task-based usability testing "
                "with representative participants using open-ended, non-leading prompts. "
                "I measure task completion rates, time-on-task, and Single Ease Question (SEQ) scores alongside qualitative think-aloud feedback. "
                "Synthesizing these insights reveals whether user hesitation stems from cognitive load, ambiguous labeling, or missing value propositions, "
                "allowing the team to iterate with targeted, validated adjustments."
            ),
            "key_points": [
                "Mixed-methods triangulation (combining quantitative funnel metrics with qualitative think-aloud observation)",
                "Objective, non-leading task scenarios and standardized usability benchmarks (SEQ, SUS)",
                "Distinguishing cognitive friction and mental model mismatches from value-proposition gaps",
                "Rapid, evidence-backed iteration loops shared transparently with cross-functional partners"
            ],
            "practical_example": (
                "When users drop off during an onboarding step, pairing heatmaps with 5 unmoderated usability sessions often reveals "
                "that a single ambiguous form label is causing user hesitation, which an immediate copy iteration resolves."
            )
        }

    # 4. Product Management / A/B Testing / Roadmaps / Metrics / Prioritization
    elif any(k in q_lower for k in ["a/b test", "experiment", "metric", "priorit", "roadmap", "north star", "trade-off", "kano", "rice"]):
        return {
            "sample_answer": (
                "Balancing product metrics requires establishing a primary North Star metric paired with explicit counter-balancing guardrail metrics. "
                "For instance, when optimizing conversion rate, the guardrail metric must track customer satisfaction and retention to avoid dark patterns. "
                "I evaluate trade-offs using structured frameworks like RICE or Kano modeling to prioritize initiatives with high customer value against technical effort. "
                "When A/B testing, I ensure statistical rigor by calculating Minimum Detectable Effect (MDE) and sample sizes beforehand. "
                "If qualitative sentiment clashes with short-term positive numbers, I prioritize long-term user trust, as short-term gains at the expense of user experience inevitably lead to churn."
            ),
            "key_points": [
                "Pairing primary conversion metrics with health/guardrail metrics (e.g. retention, CSAT, task success)",
                "Structured prioritization (RICE scoring balancing reach, impact, confidence, and engineering effort)",
                "Statistical hygiene in A/B experimentation (pre-determining sample size, power, and significance thresholds)",
                "Defending long-term user trust over short-term conversion gains"
            ],
            "practical_example": (
                "Introducing an optional step in a checkout flow might slightly reduce instantaneous conversion, but if it decreases return rates "
                "and boosts 90-day repeat purchases, the overall customer lifetime value increases significantly."
            )
        }

    # 5. React 19 / Server Components / Next.js / Hydration / Frontend Performance
    elif any(k in q_lower for k in ["react", "server component", "rsc", "hydration", "next.js", "cls", "lcp", "inp", "web vitals", "render"]):
        return {
            "sample_answer": (
                "Modern frontend architecture centers on minimizing client JavaScript bundle size and optimizing the critical rendering path. "
                "With React Server Components (RSC), data-fetching and heavy dependencies remain entirely on the server, streaming HTML chunks to the browser "
                "inside Suspense boundaries while selective hydration activates client-side interactivity where needed. "
                "For Core Web Vitals, I optimize LCP through resource prioritization and preloading critical hero content, eliminate CLS by defining explicit dimensions "
                "and aspect-ratio boxes, and maintain low INP by offloading heavy computations and breaking long tasks into smaller microtasks."
            ),
            "key_points": [
                "Executing data fetching and dependencies on the server via React Server Components (RSC) to reduce bundle payload",
                "Progressive streaming with Suspense boundaries to lower Time-to-First-Byte (TTFB) and First Contentful Paint (FCP)",
                "Eliminating Cumulative Layout Shift (CLS) through explicit layout sizing and reserved aspect ratios",
                "Preserving responsive Interaction to Next Paint (INP) by keeping main thread tasks below 50ms"
            ],
            "practical_example": (
                "Moving markdown rendering and syntax highlighting libraries into a Server Component prevents hundreds of kilobytes "
                "of parsing logic from reaching the client bundle, directly boosting mobile performance."
            )
        }

    # 6. State Management / Caching / Zustand / TanStack Query
    elif any(k in q_lower for k in ["state management", "zustand", "redux", "tanstack query", "cache", "swr", "optimistic"]):
        return {
            "sample_answer": (
                "I approach state architecture by strictly separating server cache state from client UI state. "
                "Server state—which is asynchronous, shared, and prone to going stale—is managed with tools like TanStack Query using stale-while-revalidate "
                "caching, automatic deduplication, and optimistic mutations with rollback handlers. "
                "Client-only state—such as modal visibility, active filters, or draft inputs—is managed with lightweight stores like Zustand. "
                "This separation prevents bloat in client state managers, removes manual synchronization boilerplate, and ensures clean component boundaries."
            ),
            "key_points": [
                "Clear bifurcation of server cache state (asynchronous, remote) vs client UI state (synchronous, local)",
                "Leveraging query deduplication, background revalidation, and cache invalidation policies",
                "Implementing optimistic UI updates with automated rollback upon network failures",
                "Using atomic selectors to prevent unnecessary re-rendering across component trees"
            ],
            "practical_example": (
                "When a candidate bookmarks a question, immediately updating the bookmark icon locally while triggering an asynchronous "
                "API mutation provides instantaneous UI feedback, rolling back with an alert only if the network request fails."
            )
        }

    # 7. Distributed Systems / Idempotency / Redis / Locking / Concurrency
    elif any(k in q_lower for k in ["distributed", "idempotenc", "redis", "lock", "concurrency", "race condition", "circuit breaker", "deadlock"]):
        return {
            "sample_answer": (
                "Ensuring reliability across distributed services requires designing for failure and network latency from day one. "
                "To prevent duplicate executions on network retries, critical write endpoints require an Idempotency-Key header. "
                "I store idempotency records in an in-memory store like Redis with a suitable TTL and verify them atomically before processing. "
                "For shared resource synchronization, I utilize distributed locks with automatic lease expirations to prevent deadlocks, "
                "backed by database-level atomic upserts (INSERT ... ON CONFLICT). "
                "Between services, I implement circuit breakers and exponential backoff jitter to protect downstream dependencies during degradations."
            ),
            "key_points": [
                "Enforcing idempotency keys on write operations to guarantee at-most-once execution",
                "Distributed locking with TTL expiration to prevent resource deadlocks",
                "Database-level atomicity and optimistic concurrency control (version numbers / conditional writes)",
                "Fault tolerance with circuit breakers, timeouts, and exponential backoff retry jitter"
            ],
            "practical_example": (
                "Generating a unique client transaction UUID stored in Redis with a 24-hour lease ensures payment or score submission "
                "requests cannot execute twice, even if the user double-clicks or experiences a spotty mobile connection."
            )
        }

    # 8. Databases / PostgreSQL / SQL / Indexing / Query Optimization
    elif any(k in q_lower for k in ["database", "postgresql", "sql", "index", "query", "acid", "transaction", "sharding", "schema"]):
        return {
            "sample_answer": (
                "Database performance begins with proper indexing and relational modeling. "
                "When analyzing slow queries, I inspect the execution plan using EXPLAIN ANALYZE to identify sequential table scans and nested loops. "
                "I design B-tree indexes matching query WHERE and ORDER BY predicates, being mindful of index selectivity and write overhead. "
                "For transactions, I choose appropriate isolation levels to balance consistency against lock contention. "
                "To support high throughput, I place a connection pooler like PgBouncer in front of PostgreSQL, keep transactions short, "
                "and separate read queries to read-replicas when analytical queries threaten OLTP workloads."
            ),
            "key_points": [
                "Query diagnosis via EXPLAIN ANALYZE (identifying table scans, buffer usage, and join bottlenecks)",
                "Targeted composite indexing respecting column selectivity and left-prefix rules",
                "Transaction isolation hygiene to prevent dirty reads and serialization anomalies",
                "Connection pooling (PgBouncer) and read-replica offloading to protect primary databases"
            ],
            "practical_example": (
                "Adding a composite index on (candidate_id, created_at DESC) transforms a full sequential scan of hundreds of thousands "
                "of historical interview records into an instant index scan with sub-5ms response time."
            )
        }

    # 9. LLMs / RAG / GenAI / Vector Databases / Embeddings
    elif any(k in q_lower for k in ["llm", "rag", "vector", "embedding", "genai", "prompt", "chunking", "hallucination", "retrieval"]):
        return {
            "sample_answer": (
                "Architecting high-accuracy RAG systems requires optimizing every stage of the retrieval and generation pipeline. "
                "I implement semantic chunking with sliding window overlap rather than arbitrary character splits to preserve topical context. "
                "For retrieval, I combine dense vector search with sparse BM25 keyword matching via Reciprocal Rank Fusion (RRF), "
                "followed by a cross-encoder reranker to surface the top-5 most relevant context snippets. "
                "At generation time, I apply strict system prompt guardrails and few-shot examples, and evaluate system accuracy "
                "using synthetic benchmarks measuring context precision, faithfulness, and answer relevance."
            ),
            "key_points": [
                "Semantic chunking with token overlap to preserve coherent contextual boundaries",
                "Hybrid search combining dense embeddings (semantic similarity) and sparse BM25 (keyword recall)",
                "Cross-encoder reranking to filter out noisy context before prompting the LLM",
                "Systematic evaluation frameworks measuring hallucination rates, retrieval precision, and latency"
            ],
            "practical_example": (
                "In a resume-to-job matching pipeline, hybrid retrieval ensures exact acronym matches (e.g. 'AWS ECS') are captured via BM25 "
                "while overarching domain capabilities are matched semantically via vector embeddings."
            )
        }

    # 10. Security / Authentication / JWT / RBAC
    elif any(k in q_lower for k in ["security", "jwt", "oauth", "auth", "rbac", "injection", "token"]):
        return {
            "sample_answer": (
                "Application security demands defense-in-depth across the entire stack. "
                "For authentication, I utilize short-lived JWT access tokens stored in HttpOnly, Secure, SameSite=Lax cookies to mitigate XSS vulnerabilities, "
                "paired with server-validated refresh tokens with rotation and revocation mechanisms. "
                "Authorization relies on centralized Role-Based Access Control (RBAC) enforced strictly at the API route layer rather than client-side checks. "
                "At the data tier, all queries use parameterized statements to prevent SQL injection, and cryptographic routines utilize audited algorithms like PBKDF2 with high iteration counts."
            ),
            "key_points": [
                "Storing authentication tokens in HttpOnly, Secure, SameSite cookies to mitigate XSS interception",
                "Strict server-side RBAC validation on every protected route and resource ID",
                "Parameterized queries and ORM abstractions to prevent SQL injection",
                "Rate-limiting and automated brute-force protection on authentication entrypoints"
            ],
            "practical_example": (
                "Enforcing tenant ownership checks directly in the database query (e.g. WHERE user_id = current_user.id) "
                "ensures that manipulating an ID in a URL or payload can never expose another candidate's private data."
            )
        }

        # 11. DevOps / CI/CD / Docker / Kubernetes / Cloud / Infrastructure
    elif any(k in q_lower for k in ["devops", "ci/cd", "docker", "kubernetes", "k8s", "deploy", "terraform", "helm", "aws", "gcp", "azure"]):
        return {
            "sample_answer": (
                "My approach to cloud infrastructure and CI/CD revolves around declarative automation and immutable delivery artifacts. "
                "I configure automated build pipelines that run linting, security scans, and unit suites on every pull request before packaging container images. "
                "For zero-downtime production deployments, I utilize progressive delivery techniques like canary or blue-green rollouts governed by automated health checks. "
                "All infrastructure is codified via Terraform or Kubernetes manifests to guarantee environment parity, drift detection, and rapid disaster recovery."
            ),
            "key_points": [
                "Declarative Infrastructure as Code (IaC) ensuring reproducible, auditable environments",
                "Automated progressive deployment strategies (canary/blue-green) with zero downtime",
                "Shift-left automated pipeline validation (SAST, unit testing, image vulnerability scanning)",
                "Comprehensive cluster observability with health checks, readiness probes, and automated rollbacks"
            ],
            "practical_example": (
                "Using Kubernetes readiness probes alongside automated metric thresholds in a canary deployment ensures "
                "traffic is immediately diverted away from newly rolled-out pods if response latency or error rates spike."
            )
        }

    # 12. API Design / Microservices / REST / GraphQL / gRPC
    elif any(k in q_lower for k in ["api", "rest", "graphql", "grpc", "microservice", "endpoint", "contract"]):
        return {
            "sample_answer": (
                "Designing production APIs requires a contract-first approach with clear domain boundaries. "
                "I define schemas using OpenAPI specifications before writing endpoint logic, ensuring client teams have predictable contracts. "
                "For high-volume list endpoints, I implement cursor-based pagination to maintain sub-second performance without pagination drift. "
                "I enforce standard HTTP semantics, strict payload validation with Pydantic, and centralized error handling with descriptive machine-readable error codes. "
                "For low-latency inter-service communication, I adopt gRPC with binary serialization to reduce payload overhead."
            ),
            "key_points": [
                "Contract-first schema design with strict payload validation and versioning strategies",
                "Cursor-based pagination to prevent query degradation on large relational datasets",
                "Consistent, machine-readable HTTP status codes and structured error responses",
                "Choosing appropriate communication protocols (REST for external consumers, gRPC for internal mesh)"
            ],
            "practical_example": (
                "Replacing offset/limit queries with cursor-based pagination (WHERE id > last_seen_id) avoids duplicate items "
                "when new records are inserted while a user scrolls an infinite feed."
            )
        }

    # 13. Testing / QA / Test Automation / E2E / TDD
    elif any(k in q_lower for k in ["test", "tdd", "cypress", "playwright", "mock", "stub", "qa", "coverage"]):
        return {
            "sample_answer": (
                "A resilient quality strategy adheres to the Testing Pyramid, prioritizing fast, deterministic unit tests for core business logic. "
                "At the boundary layer, integration tests verify database queries and external service contracts against ephemeral test containers. "
                "I reserve end-to-end tests (via Playwright or Cypress) for critical revenue-generating candidate journeys to guard against UI regressions. "
                "I treat test code with the same rigor as production code, isolating tests to run concurrently without shared mutable state."
            ),
            "key_points": [
                "Balanced Testing Pyramid (high-coverage unit tests, targeted integration, lean E2E)",
                "Hermetic, reproducible test environments utilizing ephemeral containerized dependencies",
                "Contract testing and boundary mocking to decouple third-party API availability from test runs",
                "Enforcing code coverage and automated regression gates in CI before merge"
            ],
            "practical_example": (
                "Running database tests against an in-memory SQLite instance or containerized Postgres ensures tests execute in milliseconds "
                "while providing genuine transactional verification."
            )
        }

    # 14. Data Engineering / Streaming / Kafka / Pipelines / ETL
    elif any(k in q_lower for k in ["data", "kafka", "pipeline", "etl", "spark", "streaming", "batch", "warehouse"]):
        return {
            "sample_answer": (
                "Robust data engineering requires treating data pipelines as distributed, fault-tolerant state machines. "
                "I design event streaming architectures using Kafka with partitioned topics to achieve linear horizontal throughput. "
                "Consumers are designed to be strictly idempotent, storing offsets alongside transactional writes to guarantee effectively once processing. "
                "For unparseable or poisoned messages, I route errors to Dead Letter Queues (DLQ) with alert thresholds rather than stalling consumers. "
                "Data schemas are strictly governed via Schema Registries to prevent downstream pipeline breakage."
            ),
            "key_points": [
                "Topic partitioning and consumer group management for horizontal data scaling",
                "Idempotent consumer processing ensuring safe retries under at-least-once message delivery",
                "Dead Letter Queue (DLQ) isolation preventing poison-pill messages from crashing pipelines",
                "Strict schema enforcement (Avro/Protobuf) protecting analytical consumers from silent drift"
            ],
            "practical_example": (
                "Recording transaction IDs in an atomic deduplication store before applying mutations guarantees event replays "
                "do not double-increment candidate scores or duplicate analytics records."
            )
        }

    # 15. Default / General Engineering Architecture
    else:
        return {
            "sample_answer": (
                f"When addressing this in a production {role_name} setting, I begin by clarifying the core functional requirements and service-level objectives (SLOs). "
                "I break the problem into modular components with clean interface boundaries to ensure maintainability and testability. "
                "I evaluate technical trade-offs—such as latency vs consistency, or development velocity vs long-term scalability—choosing patterns that fit the organization's scale. "
                "During implementation, I establish comprehensive test coverage and telemetry to monitor system health and catch regressions early."
            ),
            "key_points": [
                "Clear requirement decomposition and establishing measurable SLOs (latency, throughput, reliability)",
                "Evaluating explicit trade-offs and selecting appropriate industry-standard design patterns",
                "Designing decoupled, modular components with clear interface contracts",
                "Comprehensive automated test coverage and operational observability"
            ],
            "practical_example": (
                "Designing systems with clear interfaces and automated integration tests allows teams to refactor internal data stores "
                "or business logic without risking breaking changes across external consumer services."
            )
        }


def generate_sample_answer(
    question: str,
    role: str = "",
    skills: Optional[List[str]] = None,
    difficulty: str = "Intermediate"
) -> dict:
    """
    Generates a structured sample answer with key points and a practical example.
    Uses configured AI provider (Gemini / Groq) if available; falls back seamlessly to
    the domain-aware contextual generator if AI is unavailable or fails.
    """
    clean_q = (question or "").strip()
    if not clean_q:
        return {
            "sample_answer": "Please provide a valid question to view the sample answer.",
            "key_points": [],
            "practical_example": None
        }

    provider_name, is_configured = get_ai_provider_status()
    if is_configured:
        try:
            from .prompts import sample_answer_prompt
            prompt = sample_answer_prompt(clean_q, role, skills, difficulty)
            raw = generate_ai_questions(prompt, temperature=0.4)
            # Clean markdown code fences if present
            cleaned_raw = raw.strip()
            if cleaned_raw.startswith("```"):
                cleaned_raw = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned_raw)
                cleaned_raw = re.sub(r"\n?```$", "", cleaned_raw)
            data = json.loads(cleaned_raw)
            if isinstance(data, dict) and "sample_answer" in data:
                return {
                    "sample_answer": str(data.get("sample_answer", "")).strip(),
                    "key_points": [str(p).strip() for p in data.get("key_points", []) if str(p).strip()],
                    "practical_example": str(data.get("practical_example", "")).strip() or None
                }
        except Exception as exc:
            logger.warning("AI provider sample answer generation failed (%s); using contextual engine", exc)

    return build_contextual_sample_answer(clean_q, role, skills, difficulty)


def build_contextual_evaluation_fallback(
    question: str,
    answer: str = "",
    role: str = "Software Engineer",
    skills: Optional[List[str]] = None,
    difficulty: str = "Intermediate",
    sample_answer: Optional[str] = None,
    key_points: Optional[List[str]] = None,
    candidate_answer: Optional[str] = None,
    **kwargs
) -> dict:
    clean_ans = (candidate_answer if candidate_answer is not None else answer or "").strip()
    """
    Deterministic fallback evaluation engine that scores candidate answers
    using rubrics, keyword relevance, structural analysis, and depth criteria.
    """
    clean_ans = (answer or "").strip()
    words = clean_ans.split()
    word_count = len(words)
    ans_lower = clean_ans.lower()
    q_lower = (question or "").lower()

    # 1. Relevance Score (1-5)
    stopwords = {"what", "how", "why", "when", "where", "which", "is", "are", "the", "and", "you", "your", "for", "with", "that", "this", "from"}
    q_words = [w.strip('?,.:;"()[]') for w in q_lower.split() if len(w) > 3 and w not in stopwords]
    q_matches = sum(1 for w in q_words if w in ans_lower)
    skills_list = skills or []
    skills_matches = sum(1 for s in skills_list if s.lower() in ans_lower)

    if word_count < 10:
        relevance_score = 2
    elif q_matches >= 2 or skills_matches >= 1:
        relevance_score = 5 if word_count >= 30 else 4
    elif q_matches == 1:
        relevance_score = 3
    else:
        relevance_score = 3

    # 2. Technical Accuracy Score (1-5)
    tech_terms = ["api", "data", "system", "component", "state", "server", "client", "service", "cache",
                  "database", "index", "query", "async", "sync", "test", "security", "token", "auth",
                  "scale", "performance", "model", "schema", "architecture", "interface", "protocol"]
    tech_matches = sum(1 for t in tech_terms if t in ans_lower)
    if word_count < 15:
        accuracy_score = 2
    elif tech_matches >= 4 or skills_matches >= 2:
        accuracy_score = 5 if word_count >= 40 else 4
    elif tech_matches >= 2:
        accuracy_score = 4
    else:
        accuracy_score = 3

    # 3. Depth & Trade-offs Score (1-5)
    depth_terms = ["trade-off", "tradeoff", "because", "latency", "scale", "performance", "metric",
                   "failure", "edge case", "versus", "vs", "monitoring", "cost", "complexity",
                   "consistency", "fallback", "resilience", "redundancy", "sla", "slo"]
    depth_matches = sum(1 for d in depth_terms if d in ans_lower)
    if word_count < 25:
        depth_score = 2
    elif depth_matches >= 3 and word_count >= 50:
        depth_score = 5
    elif depth_matches >= 1 and word_count >= 35:
        depth_score = 4
    elif depth_matches >= 1 or word_count >= 30:
        depth_score = 3
    else:
        depth_score = 2

    # 4. Communication Clarity Score (1-5)
    sentences = [s.strip() for s in re.split(r'[.!?]+', clean_ans) if s.strip()]
    if word_count < 15:
        comm_score = 2
    elif len(sentences) >= 3 and 25 <= word_count <= 250:
        comm_score = 5
    elif len(sentences) >= 2 and word_count >= 20:
        comm_score = 4
    else:
        comm_score = 3

    # Overall Score (sum of 4 dimensions: 1-20)
    overall_score = relevance_score + accuracy_score + depth_score + comm_score

    # Concrete Strengths
    strengths = []
    if q_matches > 0 or relevance_score >= 4:
        strengths.append(f"Directly addresses the core scenario presented in the interview question.")
    if accuracy_score >= 4:
        strengths.append(f"Demonstrates sound technical accuracy appropriate for a {role or 'Software Engineer'}.")
    if depth_score >= 3:
        strengths.append("Shows awareness of engineering implementation details and operational mechanics.")
    if comm_score >= 4:
        strengths.append("Communicates with clear sentence structure and natural, professional spoken tone.")
    if not strengths:
        strengths.append("Provides a foundational starting response that identifies relevant high-level concepts.")

    # Concrete Constructive Improvements
    improvements = []
    if depth_score <= 3:
        improvements.append("Elaborate further on architectural trade-offs (e.g. latency vs consistency, complexity vs maintenance).")
    if accuracy_score <= 3:
        improvements.append(f"Incorporate specific technical tools or mechanisms relevant to {', '.join(skills_list[:2]) if skills_list else role}.")
    if word_count < 40:
        improvements.append("Expand on concrete implementation steps or operational monitoring guardrails to show complete end-to-end ownership.")
    if comm_score <= 3:
        improvements.append("Structure the delivery into distinct logical points (e.g. approach, execution details, and validation).")
    if not improvements:
        improvements.append("Consider citing specific production metrics (e.g. p99 latency targets or error budget impact) to elevate to Staff bar.")

    # Missing Key Points
    missing_key_points = []
    if key_points and isinstance(key_points, list):
        for kp in key_points:
            # Check if concept is in answer
            kp_words = [w.lower() for w in kp.split() if len(w) > 4 and w.lower() not in stopwords]
            if not any(w in ans_lower for w in kp_words):
                missing_key_points.append(kp)
            if len(missing_key_points) >= 3:
                break
    if not missing_key_points:
        missing_key_points = [
            "Explicit quantitative evaluation metrics and operational guardrails (e.g. SLOs, telemetry)",
            "Failure mode analysis and graceful degradation strategies under unexpected load"
        ]

    # Model Answer for Learning
    suggested = sample_answer
    if not suggested or len(suggested) < 30:
        ref_pack = build_contextual_sample_answer(question, role, skills, difficulty)
        suggested = ref_pack.get("sample_answer") or (
            f"When resolving this as a {role}, I first establish the operational requirements and interface contracts. "
            "I implement the solution using industry-standard patterns with robust error handling and automated validation. "
            "Finally, I verify system performance and telemetry to ensure end-to-end reliability in production."
        )

    # Next Practice Steps
    next_practice_steps = [
        f"Re-evaluate this answer by explicitly outlining 2 key technical trade-offs before proposing the final solution.",
        "Practice delivering the response out loud within a 90-second window to build concise spoken fluency."
    ]

    return {
        "overall_score": overall_score,
        "relevance_score": relevance_score,
        "technical_accuracy_score": accuracy_score,
        "depth_score": depth_score,
        "communication_score": comm_score,
        "score_breakdown": {
            "relevance": relevance_score,
            "technical_accuracy": accuracy_score,
            "depth": depth_score,
            "communication": comm_score
        },
        "strengths": strengths[:3],
        "improvements": improvements[:3],
        "missing_key_points": missing_key_points[:3],
        "suggested_answer": suggested,
        "next_practice_steps": next_practice_steps
    }


def evaluate_candidate_practice_answer(
    question: str,
    answer: str,
    role: str = "Software Engineer",
    skills: Optional[List[str]] = None,
    difficulty: str = "Intermediate",
    sample_answer: Optional[str] = None,
    key_points: Optional[List[str]] = None,
) -> dict:
    """
    Evaluates a candidate's submitted practice answer.
    Uses AI provider (Gemini / LLM) when configured, and falls back seamlessly
    to the contextual evaluation engine on failure or missing keys.
    """
    clean_ans = (answer or "").strip()
    clean_q = (question or "").strip()

    provider_name, is_configured = get_ai_provider_status()
    if is_configured:
        try:
            from .prompts import candidate_answer_evaluation_prompt
            prompt = candidate_answer_evaluation_prompt(
                question=clean_q,
                answer=clean_ans,
                role=role,
                skills=skills,
                difficulty=difficulty,
                sample_answer=sample_answer,
                key_points=key_points
            )
            raw = generate_ai_questions(prompt, temperature=0.3)
            cleaned_raw = raw.strip()
            if cleaned_raw.startswith("```"):
                cleaned_raw = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned_raw)
                cleaned_raw = re.sub(r"\n?```$", "", cleaned_raw)

            data = json.loads(cleaned_raw)
            if isinstance(data, dict) and "overall_score" in data:
                # Sanitize and bound scores
                rel = max(1, min(5, int(data.get("relevance_score", 3))))
                acc = max(1, min(5, int(data.get("technical_accuracy_score", 3))))
                dep = max(1, min(5, int(data.get("depth_score", 3))))
                com = max(1, min(5, int(data.get("communication_score", 3))))
                tot = rel + acc + dep + com

                return {
                    "overall_score": tot,
                    "relevance_score": rel,
                    "technical_accuracy_score": acc,
                    "depth_score": dep,
                    "communication_score": com,
                    "score_breakdown": {
                        "relevance": rel,
                        "technical_accuracy": acc,
                        "depth": dep,
                        "communication": com
                    },
                    "strengths": [str(s).strip() for s in data.get("strengths", []) if str(s).strip()],
                    "improvements": [str(i).strip() for i in data.get("improvements", []) if str(i).strip()],
                    "missing_key_points": [str(k).strip() for k in data.get("missing_key_points", []) if str(k).strip()],
                    "suggested_answer": str(data.get("suggested_answer", "")).strip() or sample_answer or "",
                    "next_practice_steps": [str(n).strip() for n in data.get("next_practice_steps", []) if str(n).strip()]
                }
        except Exception as exc:
            logger.warning("AI answer evaluation failed (%s); using contextual rubric engine", exc)

    return build_contextual_evaluation_fallback(
        question=clean_q,
        answer=clean_ans,
        role=role,
        skills=skills,
        difficulty=difficulty,
        sample_answer=sample_answer,
        key_points=key_points
    )
