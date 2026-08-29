-- ==============================================================================
-- Supabase / PostgreSQL Safe Idempotent Schema Migration
-- Table: resume_scans (Phase 5B/5C/5D Resume ↔ JD Match Persistence)
-- Run this script in the Supabase SQL Editor to ensure all columns & indexes exist.
-- ==============================================================================

-- 1. Ensure Table Exists
CREATE TABLE IF NOT EXISTS "resume_scans" (
    "id" SERIAL PRIMARY KEY,
    "scan_id" VARCHAR UNIQUE,
    "user_id" INTEGER REFERENCES "user_accounts"("id") ON DELETE CASCADE,
    "matching_engine_version" VARCHAR DEFAULT 'match-v1.0.0',
    "candidate_name" VARCHAR DEFAULT 'Candidate',
    "target_role" VARCHAR NOT NULL DEFAULT 'General Tech',
    "match_score" DOUBLE PRECISION DEFAULT 80.0,
    "overall_match_score" DOUBLE PRECISION DEFAULT 80.0,
    "match_confidence" VARCHAR DEFAULT 'MEDIUM',
    "sub_scores" TEXT,
    "skill_matrix" TEXT,
    "strengths" TEXT,
    "skill_gaps" TEXT,
    "critical_gaps" TEXT,
    "recommendations" TEXT,
    "normalized_jd" TEXT,
    "normalized_resume" TEXT,
    "matched_skills" TEXT DEFAULT '',
    "missing_skills" TEXT DEFAULT '',
    "source_type" VARCHAR DEFAULT 'paste',
    "source_url" VARCHAR,
    "fetched_at" VARCHAR,
    "created_at" TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    "updated_at" TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
);

-- 2. Safely Add Any Missing Columns (Idempotent for pre-existing tables)
DO $$
BEGIN
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "scan_id" VARCHAR UNIQUE;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "matching_engine_version" VARCHAR DEFAULT 'match-v1.0.0';
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "overall_match_score" DOUBLE PRECISION DEFAULT 80.0;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "match_confidence" VARCHAR DEFAULT 'MEDIUM';
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "sub_scores" TEXT;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "skill_matrix" TEXT;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "strengths" TEXT;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "skill_gaps" TEXT;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "critical_gaps" TEXT;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "recommendations" TEXT;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "normalized_jd" TEXT;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "normalized_resume" TEXT;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "source_type" VARCHAR DEFAULT 'paste';
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "source_url" VARCHAR;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "fetched_at" VARCHAR;
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "created_at" TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc');
    ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc');
END $$;

-- 3. Create Indexes for High-Performance Queries & Tenant Isolation
CREATE INDEX IF NOT EXISTS "ix_resume_scans_scan_id" ON "resume_scans" ("scan_id");
CREATE INDEX IF NOT EXISTS "ix_resume_scans_user_id" ON "resume_scans" ("user_id");
CREATE INDEX IF NOT EXISTS "ix_resume_scans_created_at" ON "resume_scans" ("created_at");
