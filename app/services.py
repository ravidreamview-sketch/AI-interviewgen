import os
import re
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Please create a .env file with GROQ_API_KEY=your_key or set it in your environment."
        )
    from groq import Groq
    return Groq(api_key=api_key)


def generate_ai_questions(prompt: str) -> str:
    client = get_groq_client()
    models_to_try = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-3.2-11b-vision-preview",
        "llama-3.2-3b-preview",
        "mixtral-8x7b-32768",
        "gemma2-9b-it"
    ]
    last_err = None
    for model_name in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.6,
                max_tokens=3000,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("Failed to generate AI questions with available Groq models")


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