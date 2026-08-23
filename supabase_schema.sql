-- ==============================================================================
-- RAVI GENAI STUDIO — SUPABASE REAL-TIME DATABASE SCHEMA
-- Execute this script in your Supabase SQL Editor (https://app.supabase.com)
-- ==============================================================================

-- 1. CREATE EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. CREATE TABLE: interview_papers (Generated Question Sets)
CREATE TABLE IF NOT EXISTS public.interview_papers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role TEXT NOT NULL,
    experience TEXT NOT NULL DEFAULT '3-5 Years',
    difficulty TEXT NOT NULL DEFAULT 'Hard',
    skills TEXT[] NOT NULL DEFAULT '{}',
    questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    count INTEGER NOT NULL DEFAULT 5,
    custom_question TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE
);

-- 3. CREATE TABLE: mock_interviews (Live Voice Simulations & Scorecards)
CREATE TABLE IF NOT EXISTS public.mock_interviews (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    role TEXT NOT NULL,
    company_target TEXT DEFAULT 'FAANG Tier',
    interviewer_persona TEXT NOT NULL DEFAULT 'Alex (Tech Lead)',
    score NUMERIC(5,2) NOT NULL DEFAULT 88.00,
    technical_accuracy NUMERIC(5,2) DEFAULT 92.00,
    communication_clarity NUMERIC(5,2) DEFAULT 88.00,
    star_depth NUMERIC(5,2) DEFAULT 90.00,
    confidence_score NUMERIC(5,2) DEFAULT 87.00,
    duration_seconds INTEGER DEFAULT 300,
    transcript JSONB DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE
);

-- 4. CREATE TABLE: resume_scans (ATS & JD Match Analyses)
CREATE TABLE IF NOT EXISTS public.resume_scans (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_name TEXT DEFAULT 'Ravi Chandran',
    target_role TEXT NOT NULL,
    match_score NUMERIC(5,2) NOT NULL DEFAULT 84.00,
    matched_skills TEXT[] NOT NULL DEFAULT '{}',
    missing_skills TEXT[] NOT NULL DEFAULT '{}',
    gap_questions JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE
);

-- ==============================================================================
-- 5. ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================
ALTER TABLE public.interview_papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mock_interviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resume_scans ENABLE ROW LEVEL SECURITY;

-- Allow public read access (for portfolio/demo/dashboard views)
CREATE POLICY "Allow public read on interview_papers" ON public.interview_papers FOR SELECT USING (true);
CREATE POLICY "Allow public insert on interview_papers" ON public.interview_papers FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow public update on interview_papers" ON public.interview_papers FOR UPDATE USING (true);
CREATE POLICY "Allow public delete on interview_papers" ON public.interview_papers FOR DELETE USING (true);

CREATE POLICY "Allow public read on mock_interviews" ON public.mock_interviews FOR SELECT USING (true);
CREATE POLICY "Allow public insert on mock_interviews" ON public.mock_interviews FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public read on resume_scans" ON public.resume_scans FOR SELECT USING (true);
CREATE POLICY "Allow public insert on resume_scans" ON public.resume_scans FOR INSERT WITH CHECK (true);

-- ==============================================================================
-- 6. ENABLE REAL-TIME WEBSOCKET BROADCASTING (SUPABASE REALTIME)
-- ==============================================================================
-- Add tables to the supabase_realtime publication to stream live INSERT/UPDATE/DELETE events
BEGIN;
  DROP PUBLICATION IF EXISTS supabase_realtime;
  CREATE PUBLICATION supabase_realtime;
COMMIT;

ALTER PUBLICATION supabase_realtime ADD TABLE public.interview_papers;
ALTER PUBLICATION supabase_realtime ADD TABLE public.mock_interviews;
ALTER PUBLICATION supabase_realtime ADD TABLE public.resume_scans;

-- Set replica identity to FULL so listeners receive complete old/new payloads
ALTER TABLE public.interview_papers REPLICA IDENTITY FULL;
ALTER TABLE public.mock_interviews REPLICA IDENTITY FULL;
ALTER TABLE public.resume_scans REPLICA IDENTITY FULL;

-- ==============================================================================
-- 7. PERFORMANCE INDEXES
-- ==============================================================================
CREATE INDEX IF NOT EXISTS idx_interview_papers_created_at ON public.interview_papers (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interview_papers_role ON public.interview_papers (role);
CREATE INDEX IF NOT EXISTS idx_mock_interviews_created_at ON public.mock_interviews (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_resume_scans_created_at ON public.resume_scans (created_at DESC);

-- ==============================================================================
-- 8. SEED STARTER LIVE DEMO DATA
-- ==============================================================================
INSERT INTO public.interview_papers (role, experience, difficulty, skills, questions, count, custom_question, created_at)
VALUES
(
  'Senior UX Designer',
  '5 Years',
  'Hard',
  ARRAY['Figma', 'Design Systems', 'User Research', 'WCAG 2.2', 'Usability Testing'],
  '[
    "How do you establish typographic scale, 8pt spatial grid, and color contrast tokens in Figma Variables for a multi-brand design system?",
    "Describe your methodology for conducting unmoderated remote usability testing on an interactive Figma checkout prototype to isolate friction points.",
    "How do you evaluate and defend WCAG 2.2 Level AA accessibility compliance against aggressive marketing aesthetics or engineering deadline cuts?",
    "Explain how you architect component variants, boolean properties, and nested instances to maximize reuse across distributed cross-functional squads.",
    "Scenario: Post-launch analytics indicate a 35% abandonment rate at step 2 of an onboarding wizard. Walk through your systematic diagnostic and iteration plan."
  ]'::jsonb,
  5,
  'How do you conduct usability testing on a Figma prototype for an e-commerce checkout flow?',
  NOW() - INTERVAL '15 minutes'
),
(
  'Product Designer',
  '5 Years',
  'Hard',
  ARRAY['Product Strategy', 'UX Discovery', 'Conversion Optimization', 'Figma'],
  '[
    "How do you balance aggressive business conversion targets with customer friction when redesigning a SaaS subscription upgrade flow?",
    "Describe how you define North Star product metrics and secondary guardrail indicators before launching a core feature redesign.",
    "Walk through how you would facilitate an MVP scoping workshop with cross-functional PM and Engineering leads."
  ]'::jsonb,
  3,
  'How do you balance business conversion goals with user friction in a subscription upgrade flow?',
  NOW() - INTERVAL '2 hours'
),
(
  'Staff Frontend Developer',
  '8+ Years',
  'Brutal',
  ARRAY['React 19', 'Next.js App Router', 'TypeScript', 'Performance', 'a11y'],
  '[
    "Explain how you architect Server Components vs Client Components in React 19 / Next.js to minimize client bundle size and optimize TTFB.",
    "How do you diagnose and eliminate long tasks and Interaction to Next Paint (INP) bottlenecks using Chrome DevTools Performance Profiler?",
    "Describe your strategy for state orchestration: when do you use URL search params, React Context, TanStack Query, and Zustand?"
  ]'::jsonb,
  3,
  'How do you optimize Core Web Vitals (LCP, INP, CLS) in a large-scale React/Next.js application?',
  NOW() - INTERVAL '1 day'
),
(
  'GenAI & RAG Systems Engineer',
  '5 Years',
  'Hard',
  ARRAY['LLMs', 'RAG Architecture', 'Vector DBs', 'LangGraph', 'Hallucination Evaluation'],
  '[
    "How do you architect an enterprise hybrid vector search pipeline combining dense embeddings (text-embedding-3-large) and BM25 sparse lexical search?",
    "Describe how you evaluate retrieval precision, context recall, and hallucination rates in production using Ragas and DeepEval.",
    "How do you enforce document-level Access Control Lists (ACLs) and tenant metadata filtering in Pinecone/Milvus retrieval pipelines?"
  ]'::jsonb,
  3,
  'How do you architect a multi-tenant enterprise RAG pipeline with hybrid search and strict document access control?',
  NOW() - INTERVAL '2 days'
);

INSERT INTO public.mock_interviews (role, company_target, interviewer_persona, score, technical_accuracy, communication_clarity, star_depth, confidence_score, duration_seconds, created_at)
VALUES
('Python Backend Engineer', 'Amazon (Leadership Principles)', 'Alex (Tech Lead)', 89.00, 92.00, 88.00, 90.00, 87.00, 312, NOW() - INTERVAL '3 hours'),
('Senior UX Designer', 'Google (GCA & Googleyness)', 'Elena (Principal Architect)', 94.00, 96.00, 92.00, 94.00, 93.00, 280, NOW() - INTERVAL '1 day'),
('Staff Frontend Engineer', 'Meta (Execution & Scale)', 'Marcus (Hiring Manager)', 87.00, 90.00, 85.00, 88.00, 86.00, 340, NOW() - INTERVAL '3 days');

INSERT INTO public.resume_scans (candidate_name, target_role, match_score, matched_skills, missing_skills, created_at)
VALUES
('Ravi Chandran', 'Senior Backend Engineer', 84.00, ARRAY['Python', 'FastAPI', 'PostgreSQL', 'Redis', 'Docker'], ARRAY['Kafka', 'Kubernetes'], NOW() - INTERVAL '5 hours'),
('Ravi Chandran', 'Senior Product Designer', 91.00, ARRAY['Figma', 'User Research', 'Design Systems', 'Prototyping'], ARRAY['SQL Telemetry'], NOW() - INTERVAL '2 days');
