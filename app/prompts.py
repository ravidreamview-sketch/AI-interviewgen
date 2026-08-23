def interview_prompt(data):
    role_str = (data.role or "").strip()
    role_lower = role_str.lower()
    skills_str = ", ".join(data.skills or [])
    exp = data.experience or "3-5 Years"
    diff = data.difficulty or "Medium"
    company = getattr(data, "company", None) or "General Tech"
    interview_type = getattr(data, "interview_type", None) or "Technical & Architecture"
    num_q = data.number_of_questions or 5
    custom_q = getattr(data, "custom_question", None) or ""

    seed_instruction = ""
    if custom_q.strip():
        seed_instruction = f"""
SPECIFIC SEED / FOCUS TOPIC:
"{custom_q.strip()}"
STRICT REQUIREMENT: Ensure all generated questions directly probe, expand, and branch from this specific topic into deep-dive scenarios, trade-offs, architecture, and edge cases.
"""

    format_instruction = f"""
CRITICAL REQUIREMENTS:
- Target Company Bar: {company}
- Interview Round / Format: {interview_type}
- You MUST generate EXACTLY {num_q} interview questions (numbered sequentially from 1 to {num_q}).
- Return ONLY the numbered list of {num_q} questions.
- Do NOT output any introductory text, section headers, or markdown formatting asterisks around the whole question.
- Format every question on its own line:
1. [First question text]
2. [Second question text]
...
{num_q}. [{num_q}th question text]
"""

    # 1. UX DESIGNER
    if any(k in role_lower for k in ["ux designer", "user experience designer", "ux researcher", "interaction designer"]) and "product" not in role_lower and "ui/ux" not in role_lower:
        return f"""
You are the Head of UX & Design Research conducting a rigorous, role-specific interview for a {role_str} position ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly relevant to UX Design.
{seed_instruction}
STRICT NEGATIVE CONSTRAINT:
- Do NOT generate ANY coding, programming language, database, cloud infrastructure, or software engineering questions.
- Do NOT generate generic HR questions (e.g. "tell me about your strengths").

REQUIRED TOPIC DOMAINS (Distribute the {num_q} questions across these areas):
1. User Research & Discovery (moderated/unmoderated testing, interviews, generative research, synthesis)
2. Usability Testing & Validation (protocols, metrics like SUS/SEQ, task completion rate, A/B validation)
3. Information Architecture & User Flows (mental models, card sorting, wireframing, cognitive load)
4. Interaction Design & Accessibility (WCAG 2.2 Level AA/AAA, affordances, error recovery, responsive patterns)
5. Design Systems & Figma Execution (component architecture, Auto Layout, tokens, developer handoff)
6. Real-World UX Scenarios (handling edge cases, redesigning low-conversion flows, defending UX trade-offs to PM/Eng)
{format_instruction}
"""

    # 2. PRODUCT DESIGNER
    elif "product designer" in role_lower or "lead product designer" in role_lower:
        return f"""
You are the VP of Product Design interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly relevant to Product Design.
{seed_instruction}
STRICT NEGATIVE CONSTRAINT:
- Do NOT generate code-writing or backend questions.
- Focus deeply on the intersection of Product Strategy, Business Metrics, User Experience, and Cross-functional Execution.

REQUIRED TOPIC DOMAINS (Distribute the {num_q} questions across these areas):
1. Product Thinking & UX Strategy (problem framing, user needs vs business goals, prioritization frameworks)
2. Product Metrics & Business Impact (retention, conversion funnels, churn, North Star metrics, A/B testing)
3. Design Systems & Scalability (tokens, multi-platform consistency, component governance)
4. Cross-Functional Collaboration (partnering with Product Managers, balancing engineering feasibility, discovery vs delivery)
5. Complex Product Scenarios (launching 0-to-1 features, sunsetting features, resolving user friction under business constraints)
{format_instruction}
"""

    # 3. UI/UX DESIGNER
    elif "ui/ux" in role_lower or "ui designer" in role_lower or "visual designer" in role_lower:
        return f"""
You are a Principal UI/UX & Interaction Design Director interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly focused on UI/UX Design.
{seed_instruction}
STRICT NEGATIVE CONSTRAINT:
- Do NOT generate software coding or server infrastructure questions.

REQUIRED TOPIC DOMAINS (Distribute the {num_q} questions across these areas):
1. Visual Hierarchy & Craft (typography scale, 8pt/4pt spatial grids, color contrast, micro-interactions)
2. Design Systems & Figma Architecture (variables, modes, interactive component states, token hierarchies)
3. User Experience & Flows (wireframing to high-fidelity, usability heuristics, WCAG accessibility)
4. Interactive Prototyping (motion design principles, realistic user validation prototypes)
5. Practical Scenarios (responsive design across breakpoints, redesigning legacy interfaces, design handoff)
{format_instruction}
"""

    # 4. FRONTEND DEVELOPER
    elif "frontend" in role_lower or "front-end" in role_lower or "ui engineer" in role_lower or "react" in role_lower:
        return f"""
You are a Principal Frontend Architect interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly focused on Modern Frontend Engineering.
{seed_instruction}
REQUIRED TOPIC DOMAINS (Distribute the {num_q} questions across these areas):
1. Core Web Technologies (semantic HTML5, modern CSS flexbox/grid/animations, JS event loop, closures, DOM lifecycle)
2. Frameworks & Architecture (React 19, hooks, component lifecycle, Next.js App Router, SSR vs SSG vs RSC)
3. Performance & Web Vitals (LCP, INP, CLS optimization, bundle splitting, memory leak debugging, virtualized lists)
4. State Management & API Integration (React Query/Zustand/Redux, optimistic updates, WebSocket real-time feeds, caching)
5. Accessibility & Responsive Edge Cases (WCAG 2.2 a11y, ARIA roles, cross-browser rendering quirks, responsive UI)
6. Real-World Frontend Scenarios (architecting a high-frequency trading dashboard, handling offline sync)
{format_instruction}
"""

    # 5. BACKEND DEVELOPER
    elif "backend" in role_lower or "back-end" in role_lower or "api engineer" in role_lower or "python engineer" in role_lower or "java" in role_lower:
        return f"""
You are a Principal Backend & Systems Architect interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly focused on Backend Engineering and Distributed Systems.
{seed_instruction}
REQUIRED TOPIC DOMAINS (Distribute the {num_q} questions across these areas):
1. API Design & Frameworks (RESTful best practices, FastAPI/Node/Go, GraphQL, gRPC, idempotent request handling)
2. Databases & Storage (PostgreSQL/MySQL indexing strategies, query execution plans, transactions/ACID, connection pooling)
3. Scalability, Caching & Concurrency (Redis caching patterns, async event loops, message queues like Kafka/RabbitMQ, sharding)
4. Security & Authentication (JWT, OAuth2, RBAC, SQL injection & rate-limiting safeguards)
5. Distributed Systems Scenarios (handling partial network outages, microservices communication, circuit breakers, deadlocks)
{format_instruction}
"""

    # 6. GENAI ENGINEER
    elif "genai" in role_lower or "llm" in role_lower or "ai engineer" in role_lower or "machine learning" in role_lower or "rag" in role_lower:
        return f"""
You are a Chief AI Architect interviewing a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly focused on Generative AI, LLMs, and AI Systems.
{seed_instruction}
REQUIRED TOPIC DOMAINS (Distribute the {num_q} questions across these areas):
1. LLM Architecture & Foundations (transformer attention mechanics, tokenization, context window management, quantized models)
2. Retrieval-Augmented Generation (RAG) (chunking strategies, sparse BM25 vs dense embeddings, hybrid search, rerankers)
3. Vector Databases & Indexing (HNSW, IVFFlat, vector database scalability in Pinecone/Milvus/Qdrant/pgvector)
4. Prompt Engineering & Agentic Systems (Chain-of-Thought, ReAct frameworks, LangGraph/AutoGen tool-calling agents)
5. LLM Evaluation & Guardrails (measuring hallucinations via Ragas/TruLens, latency vs cost trade-offs, guardrail filtering)
6. Production GenAI Scenarios (building multi-tenant RAG with strict ACLs, handling streaming token degradation)
{format_instruction}
"""

    # 7. DEFAULT / CUSTOM ROLE
    else:
        return f"""
You are a Principal Hiring Manager and Senior Interviewer conducting a specialized interview for a {role_str} ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} interview questions strictly tailored to the responsibilities, tools, and technical nuances of {role_str}.
{seed_instruction}
STRICT REQUIREMENTS:
- Every question must be 100% relevant to {role_str}.
- Include practical hands-on execution, realistic scenario-based questions, and trade-offs/metrics.
- Scale difficulty strictly to match {exp}.
{format_instruction}
"""