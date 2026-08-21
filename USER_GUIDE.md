# AI Interview Generator — User Guide & Manual

Welcome to the **AI Interview Question Generator & Mock Studio** documentation. This comprehensive user guide covers everything you need to know about generating tailored, role-specific interview papers, practicing real-time simulations, analyzing resumes, and sharing complete question packages across channels.

---

## 📑 Table of Contents
1. [Overview & Key Features](#1-overview--key-features)
2. [Quick Start Guide](#2-quick-start-guide)
3. [Strict Role-Based Generation](#3-strict-role-based-generation)
4. [Front-Page Real-Time Synthesizer (Dashboard)](#4-front-page-real-time-synthesizer-dashboard)
5. [Deep-Dive Studio & Custom Seed Questions](#5-deep-dive-studio--custom-seed-questions)
6. [Sharing & Exporting Question Packages](#6-sharing--exporting-question-packages)
7. [Mock Interview Simulation & Voice Mode](#7-mock-interview-simulation--voice-mode)
8. [Resume-to-Job Match Analysis](#8-resume-to-job-match-analysis)
9. [Company FAANG Playbooks](#9-company-faang-playbooks)
10. [API & Developer Reference](#10-api--developer-reference)
11. [Troubleshooting & FAQs](#11-troubleshooting--faqs)

---

## 1. Overview & Key Features

The **AI Interview Generator** is an enterprise-grade recruitment and candidate preparation platform powered by Google Gemini 2.5 and FastAPI. 

### Core Capabilities:
- **Strict Role-Based Discipline Intelligence**: Generates 100% relevant questions matching the target job discipline (e.g. UX Design, Product Design, Frontend, Backend, GenAI) with zero generic cross-contamination.
- **Real-Time Word-by-Word Streaming**: Progressive typewriter animations stream questions directly onto the UI with live counter badges.
- **Specific Seed Question Branching**: Input an exact question or case study to automatically branch 5–10 deep-dive scenario, tooling, metric, and edge-case questions.
- **Direct Question Package Sharing**: Share formatted interview packages directly via Email (Gmail, Outlook, Native Mail) and LinkedIn without requiring external links.
- **URL Rehydration & Live QR Codes**: Share interactive papers with self-contained Base64 URL state and scannable mobile QR codes.
- **Role Evaluation Lenses**: Every generated question includes interviewer evaluation criteria and assessment rubrics.
- **Mock Interview Engine**: Interactive voice/text rehearsal simulator with real-time scoring and feedback.

---

## 2. Quick Start Guide

### Prerequisites
- Python 3.10+ installed
- Modern web browser (Chrome, Edge, Firefox, Safari)
- Google Gemini API Key (optional for online AI generation; platform includes rich offline banks)

### Local Launch in 3 Steps:
1. **Clone or Open the Repository**:
   ```bash
   git clone https://github.com/ravidreamview-sketch/AI-interviewgen.git
   cd AI-interviewgen
   ```
2. **Configure Environment Variable**:
   Create a `.env` file from `.env.example`:
   ```bash
   copy .env.example .env
   ```
   Add your Gemini API Key:
   ```env
   GEMINI_API_KEY=your_google_gemini_api_key_here
   ```
3. **Launch the Application**:
   Double click `run_app.bat` or run:
   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   Open your browser to: `http://127.0.0.1:8000/Dashboard.html` or `http://127.0.0.1:8000/index.html`.

---

## 3. Strict Role-Based Generation

The platform enforces strict discipline-specific boundaries to prevent generic HR questions and ensure questions feel like they were written by experienced hiring managers.

### Supported Role Profiles:

| Role | Topics & Domains | Prohibited Topics | Interviewer Persona |
| :--- | :--- | :--- | :--- |
| **🎨 UX Designer** | User research (moderated/unmoderated), usability testing protocols, information architecture, wireframing, interaction design, design systems, WCAG 2.2 accessibility, stakeholder alignment. | ❌ NO coding, software programming, databases, or cloud infrastructure. | Head of UX & Design Research |
| **💡 Product Designer** | Product thinking, UX strategy, user research, product metrics (ARR, retention, conversion, churn, North Star), design systems, PM & Engineering collaboration, problem framing. | ❌ NO software coding/backend syntax. | VP of Product Design |
| **✨ UI/UX Designer** | Visual hierarchy, typography scale, 8pt/4pt spatial grids, design tokens in Figma Variables, micro-interactions, responsive breakpoints, component states. | ❌ NO server architecture or database queries. | Principal UI/UX & Interaction Design Director |
| **⚛️ Frontend Developer** | HTML5 semantics, modern CSS, JS event loop/closures, React 19/Next.js App Router, Core Web Vitals (LCP, INP, CLS), WAI-ARIA accessibility, client/server state management. | Focus on client-side web architecture. | Principal Frontend Architect |
| **⚙️ Backend Developer** | Python, FastAPI, PostgreSQL indexing & ACID transactions, Redis caching, JWT/OAuth2 authentication, distributed scalability, rate limiting, microservices, production debugging. | Focus on server systems & database engineering. | Principal Backend & Systems Architect |
| **🤖 GenAI Engineer** | LLMs, RAG architectures, sparse/dense embeddings, vector databases, LangGraph agentic workflows, hallucination evaluation (Ragas/TruLens), token latency & cost optimization. | Focus on AI systems & LLM engineering. | Chief AI Architect |

---

## 4. Front-Page Real-Time Synthesizer (Dashboard)

The **Dashboard** ([Dashboard.html](file:///e:/Gen%20AI/Project/AI-Interview-Generator/Dashboard.html)) features a live synthesis widget that generates and streams questions without navigating away.

```
+-----------------------------------------------------------------------------------+
|  ⚡ Real-Time AI Question Synthesizer                        [ LIVE ENGINE ]      |
|  [🎨 UX Designer] [💡 Product Designer] [✨ UI/UX] [⚛️ Frontend] [⚙️ Backend] [🤖 GenAI] |
+-----------------------------------------------------------------------------------+
|  Target Role:         Tools & Stack:       Focus Question / Seed:   Difficulty:   |
|  [ UX Designer   v]   [ Figma, Research ]  [ How do you test... ]   [ Hard    v]  |
|                                                                     [⚡ Regenerate]|
+-----------------------------------------------------------------------------------+
|  Q01 | How do you design and execute a mixed-methods user research plan...?       |
|      💡 Interviewer Lens: Validates user research methodology and WCAG accessibility|
|  Q02 | In Figma, how would you architect component variants and variables...?     |
+-----------------------------------------------------------------------------------+
```

### How to Use:
1. Click any **Role Preset Chip** (e.g. `🎨 UX Designer`) or pick a role from the dropdown.
2. The engine **immediately regenerates and streams** questions onto the live card in real time.
3. Use the **📋 Copy All** button to copy the plain text package to your clipboard.
4. Click **✉️ Email Package** to open an email draft with the complete question package pre-filled.
5. Click **Open Full in Studio →** to transition seamlessly to the advanced studio with all inputs preserved.

---

## 5. Deep-Dive Studio & Custom Seed Questions

The **Interview Studio** ([Interview-studio.html](file:///e:/Gen%20AI/Project/AI-Interview-Generator/Interview-studio.html)) gives you full granular control over question creation.

### Step-by-Step Studio Workflow:
1. **Choose a Role**: Select a preset chip or type a custom role.
2. **Specify Experience Level**: Choose from `Intern/Fresher`, `1-2 Years`, `3-5 Years`, `5-8 Years`, or `8+ Years (Staff/Principal)`.
3. **Add Skills & Tools**: Tag specific frameworks, libraries, or methodologies (e.g. `Figma`, `Auto Layout`, `WCAG 2.2`).
4. **Enter a Specific Focus Question (Optional)**:
   - Type or paste an exact seed question (e.g., *"How do you design, prototype, and usability-test a multi-step checkout experience in Figma?"*).
   - Use the **1-Click Inspiration Pills**:
     - `✨ Figma Design Tokens`
     - `✨ Usability Testing Case`
     - `✨ Accessibility & WCAG`
     - `✨ Stakeholder Trade-offs`
5. **Click "Compose interview paper"**:
   - Questions stream progressively into the right-hand panel with active typewriter cursors.
   - Each question includes an interactive copy button and interviewer evaluation lens.

---

## 6. Sharing & Exporting Question Packages

You can share questions across multiple platforms without requiring third-party hosting or complex URLs.

### 1. Direct Question Package Sharing (Plain Text)
- **Email Sharing**:
  - Click **✉️ Email Package** in the studio or dashboard.
  - Choose your preferred email client:
    - **Gmail Web**: Opens compose in mail.google.com with subject and body populated.
    - **Outlook Web**: Opens compose in outlook.office.com with subject and body populated.
    - **Default Mail App**: Launches your OS mail client (Apple Mail, Thunderbird, Windows Mail).
- **LinkedIn Sharing**:
  - Click **💼 LinkedIn** to launch a formatted post draft highlighting the role, difficulty, questions, and evaluation lenses.

### 2. Interactive URL Sharing & QR Codes
- Click **🔗 Share / Export** in the top action bar:
  - **Live URL**: Generates a shareable URL containing the complete interview payload encoded in Base64 (zero server storage required).
  - **Live QR Code**: Generates a high-contrast QR code for instant mobile access.
  - **Markdown Export**: Formats the paper into clean GitHub-flavored markdown for documentation.
  - **JSON Export**: Downloads the structured schema for ATS or LMS integrations.

---

## 7. Mock Interview Simulation & Voice Mode

Practice or conduct live candidate evaluations with the **Mock Interview Engine** ([Mock-interview.html](file:///e:/Gen%20AI/Project/AI-Interview-Generator/Mock-interview.html)).

### Features:
- **Interactive Question Progression**: Step through questions one by one with live timer countdowns.
- **Voice Response Mode**: Speak candidate answers using browser Speech-to-Text (`webkitSpeechRecognition`).
- **Real-Time Rubric Scoring**: AI evaluates answers on **Clarity (25%)**, **Technical Depth (35%)**, **Practical Execution (25%)**, and **Communication (15%)**.
- **Final Performance Scorecard**: Provides a composite score (out of 100) with key strengths and improvement areas.

---

## 8. Resume-to-Job Match Analysis

The **Resume Matcher** ([Resume-match.html](file:///e:/Gen%20AI/Project/AI-Interview-Generator/Resume-match.html)) compares a candidate's resume against a target job description.

### How to Use:
1. Paste the candidate's resume text or upload a PDF/DOCX.
2. Paste the target Job Description (JD).
3. Click **"Analyze Match & Generate Questions"**.
4. The system calculates:
   - **Match Percentage** (e.g. `87% Match`)
   - **Identified Skill Gaps**
   - **Tailored Target Questions**: Specifically targeting missing or ambiguous skills found in the gap analysis.

---

## 9. Company FAANG Playbooks

The **Company Playbooks** section ([Company-playbooks.html](file:///e:/Gen%20AI/Project/AI-Interview-Generator/Company-playbooks.html)) provides curated interview frameworks for top tech firms:

- **Google**: Focuses on Googleyness, algorithmic complexity, system scalability, and structured problem solving.
- **Meta**: Focuses on rapid execution, product sense, system architecture, and behavioral leadership.
- **Amazon**: Evaluates against the 16 Leadership Principles (Customer Obsession, Ownership, Bias for Action) with STAR method scoring.
- **Apple**: Focuses on deep hardware/software integration, extreme attention to visual detail, and craftsmanship.
- **Netflix**: Focuses on the Culture of Freedom & Responsibility, high-context decision making, and architectural autonomy.

---

## 10. API & Developer Reference

The backend exposes a lightweight REST API built with FastAPI.

### Endpoints:

#### 1. Generate Interview Questions
`POST /generate`

**Request Body:**
```json
{
  "role": "Senior UX Designer",
  "experience": "5 Years",
  "skills": ["User Research", "Figma", "Design Systems", "WCAG 2.2"],
  "difficulty": "Hard",
  "number_of_questions": 5,
  "custom_question": "How do you conduct usability testing on an e-commerce checkout flow?"
}
```

**Response:**
```json
{
  "id": 42,
  "role": "Senior UX Designer",
  "difficulty": "Hard",
  "questions": [
    "How do you design and execute a mixed-methods user research plan for an ambiguous feature definition?",
    "In Figma, how would you architect wireframes and Auto Layout constraints for a multi-step checkout?",
    "What usability friction points and WCAG 2.2 AA accessibility constraints must be accounted for?",
    "How would you design a usability testing protocol to validate checkout drop-off reduction?",
    "How do you defend your UX decisions when engineering raises performance trade-offs?"
  ],
  "created_at": "2026-08-21T08:30:00"
}
```

#### 2. Get Interview History
`GET /history`
Returns a list of previously generated interview papers stored in the local SQLite database (`interview.db`).

#### 3. Get Single Interview Paper
`GET /history/{id}`
Returns details and questions for a specific interview paper by ID.

---

## 11. Troubleshooting & FAQs

### Q: Why do I see offline questions instead of Gemini AI generation?
**A**: Ensure your `.env` file contains a valid `GEMINI_API_KEY` and the FastAPI server is running (`http://127.0.0.1:8000`). If no API key is provided, the platform automatically utilizes its high-yield role banks to ensure uninterrupted operation.

### Q: Why does changing the role on the Dashboard regenerate questions?
**A**: The front-page synthesizer is designed for instant exploration. Switching roles (e.g. from `UX Designer` to `Backend Developer`) automatically triggers real-time streaming for the newly selected role.

### Q: Can I share questions with someone who doesn't have an account or local server?
**A**: Yes! Click **✉️ Email Package** or **💼 LinkedIn** to send the raw question package directly. Alternatively, copy the **Share Link** from the share modal, which embeds the entire paper into a self-contained URL.

### Q: Can I export questions to PDF or Markdown?
**A**: Yes. In the Interview Studio, click **Print / PDF** to use the browser print dialog with print-optimized CSS, or click **Markdown** in the share modal to copy GitHub-formatted markdown.

---

*Document Version: 2.5.0 | Last Updated: August 2026*
