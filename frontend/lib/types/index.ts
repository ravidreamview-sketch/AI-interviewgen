export interface UserAccount {
  id: number;
  email: string;
  full_name?: string;
  role: string;
  plan_tier: string;
  is_active: boolean;
}

export interface AssessedSkill {
  skill: string;
  score: number;
  level: number;
  level_title: string;
  confidence: string;
  trend: string;
  weakness_status: string;
}

export interface SelfReportedSkill {
  level: number;
  level_title: string;
  baseline_score: number;
  notes?: string;
  reported_at?: string;
}

export interface LearnerProfile {
  id: number;
  user_id: number;
  email: string;
  full_name?: string;
  target_role: string;
  secondary_roles: string[];
  career_goals?: string;
  target_level: string;
  education_level?: string;
  institution?: string;
  graduation_year?: number;
  years_of_experience: number;
  current_role?: string;
  current_company?: string;
  preferred_learning_goals: string[];
  career_interests: string[];
  self_reported_skills: Record<string, SelfReportedSkill>;
  assessed_skills: AssessedSkill[];
  latest_scan_id?: string;
  created_at: string;
  updated_at: string;
}

export interface CompetencyItem {
  skill: string;
  category: string;
  target_level: number;
  target_level_title: string;
  role_criticality: number;
  description: string;
}

export interface SkillGap {
  skill: string;
  category: string;
  description: string;
  target_level: number;
  target_level_title: string;
  current_level: number;
  current_level_title: string;
  current_score: number;
  gap_level: number;
  priority: "CRITICAL" | "HIGH" | "MODERATE" | "LOW" | "ON_TRACK";
  evidence_type: "VERIFIED" | "ASSESSED" | "SELF_REPORTED" | "NOT_EVIDENCED";
  confidence: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  is_verified: boolean;
  evidence_count: number;
  last_evaluated?: string;
}

export interface ResumeSyncResult {
  success: boolean;
  scan_id: string;
  target_role: string;
  match_score: number;
  extracted_skills: string[];
  years_of_experience: number;
  education?: string;
  message: string;
}

export interface LearningActivity {
  id: string;
  title: string;
  description: string;
  activity_type: "interactive_concept" | "code_exercise" | "system_design_challenge" | "architecture_review" | "knowledge_check";
  estimated_minutes: number;
  status: "pending" | "in_progress" | "completed";
  completed_at?: string;
  score?: number;
  external_resources: Array<{ title: string; url: string; type: string }>;
}

export interface LearningMilestone {
  id: string;
  title: string;
  criteria: string;
  milestone_type: "checkpoint_quiz" | "mock_scenario" | "project_verification";
  status: "pending" | "unlocked" | "passed";
  score?: number;
  passed_at?: string;
}

export interface LearningModule {
  id: string;
  sequence_index: number;
  title: string;
  description: string;
  targeted_skills: string[];
  target_level: number;
  target_level_title: string;
  gap_priority: "CRITICAL" | "HIGH" | "MODERATE" | "LOW" | "ON_TRACK";
  estimated_hours: number;
  prerequisites: string[];
  activities: LearningActivity[];
  milestone: LearningMilestone;
  status: "locked" | "available" | "in_progress" | "completed";
  progress_percentage: number;
}

export interface AdaptiveRoadmapData {
  roadmap_id: string;
  title: string;
  target_role: string;
  target_level: string;
  rationale: string;
  total_estimated_hours: number;
  modules: LearningModule[];
  overall_progress: number;
  last_adapted_at: string;
  adaptation_reason?: string;
}

export interface NextRecommendationResponse {
  current_activity: LearningActivity | null;
  current_module: {
    id: string;
    title: string;
    gap_priority: string;
    targeted_skills: string[];
    progress_percentage: number;
  } | null;
  upcoming_queue: Array<{
    id: string;
    title: string;
    module_title: string;
    activity_type: string;
    estimated_minutes: number;
  }>;
  overall_progress: number;
}

export interface TutorMessageItem {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  code_snippet?: string;
  pedagogical_intent?: string;
  created_at: string;
}

export interface TutorSessionItem {
  session_id: string;
  concept: string;
  teaching_mode: "explain" | "demonstrate" | "hint" | "challenge" | "solution";
  complexity_level: "simple" | "standard" | "deep_dive";
  activity_id?: string;
  roadmap_id?: string;
  title?: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface TutorResponse {
  session_id: string;
  concept: string;
  teaching_mode: string;
  complexity_level: string;
  message: string;
  pedagogical_intent: string;
  activity_id?: string;
  created_at: string;
}

export interface ScenarioDetail {
  scenario_id: string;
  title: string;
  category: string;
  domain: string;
  target_role: string;
  difficulty: string;
  difficulty_level: number;
  context: string;
  problem_statement: string;
  required_skills: string[];
  objectives: string[];
  instructions: string[];
  constraints: string[];
  deliverables: string[];
  rubric: Record<string, { weight: number; description: string; target_expectations: string }>;
  success_criteria: string[];
  hints: string[];
  is_completed: boolean;
  created_at: string;
}

export interface SubmissionEvaluation {
  submission_id: string;
  scenario_id: string;
  status: "passed" | "revision_needed";
  overall_score: number;
  dimension_scores: Record<string, number>;
  strengths: string[];
  areas_for_improvement: string[];
  evidence: string;
  feedback: string;
  recommended_next_steps: string[];
  evaluation_disclaimer: string;
  evaluated_at: string;
}

export interface ProjectItem {
  project_id: string;
  title: string;
  target_role: string;
  domain: string;
  description: string;
  architecture_overview?: string;
  tech_stack: string[];
  status: "planning" | "in_development" | "review_ready" | "completed";
  created_at: string;
  updated_at: string;
}

export interface ProjectMentorshipTurn {
  id: number;
  project_id: string;
  mentorship_stage: string;
  user_query: string;
  mentor_guidance: string;
  action_items: string[];
  created_at: string;
}

export interface InterviewHistoryItem {
  interview_id: string;
  role: string;
  company_target: string;
  interviewer_persona: string;
  score: number;
  technical_accuracy: number;
  communication_clarity: number;
  star_depth: number;
  status: string;
  created_at?: string;
}

// =============================================================================
// PHASE 6: COMPETENCY INTELLIGENCE & CAREER READINESS
// =============================================================================

export interface CompetencyTier {
  level: number;
  name: string;
  score: number;
  desc: string;
}

export interface SkillEvidenceSources {
  self_reported?: {
    claimed_level?: string;
    estimated_score?: number;
    years?: number;
    source?: string;
  } | null;
  assessed?: {
    score?: number;
    confidence?: string;
    evidence_count?: number;
    weakness_status?: string;
  } | null;
  scenario?: Array<{
    submission_id: string;
    scenario_title: string;
    score: number;
    status: string;
    evaluated_at?: string;
  }> | null;
  interview?: {
    completed_interviews_count: number;
    average_score: number;
  } | null;
  project?: Array<{
    project_id: string;
    title: string;
    status: string;
    mentorship_turns_count: number;
    stages_engaged: string[];
  }> | null;
}

export interface SkillCompetencyItem {
  skill_name: string;
  overall_score: number;
  competency_tier: CompetencyTier;
  verification_status: "multi_source_verified" | "assessed" | "self_reported";
  trend: "improving" | "steady" | "declining" | "insufficient_data";
  open_mistakes_count: number;
  evidence_sources: SkillEvidenceSources;
}

export interface RoleBenchmarkGap {
  skill: string;
  category: string;
  target_benchmark_score: number;
  candidate_score: number;
  gap_delta: number;
  status: "met" | "near_benchmark" | "critical_gap" | "missing_evidence";
  has_empirical_evidence: boolean;
}

export interface CareerReadinessAssessment {
  readiness_index: number;
  readiness_tier: string;
  target_role: string;
  target_level: string;
  overall_coverage_pct: number;
  evidence_coverage: {
    profile_completed: boolean;
    assessed_skills_count: number;
    scenarios_evaluated_count: number;
    interviews_completed_count: number;
    projects_mentored_count: number;
    roadmap_progress_pct: number;
  };
  missing_evidence: string[];
  contributing_factors: {
    positive: string[];
    risk_areas: string[];
  };
  readiness_disclaimer: string;
}

export interface ActionableRecommendations {
  skills_to_improve: string[];
  learning_activities: Array<{
    title: string;
    activity_id: string;
    roadmap_id: string;
    skill: string;
    action_url: string;
  }>;
  scenarios: Array<{
    scenario_id: string;
    title: string;
    category: string;
    difficulty: string;
    target_role: string;
    action_url: string;
  }>;
  projects: Array<{
    project_id: string;
    title: string;
    stage: string;
    focus: string;
    action_url: string;
  }>;
  interview_practice: {
    role: string;
    interview_type: string;
    persona: string;
    recommended_focus: string;
    action_url: string;
  };
}

export interface CompetencyDashboardData {
  readiness: CareerReadinessAssessment;
  role_gaps: RoleBenchmarkGap[];
  skills: SkillCompetencyItem[];
  skills_improving: string[];
  skills_requiring_improvement: string[];
  assessment_history: Array<{
    skill: string;
    score: number;
    trend: string;
    confidence: string;
    weakness_status: string;
    last_updated?: string;
  }>;
  scenario_evidence: Array<{
    submission_id: string;
    scenario_id: string;
    scenario_title: string;
    overall_score: number;
    status: string;
    evaluated_at?: string;
  }>;
  interview_evidence: Array<{
    interview_id: string;
    role: string;
    interviewer_persona: string;
    score: number;
    technical_accuracy: number;
    communication_clarity: number;
    star_depth: number;
    status: string;
    created_at?: string;
  }>;
  project_evidence: Array<{
    project_id: string;
    title: string;
    domain: string;
    status: string;
    mentorship_turns_count: number;
    stages_engaged: string[];
  }>;
  learning_progress: {
    has_active_roadmap: boolean;
    roadmap_id?: string;
    roadmap_title?: string;
    overall_progress_pct: number;
    completed_activities_count: number;
    total_activities_count: number;
    tutor_sessions_count: number;
  };
  recommendations: ActionableRecommendations;
}

// ==============================================================================
// CANDIDATE ONBOARDING & RESUME ASSESSMENT TYPES
// ==============================================================================

export interface CandidateSkillEntry {
  skill: string;
  category?: string;
  proficiency: "Beginner" | "Basic" | "Intermediate" | "Advanced" | "Expert";
  source?: "SELF_REPORTED" | "RESUME_EXTRACTED";
  notes?: string;
}

export interface EvaluatedSkill {
  skill: string;
  category: string;
  description: string;
  required_level: number;
  required_level_title: string;
  candidate_level: number;
  candidate_level_title: string;
  candidate_score: number;
  status: "Matched" | "Partial Match" | "Gap" | "Not Assessed" | "Needs Verification";
  source: string;
  confidence: string;
  is_verified: boolean;
  role_criticality: number;
}

export interface OnboardingAssessmentResponse {
  target_role: string;
  target_level: string;
  overall_match_percentage: number;
  skills_identified_count: number;
  skills_matched_count: number;
  skills_partial_count: number;
  skills_gap_count: number;
  skills_not_assessed_count: number;
  readiness_status: "Foundation Required" | "Developing" | "Job-Ready Progress" | "Strong Role Alignment";
  readiness_description: string;
  experience_alignment: string;
  experience_description: string;
  education_alignment: string;
  evaluated_skills: EvaluatedSkill[];
  additional_skills: EvaluatedSkill[];
  categories: Record<string, EvaluatedSkill[]>;
  recommended_areas: Array<{
    skill: string;
    category: string;
    status: string;
    required_level: string;
    description: string;
    priority: "CRITICAL" | "HIGH" | "MODERATE" | "LOW";
  }>;
  disclaimer: string;
}

export interface ResumeExtractedSkillItem {
  skill: string;
  category: string;
  proficiency: "Beginner" | "Basic" | "Intermediate" | "Advanced" | "Expert";
  source: "RESUME_EXTRACTED";
}

export interface WorkExperienceEntry {
  company: string;
  role: string;
  duration?: string;
  description?: string;
  technologies?: string[];
}

export interface ProjectEntry {
  name: string;
  description?: string;
  technologies?: string[];
}

export interface ResumeUploadExtractResponse {
  success: boolean;
  message: string;
  filename: string;
  file_size_bytes: number;
  candidate_name?: string;
  email?: string;
  phone?: string;
  summary?: string;
  years_of_experience: number;
  education?: string;
  institution?: string;
  graduation_year?: number;
  current_role?: string;
  current_company?: string;
  work_experience?: WorkExperienceEntry[];
  projects_detail?: ProjectEntry[];
  skills: ResumeExtractedSkillItem[];
  technical_skills: string[];
  soft_skills: string[];
  tools_and_technologies: string[];
  projects: string[];
  certifications: string[];
  raw_text?: string;
}

export interface CompleteOnboardingRequest {
  full_name?: string;
  email?: string;
  phone?: string;
  summary?: string;
  education_level?: string;
  institution?: string;
  graduation_year?: number;
  target_role: string;
  target_level: string;
  years_of_experience: number;
  current_role?: string;
  current_company?: string;
  work_experience?: WorkExperienceEntry[];
  projects?: ProjectEntry[];
  certifications?: string[];
  career_goals?: string;
  target_industry?: string;
  preferred_learning_goals?: string[];
  skills: CandidateSkillEntry[];
  raw_resume_text?: string;
  resume_filename?: string;
}

export interface CompleteOnboardingResponse {
  success: boolean;
  message: string;
  profile_id: number;
  user_id: number;
  full_name: string;
  target_role: string;
  target_level: string;
  overall_match_score: number;
  readiness_status: string;
  roadmap_id?: string;
  top_matched_skills: string[];
  top_skill_gaps: string[];
  next_action: string;
  assessment?: OnboardingAssessmentResponse;
  submitted_profile?: {
    full_name: string;
    email: string;
    phone?: string;
    summary?: string;
    education_level?: string;
    institution?: string;
    graduation_year?: number;
    current_role?: string;
    current_company?: string;
    years_of_experience: number;
    target_role: string;
    target_level: string;
    skills: CandidateSkillEntry[];
    work_experience?: WorkExperienceEntry[];
    projects?: ProjectEntry[];
    certifications?: string[];
  };
}

// ==============================================================================
// RESUME & ATS MATCH SCHEMAS
// ==============================================================================

export interface ResumeSubScores {
  required_skills?: number;
  experience?: number;
  domain?: number;
  responsibilities?: number;
  preferred_skills?: number;
  tools_technology?: number;
  education?: number;
}

export interface ResumeSkillMatrixItem {
  skill: string;
  importance: "HIGH" | "MEDIUM" | "LOW";
  jd_requirement: string;
  resume_evidence?: string | null;
  evidence_level: number;
  evidence_strength: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  match_score: number;
  gap_status: "matched" | "partial" | "gap";
}

export interface ResumeJDMatchRequest {
  resume_text?: string;
  jd_text?: string;
  jd_url?: string;
  target_role?: string;
  source_type?: string;
}

export interface ResumeJDMatchResponse {
  scan_id: string;
  matching_engine_version: string;
  overall_match_score: number;
  match_confidence: "HIGH" | "MEDIUM" | "LOW";
  sub_scores: ResumeSubScores;
  skill_matrix: ResumeSkillMatrixItem[];
  strengths: string[];
  skill_gaps: string[];
  critical_gaps: string[];
  recommendations: string[];
  target_role: string;
  candidate_name?: string;
  source_type: string;
  source_url?: string;
  evaluation_fingerprint?: string;
  is_cached?: boolean;
  career_improvement_plan?: Record<string, any>;
  created_at: string;
}





