from typing import Optional
from datetime import timezone

# Difficulty instruction templates (simple English for beginners, deeper for advanced)
DIFFICULTY_INSTRUCTIONS = {
    "Beginner": "Ask simple, conceptual questions suitable for a beginner. Avoid deep implementation details, keep language plain, and limit answers to basic explanations.",
    "Intermediate": "Ask moderately complex questions that test practical knowledge and some implementation details. Encourage concise, technical answers.",
    "Advanced": "Ask challenging, senior-level questions that require deep technical reasoning, trade-off analysis, and detailed design explanations.",
}

def normalize_difficulty(value: str) -> str:
    """Normalize various difficulty inputs to one of Beginner/Intermediate/Advanced.
    Returns "Intermediate" as default.
    """
    if not value:
        return "Intermediate"
    v = value.strip().lower()
    if v in {"beginner", "entry", "junior", "low"}:
        return "Beginner"
    if v in {"intermediate", "medium", "mid", "average"}:
        return "Intermediate"
    if v in {"advanced", "senior", "expert", "high"}:
        return "Advanced"
    return "Intermediate"



def technical_implementation_role_guidance(role: Optional[str] = None) -> str:
    if (role or "").strip().casefold() != "technical implementation engineer":
        return ""

    return """
ENTRY-LEVEL / FRESHER CANDIDATE GUIDANCE:
- Do not assume professional employment, production ownership, or prior client work.
- Accept well-reasoned hypothetical answers and clearly stated investigation steps.
- Evaluate only skills demonstrated in the answer; do not infer experience or award credit for unsupported claims.
- Accept equivalent correct SQL syntax and approaches.
- Use foundational follow-ups for gaps; increase difficulty through practical multi-step tasks when answers are strong, without requiring senior-level architecture.
- Evaluate technical correctness, SQL logic, API understanding, data analysis, testing, troubleshooting/root-cause reasoning, evidence use, and communication clarity.
- In a live interview, ask exactly one concise question per turn.
"""

def question_bundle_prompt(role: str, difficulty: str, count: int, custom_question: str = "") -> str:
    """Build a prompt for generating a structured interview question bundle.
    Returns a JSON array where each item includes:
        - question (str)
        - difficulty (Beginner|Intermediate|Advanced)
        - model_answer (str)
        - explanation (str)
        - key_points (list[str])
        - common_mistakes (list[str])
    """
    diff_norm = normalize_difficulty(difficulty)
    diff_instr = DIFFICULTY_INSTRUCTIONS.get(diff_norm, DIFFICULTY_INSTRUCTIONS["Intermediate"]).strip()
    seed_instr = f"\nSPECIFIC SEED / FOCUS TOPIC:\n{custom_question.strip()}\n" if custom_question.strip() else ""
    return f"""You are generating an interview question bundle for role: {role}. Difficulty level: {diff_norm} ({diff_instr}). Generate exactly {count} items.
{seed_instr}
Output ONLY a JSON array where each element has the following keys:
- question: string
- difficulty: \"Beginner\"|\"Intermediate\"|\"Advanced\"
- model_answer: string (concise exemplary answer)
- explanation: string (why the question matters and what is being tested)
- key_points: array of strings (important concepts to cover)
- common_mistakes: array of strings (typical pitfalls candidates make)
Do not include any additional text or markdown.
"""



def interview_prompt(data):
    role_str = (data.role or "").strip()
    role_lower = role_str.lower()
    skills_str = ", ".join(data.skills or [])
    exp = data.experience or "3-5 Years"
    diff_raw = data.difficulty or "Medium"
    diff = normalize_difficulty(diff_raw)
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

    difficulty_instruction = DIFFICULTY_INSTRUCTIONS.get(diff, DIFFICULTY_INSTRUCTIONS["Intermediate"])
    format_instruction = f"""
    {difficulty_instruction}
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

    # 5. TECHNICAL IMPLEMENTATION ENGINEER
    elif role_lower == "technical implementation engineer":
        return f"""
You are an interviewer assessing an entry-level / fresher Technical Implementation Engineer ({exp}, Level: {diff}, Skills: {skills_str}).

Generate exactly {num_q} practical, role-specific interview questions.
{seed_instruction}
{technical_implementation_role_guidance(role_str)}
Distribute questions across these entry-level areas, using basic, intermediate, scenario-based, practical, and communication formats:
1. SQL and databases: SELECT, INSERT, UPDATE, DELETE; WHERE, ORDER BY, GROUP BY, HAVING; INNER/LEFT and other JOINs; COUNT, SUM, AVG; filtering, sorting, validation; keys and relationships; query writing/debugging; identify duplicate, missing, inconsistent records and investigate transaction/data discrepancies.
2. REST APIs and Postman: GET, POST, PUT, PATCH, DELETE; status codes; headers, authentication, parameters, request/response bodies; JSON and XML; Postman collections, response validation, HTTP vs HTTPS, client-server communication and API error troubleshooting.
3. Client implementation and integrations: clarify requirements, configure a product, onboard a client, exchange data between applications, validate environments/configuration, integration testing, and coordinate with development/support.
4. Testing and QA: manual and basic automation concepts, test cases/scenarios, positive/negative, boundary and invalid-input tests, API/integration/regression testing, expected vs actual results, defect reports and retesting.
5. Troubleshooting and production support: reproduce an issue, analyze requests/responses, database records, errors/logs and configuration, find likely root cause, prioritize incidents, escalate with evidence, and document resolutions/recurring issues.
6. Communication and documentation: explain findings to clients, record investigation steps, write troubleshooting notes/FAQs, collaborate across teams, prioritize work, and show ownership.

Include practical SQL exercises involving INSERT, JOIN, filtering, aggregation, and data troubleshooting; API response analysis; and scenarios such as a transaction missing from the database, HTTP 200 with failed business outcome, duplicate records, HTTP 401/500, incorrect onboarding configuration, environment-specific test failures, and evidence-based escalation. Questions must remain appropriate for a fresher and allow hypothetical answers.
{format_instruction}
"""

    # 6. BACKEND DEVELOPER
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


def sample_answer_prompt(
    question: str,
    role: str = "",
    skills: Optional[list] = None,
    difficulty: str = "Intermediate"
) -> str:
    """
    Build prompt to generate a high-quality, relevant sample interview answer,
    key evaluation points, and a concise practical example.
    """
    skills_text = ", ".join(skills) if skills else "relevant industry stack"
    diff_norm = normalize_difficulty(difficulty)
    return f"""You are an elite Technical Interview Coach and Staff Interviewer.
Provide an exemplary, high-scoring sample interview response for the following question.

Target Role: {role or "Software Engineer"}
Target Skills: {skills_text}
Difficulty: {diff_norm}
Interview Question: "{question}"

CRITICAL INSTRUCTIONS:
1. "sample_answer": Provide a clear, technically accurate response written in natural, professional spoken English as a candidate would deliver in a top-tier interview.
2. DO NOT invent personal past employment history, specific company names, or exaggerated personal metrics on behalf of the candidate (e.g. do NOT say "At my previous company, I..."). Instead, answer authoritatively using first-principles reasoning, established industry standards, mechanisms, and architectural trade-offs.
3. "key_points": Provide an array of 3 to 4 specific technical concepts, core evaluation criteria, or trade-offs that interviewers look for in a strong response.
4. "practical_example": Provide a concise real-world scenario, architectural pattern, or code/system flow illustrating the approach in practice.

Return ONLY valid JSON matching this schema:
{{
  "sample_answer": "<Direct, articulate interview answer in professional spoken English>",
  "key_points": [
    "<Key concept / technical evaluation criteria 1>",
    "<Key concept / technical evaluation criteria 2>",
    "<Key concept / technical evaluation criteria 3>"
  ],
  "practical_example": "<Concise real-world example or scenario illustrating the solution>"
}}
Do NOT output markdown fences or any text outside the JSON object.
"""
