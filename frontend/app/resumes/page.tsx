"use client";

import React, { useState, useRef } from "react";
import Link from "next/link";
import { Card, CardHeader, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { apiClient } from "@/lib/api/client";
import {
  ResumeUploadExtractResponse,
  ResumeJDMatchResponse,
  ResumeJDMatchRequest,
  ResumeSkillMatrixItem,
} from "@/lib/types";
import {
  FileText,
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Sparkles,
  ArrowRight,
  RotateCcw,
  Briefcase,
  Layers,
  Target,
  Trash2,
  Check,
  AlertCircle,
  FileCheck,
  ExternalLink,
} from "lucide-react";

const SAMPLE_JD_PRESETS = [
  {
    title: "Senior Full-Stack Engineer",
    jd: `Role: Senior Full-Stack Engineer
Company: CloudScale Technologies
Required Skills: React, Next.js, TypeScript, Python, FastAPI, PostgreSQL, Docker, REST APIs
Preferred Skills: Kubernetes, Redis, GraphQL, Tailwind CSS, CI/CD pipelines
Domain: Distributed Web Applications, High-Throughput APIs
Experience: Minimum 4+ years building production web systems.
Responsibilities:
- Architect and maintain full-stack web applications using React/Next.js and FastAPI.
- Design database schemas and optimize PostgreSQL queries for latency.
- Implement robust authentication, authorization, and API security.
- Collaborate with product teams and conduct code reviews.`,
  },
  {
    title: "Backend Platform Engineer",
    jd: `Role: Backend Platform Engineer
Company: Nexus Data Systems
Required Skills: Python, FastAPI, PostgreSQL, SQLAlchemy, Docker, AsyncIO, Pytest
Preferred Skills: Kafka, Redis, Microservices architecture, Google Cloud Platform (GCP)
Domain: Backend infrastructure, Event-Driven Architecture
Experience: 3+ years of professional backend engineering.
Responsibilities:
- Build reliable microservices and asynchronous task pipelines in Python.
- Maintain high test coverage using Pytest and automated CI/CD.
- Ensure strict database connection pooling and zero data corruption.`,
  },
];

const SAMPLE_RESUME_TEXT = `Ravi Kumar — Senior Full-Stack Engineer
Email: ravi.kumar@example.com | Location: Bangalore, India
LinkedIn: linkedin.com/in/ravikumar | GitHub: github.com/ravikumar

SUMMARY
Senior Software Engineer with 5+ years of experience designing, developing, and deploying resilient web applications and microservices. Expert in TypeScript, React, Next.js, Python, FastAPI, and PostgreSQL. Proven track record optimizing high-throughput distributed architectures.

TECHNICAL SKILLS
Languages: Python, TypeScript, JavaScript, SQL, HTML5, CSS3
Frameworks & Libraries: FastAPI, Next.js, React, Node.js, Tailwind CSS, SQLAlchemy, Pydantic
Databases: PostgreSQL, SQLite, Redis
DevOps & Cloud: Docker, Kubernetes, Git, CI/CD (GitHub Actions), Google Cloud Platform (GCP)
Testing: Pytest, Jest, Integration Testing

WORK EXPERIENCE
Senior Full-Stack Developer | CloudTech Solutions (2022 - Present)
- Architected and deployed microservices backend using FastAPI and PostgreSQL handling 2M+ daily requests with <80ms p95 latency.
- Built responsive client dashboard with Next.js 14, React, and TypeScript, improving user retention by 35%.
- Implemented robust JWT authentication, role-based access control (RBAC), and automated database migrations using Alembic.
- Containerized applications using Docker and orchestrated deployments on Google Cloud Run.

Full-Stack Software Engineer | DataCraft Labs (2019 - 2022)
- Developed RESTful APIs and real-time data pipelines using Python, FastAPI, and PostgreSQL.
- Built accessible frontend user interfaces with React, TypeScript, and modern CSS.
- Authored comprehensive test suites in Pytest achieving 92% code coverage across core business logic.

EDUCATION
Bachelor of Technology in Computer Science & Engineering (2015 - 2019)`;

export default function ResumeMatchPage() {
  // Input states
  const [targetRole, setTargetRole] = useState("Senior Full-Stack Engineer");
  const [jdText, setJdText] = useState(SAMPLE_JD_PRESETS[0].jd);
  const [resumeText, setResumeText] = useState("");
  
  // File upload states
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "parsed" | "error">("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [extractedInfo, setExtractedInfo] = useState<ResumeUploadExtractResponse | null>(null);
  
  // Analysis execution states
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [matchResult, setMatchResult] = useState<ResumeJDMatchResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "matrix" | "recommendations">("overview");

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Handle resume file upload
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate extension
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (![".pdf", ".docx", ".doc", ".txt"].includes(ext)) {
      setUploadError("Unsupported format. Please upload a PDF, DOCX, or TXT file.");
      return;
    }

    // Validate size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      setUploadError("File exceeds 5MB size limit. Please upload a smaller document.");
      return;
    }

    setUploadedFile(file);
    setUploadStatus("uploading");
    setUploadError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await apiClient<ResumeUploadExtractResponse>("/api/v1/learners/upload-resume", {
        method: "POST",
        body: formData,
      });

      if (res.success && res.raw_text) {
        setExtractedInfo(res);
        setResumeText(res.raw_text);
        if (res.current_role && !targetRole) {
          setTargetRole(res.current_role);
        }
        setUploadStatus("parsed");
      } else {
        throw new Error(res.message || "Failed to extract text from resume");
      }
    } catch (err: any) {
      console.error("Resume extraction failed:", err);
      setUploadStatus("error");
      setUploadError(err.message || "Failed to parse resume document. You can paste your resume text directly.");
    }
  };

  const handleRemoveFile = () => {
    setUploadedFile(null);
    setUploadStatus("idle");
    setExtractedInfo(null);
    setUploadError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleLoadSampleResume = () => {
    setResumeText(SAMPLE_RESUME_TEXT);
    setUploadStatus("parsed");
    setUploadedFile(null);
    setExtractedInfo(null);
    setUploadError(null);
  };

  const handleSelectPreset = (preset: typeof SAMPLE_JD_PRESETS[0]) => {
    setTargetRole(preset.title);
    setJdText(preset.jd);
  };

  // Run ATS Match analysis
  const handleAnalyzeMatch = async () => {
    const trimmedResume = resumeText.trim();
    const trimmedJd = jdText.trim();

    if (!trimmedResume) {
      setAnalysisError("Please upload a resume or paste your resume text before running analysis.");
      return;
    }
    if (!trimmedJd) {
      setAnalysisError("Please paste a target job description to evaluate your resume against.");
      return;
    }

    setIsAnalyzing(true);
    setAnalysisError(null);

    try {
      const payload: ResumeJDMatchRequest = {
        resume_text: trimmedResume,
        jd_text: trimmedJd,
        target_role: targetRole.trim() || undefined,
        source_type: uploadedFile ? "upload" : "paste",
      };

      const result = await apiClient<ResumeJDMatchResponse>("/api/v1/resumes/match", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setMatchResult(result);
      // Scroll to results
      setTimeout(() => {
        document.getElementById("results-section")?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    } catch (err: any) {
      console.error("ATS Match calculation failed:", err);
      // Fallback attempt to alternate endpoint if needed
      try {
        const payload: ResumeJDMatchRequest = {
          resume_text: trimmedResume,
          jd_text: trimmedJd,
          target_role: targetRole.trim() || undefined,
          source_type: uploadedFile ? "upload" : "paste",
        };
        const altResult = await apiClient<ResumeJDMatchResponse>("/api/candidate/resume-jd/match", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setMatchResult(altResult);
      } catch (altErr: any) {
        setAnalysisError(altErr.message || err.message || "Failed to calculate resume match. Please check inputs.");
      }
    } finally {
      setIsAnalyzing(false);
    }
  };

  const getScoreBadge = (score: number) => {
    if (score >= 80) return { label: "Strong Fit", variant: "success" as const, textClass: "text-emerald-700 bg-emerald-50 border-emerald-200" };
    if (score >= 65) return { label: "Good Fit", variant: "info" as const, textClass: "text-blue-700 bg-blue-50 border-blue-200" };
    if (score >= 50) return { label: "Moderate Match", variant: "warning" as const, textClass: "text-amber-700 bg-amber-50 border-amber-200" };
    return { label: "Significant Gap", variant: "danger" as const, textClass: "text-rose-700 bg-rose-50 border-rose-200" };
  };

  const getEvidenceBadge = (level: number) => {
    switch (level) {
      case 1: return { label: "L1 • Production", variant: "success" as const };
      case 2: return { label: "L2 • Responsibility", variant: "success" as const };
      case 3: return { label: "L3 • Project", variant: "info" as const };
      case 4: return { label: "L4 • Skills List", variant: "neutral" as const };
      case 5: return { label: "L5 • Contextual", variant: "warning" as const };
      default: return { label: "L6 • No Evidence", variant: "danger" as const };
    }
  };

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 space-y-6 pb-16">
      {/* 1. Header Banner */}
      <div className="bg-white border border-[#E5E5E5] rounded-xl p-6 shadow-xs relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="max-w-3xl space-y-2">
            <div className="flex items-center gap-2">
              <Badge variant="neutral" size="sm" className="font-semibold uppercase tracking-wider text-[11px]">
                ATS Engine v1.1.0
              </Badge>
              <Badge variant="neutral" size="sm" className="font-medium text-[11px]">
                Zero-Fabrication Analysis
              </Badge>
            </div>
            <h1 className="text-[28px] font-bold leading-[34px] tracking-[-0.02em] text-[#111827]">
              Resume & ATS Match Intelligence
            </h1>
            <p className="text-sm font-normal leading-[22px] text-[#4B5563]">
              Evaluate your resume against target job requirements with deterministic multi-dimensional scoring.
              Identify high-priority skill gaps, evidence strength hierarchy, and precise ATS alignment before applying.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={handleLoadSampleResume}
              title="Loads high-quality sample engineer resume for testing"
            >
              <FileCheck className="w-3.5 h-3.5 mr-1.5 text-[#4B5563]" />
              Load Sample Resume
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setTargetRole("");
                setJdText("");
                setResumeText("");
                handleRemoveFile();
                setMatchResult(null);
                setAnalysisError(null);
              }}
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1.5 text-[#4B5563]" />
              Reset All
            </Button>
          </div>
        </div>
      </div>

      {/* Error alert if any */}
      {analysisError && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold">Analysis Failed</p>
            <p className="text-xs text-red-700 mt-0.5">{analysisError}</p>
          </div>
          <button
            onClick={() => setAnalysisError(null)}
            className="text-red-500 hover:text-red-700 text-xs font-medium"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 2. Two-Column Input Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Resume Ingestion */}
        <Card className="flex flex-col h-full border-[#E5E5E5] bg-white shadow-xs">
          <CardHeader className="pb-3 border-b border-[#F0F0F0] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#111827]" />
              <h2 className="font-semibold text-base text-[#111827]">Candidate Resume</h2>
            </div>
            {uploadStatus === "parsed" && (
              <Badge variant="success" size="sm" className="font-medium text-[11px]">
                <Check className="w-3 h-3 mr-1" /> Resume Loaded
              </Badge>
            )}
          </CardHeader>
          <CardContent className="p-5 flex-1 flex flex-col space-y-4">
            {/* File Upload Box */}
            <div
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition-all duration-150 ${
                uploadedFile
                  ? "border-emerald-300 bg-emerald-50/40"
                  : "border-[#D1D5DB] hover:border-[#9CA3AF] bg-[#FAFAFA] hover:bg-[#F3F4F6]"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                onChange={handleFileChange}
                className="hidden"
              />

              {uploadedFile ? (
                <div className="flex items-center justify-between gap-3 text-left">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-lg bg-emerald-100 text-emerald-800 flex items-center justify-center shrink-0">
                      <FileCheck className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-[#111827] truncate">{uploadedFile.name}</p>
                      <p className="text-xs text-[#6B7280]">
                        {(uploadedFile.size / 1024).toFixed(1)} KB • {uploadStatus === "uploading" ? "Extracting..." : "Ready for analysis"}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        fileInputRef.current?.click();
                      }}
                    >
                      Replace
                    </Button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemoveFile();
                      }}
                      className="p-1.5 text-[#6B7280] hover:text-red-600 rounded-md hover:bg-white transition-colors"
                      title="Remove file"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <div className="w-10 h-10 mx-auto rounded-full bg-[#EEEEEE] text-[#4B5563] flex items-center justify-center">
                    <UploadCloud className="w-5 h-5" />
                  </div>
                  <p className="text-sm font-semibold text-[#111827]">
                    Click to upload or drag & drop resume
                  </p>
                  <p className="text-xs text-[#6B7280]">
                    Supports PDF, DOCX, or TXT up to 5 MB
                  </p>
                </div>
              )}
            </div>

            {uploadError && (
              <p className="text-xs text-red-600 bg-red-50 p-2.5 rounded-lg border border-red-200">
                {uploadError}
              </p>
            )}

            {/* Extracted overview pill list if parsed */}
            {extractedInfo && (
              <div className="p-3 bg-[#F9FAFB] border border-[#E5E5E5] rounded-lg text-xs space-y-1.5">
                <div className="flex justify-between text-[#4B5563]">
                  <span>Candidate: <strong>{extractedInfo.candidate_name || "Detected Candidate"}</strong></span>
                  <span>Experience: <strong>{extractedInfo.years_of_experience || 0} years</strong></span>
                </div>
                {extractedInfo.technical_skills && extractedInfo.technical_skills.length > 0 && (
                  <p className="text-[#6B7280] truncate">
                    Skills detected: {extractedInfo.technical_skills.slice(0, 8).join(", ")}
                    {extractedInfo.technical_skills.length > 8 ? ` +${extractedInfo.technical_skills.length - 8} more` : ""}
                  </p>
                )}
              </div>
            )}

            {/* Resume Text Editor / Paste Box */}
            <div className="flex-1 flex flex-col space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <label className="font-medium text-[#374151]">
                  Resume Plain Text Content
                </label>
                <span className="text-[#6B7280]">
                  {resumeText.trim().split(/\s+/).filter(Boolean).length} words
                </span>
              </div>
              <textarea
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
                placeholder="Paste your raw resume text here, or upload a document above..."
                className="w-full flex-1 min-h-[220px] p-3 rounded-lg border border-[#D1D5DB] focus:border-[#111827] focus:ring-1 focus:ring-[#111827] text-xs font-mono leading-relaxed resize-y bg-[#FAFAFA]"
              />
            </div>
          </CardContent>
        </Card>

        {/* Right Column: Job Description Ingestion */}
        <Card className="flex flex-col h-full border-[#E5E5E5] bg-white shadow-xs">
          <CardHeader className="pb-3 border-b border-[#F0F0F0] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-[#111827]" />
              <h2 className="font-semibold text-base text-[#111827]">Target Job Description</h2>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-[#6B7280]">Presets:</span>
              {SAMPLE_JD_PRESETS.map((p) => (
                <button
                  key={p.title}
                  type="button"
                  onClick={() => handleSelectPreset(p)}
                  className="text-[11px] font-medium px-2 py-0.5 rounded bg-[#F3F4F6] hover:bg-[#E5E7EB] text-[#374151] transition-colors"
                >
                  {p.title.split(" ")[0]}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="p-5 flex-1 flex flex-col space-y-4">
            {/* Target Role Input */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-[#374151]">
                Target Job Role / Title
              </label>
              <div className="relative">
                <Target className="w-4 h-4 text-[#6B7280] absolute left-3 top-2.5" />
                <input
                  type="text"
                  value={targetRole}
                  onChange={(e) => setTargetRole(e.target.value)}
                  placeholder="e.g. Senior Full-Stack Engineer"
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-[#D1D5DB] focus:border-[#111827] focus:ring-1 focus:ring-[#111827] text-sm bg-white"
                />
              </div>
            </div>

            {/* Job Description Textarea */}
            <div className="flex-1 flex flex-col space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <label className="font-medium text-[#374151]">
                  Job Description Text
                </label>
                <span className="text-[#6B7280]">
                  {jdText.trim().split(/\s+/).filter(Boolean).length} words
                </span>
              </div>
              <textarea
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="Paste the job requirements, responsibilities, and required qualifications here..."
                className="w-full flex-1 min-h-[220px] p-3 rounded-lg border border-[#D1D5DB] focus:border-[#111827] focus:ring-1 focus:ring-[#111827] text-xs font-mono leading-relaxed resize-y bg-[#FAFAFA]"
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 3. Primary Action Trigger */}
      <div className="bg-white border border-[#E5E5E5] rounded-xl p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="font-semibold text-sm text-[#111827]">
            Ready for Multi-Dimensional ATS Evaluation
          </h3>
          <p className="text-xs text-[#6B7280] mt-0.5">
            Calculates weighted fit, identifies exact evidence quotes, and flags anti-masking critical gaps.
          </p>
        </div>
        <Button
          variant="primary"
          size="md"
          isLoading={isAnalyzing}
          onClick={handleAnalyzeMatch}
          className="shrink-0 px-6 font-semibold"
        >
          <Sparkles className="w-4 h-4 mr-2" />
          {isAnalyzing ? "Analyzing ATS Fit..." : "Analyze Match & ATS Score"}
        </Button>
      </div>

      {/* 4. Results Section (Renders when matchResult is available) */}
      {matchResult && (
        <div id="results-section" className="space-y-6 pt-4">
          {/* Top KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Overall Score */}
            <div className="bg-white border border-[#E5E5E5] rounded-xl p-4 shadow-xs">
              <div className="flex items-center justify-between text-xs font-medium text-[#4B5563]">
                <span>Overall ATS Match</span>
                <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${getScoreBadge(matchResult.overall_match_score).textClass}`}>
                  {getScoreBadge(matchResult.overall_match_score).label}
                </span>
              </div>
              <div className="flex items-baseline gap-2 mt-2">
                <span className="text-[34px] font-bold leading-none tracking-tight text-[#111827]">
                  {Math.round(matchResult.overall_match_score)}%
                </span>
                <span className="text-xs text-[#6B7280]">composite</span>
              </div>
              {/* Progress bar */}
              <div className="w-full bg-[#F3F4F6] rounded-full h-1.5 mt-3 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    matchResult.overall_match_score >= 80 ? "bg-emerald-600" :
                    matchResult.overall_match_score >= 65 ? "bg-blue-600" :
                    matchResult.overall_match_score >= 50 ? "bg-amber-500" : "bg-red-500"
                  }`}
                  style={{ width: `${Math.min(100, Math.max(0, matchResult.overall_match_score))}%` }}
                />
              </div>
            </div>

            {/* Confidence */}
            <div className="bg-white border border-[#E5E5E5] rounded-xl p-4 shadow-xs">
              <span className="text-xs font-medium text-[#4B5563] block">Match Confidence</span>
              <div className="flex items-baseline gap-2 mt-2">
                <span className="text-[34px] font-bold leading-none tracking-tight text-[#111827]">
                  {matchResult.match_confidence}
                </span>
              </div>
              <p className="text-xs text-[#6B7280] mt-3 truncate">
                Based on verified evidence depth
              </p>
            </div>

            {/* Critical Gaps */}
            <div className="bg-white border border-[#E5E5E5] rounded-xl p-4 shadow-xs">
              <span className="text-xs font-medium text-[#4B5563] block">Critical Gaps</span>
              <div className="flex items-baseline gap-2 mt-2">
                <span className="text-[34px] font-bold leading-none tracking-tight text-red-600">
                  {matchResult.critical_gaps.length}
                </span>
                <span className="text-xs text-[#6B7280]">high-importance</span>
              </div>
              <p className="text-xs text-[#6B7280] mt-3 truncate">
                {matchResult.critical_gaps.length === 0 ? "No critical blockers" : "Must address before interview"}
              </p>
            </div>

            {/* Verified Strengths */}
            <div className="bg-white border border-[#E5E5E5] rounded-xl p-4 shadow-xs">
              <span className="text-xs font-medium text-[#4B5563] block">Key Strengths</span>
              <div className="flex items-baseline gap-2 mt-2">
                <span className="text-[34px] font-bold leading-none tracking-tight text-emerald-600">
                  {matchResult.strengths.length}
                </span>
                <span className="text-xs text-[#6B7280]">competencies</span>
              </div>
              <p className="text-xs text-[#6B7280] mt-3 truncate">
                Proven production alignment
              </p>
            </div>
          </div>

          {/* Sub-scores Dimensions Breakdown */}
          {matchResult.sub_scores && (
            <Card className="border-[#E5E5E5] bg-white shadow-xs">
              <CardHeader className="pb-3 border-b border-[#F0F0F0]">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-base text-[#111827]">Dimension Sub-Scores</h3>
                    <p className="text-xs text-[#6B7280] mt-0.5">
                      Weighted baseline evaluation across job requirements
                    </p>
                  </div>
                  <Badge variant="neutral" size="sm">5 Evaluated Dimensions</Badge>
                </div>
              </CardHeader>
              <CardContent className="p-5">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                  {/* Required Skills */}
                  {matchResult.sub_scores.required_skills !== undefined && matchResult.sub_scores.required_skills !== null && (
                    <div className="space-y-1.5 p-3 rounded-lg bg-[#FAFAFA] border border-[#E5E5E5]">
                      <div className="flex justify-between text-xs">
                        <span className="font-medium text-[#374151]">Required Skills (40% wt)</span>
                        <span className="font-bold text-[#111827]">{Math.round(matchResult.sub_scores.required_skills)}%</span>
                      </div>
                      <div className="w-full bg-[#E5E7EB] rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-emerald-600 h-full rounded-full"
                          style={{ width: `${matchResult.sub_scores.required_skills}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Experience */}
                  {matchResult.sub_scores.experience !== undefined && matchResult.sub_scores.experience !== null && (
                    <div className="space-y-1.5 p-3 rounded-lg bg-[#FAFAFA] border border-[#E5E5E5]">
                      <div className="flex justify-between text-xs">
                        <span className="font-medium text-[#374151]">Experience & Seniority (20% wt)</span>
                        <span className="font-bold text-[#111827]">{Math.round(matchResult.sub_scores.experience)}%</span>
                      </div>
                      <div className="w-full bg-[#E5E7EB] rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-blue-600 h-full rounded-full"
                          style={{ width: `${matchResult.sub_scores.experience}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Domain */}
                  {matchResult.sub_scores.domain !== undefined && matchResult.sub_scores.domain !== null && (
                    <div className="space-y-1.5 p-3 rounded-lg bg-[#FAFAFA] border border-[#E5E5E5]">
                      <div className="flex justify-between text-xs">
                        <span className="font-medium text-[#374151]">Domain Knowledge (15% wt)</span>
                        <span className="font-bold text-[#111827]">{Math.round(matchResult.sub_scores.domain)}%</span>
                      </div>
                      <div className="w-full bg-[#E5E7EB] rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-purple-600 h-full rounded-full"
                          style={{ width: `${matchResult.sub_scores.domain}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Responsibilities */}
                  {matchResult.sub_scores.responsibilities !== undefined && matchResult.sub_scores.responsibilities !== null && (
                    <div className="space-y-1.5 p-3 rounded-lg bg-[#FAFAFA] border border-[#E5E5E5]">
                      <div className="flex justify-between text-xs">
                        <span className="font-medium text-[#374151]">Responsibilities Fit (15% wt)</span>
                        <span className="font-bold text-[#111827]">{Math.round(matchResult.sub_scores.responsibilities)}%</span>
                      </div>
                      <div className="w-full bg-[#E5E7EB] rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-indigo-600 h-full rounded-full"
                          style={{ width: `${matchResult.sub_scores.responsibilities}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Preferred Skills */}
                  {matchResult.sub_scores.preferred_skills !== undefined && matchResult.sub_scores.preferred_skills !== null && (
                    <div className="space-y-1.5 p-3 rounded-lg bg-[#FAFAFA] border border-[#E5E5E5]">
                      <div className="flex justify-between text-xs">
                        <span className="font-medium text-[#374151]">Preferred Skills (10% wt)</span>
                        <span className="font-bold text-[#111827]">{Math.round(matchResult.sub_scores.preferred_skills)}%</span>
                      </div>
                      <div className="w-full bg-[#E5E7EB] rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-amber-600 h-full rounded-full"
                          style={{ width: `${matchResult.sub_scores.preferred_skills}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Strengths & Critical Gaps Dual Card */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Strengths */}
            <Card className="border-[#E5E5E5] bg-white shadow-xs">
              <CardHeader className="pb-3 border-b border-[#F0F0F0] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <h3 className="font-semibold text-base text-[#111827]">Verified Strengths</h3>
                </div>
                <Badge variant="success" size="sm">{matchResult.strengths.length} items</Badge>
              </CardHeader>
              <CardContent className="p-5">
                {matchResult.strengths.length > 0 ? (
                  <ul className="space-y-2.5">
                    {matchResult.strengths.map((str, idx) => (
                      <li key={idx} className="flex items-start gap-2.5 text-xs text-[#374151] leading-relaxed">
                        <span className="w-4 h-4 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5 text-[10px] font-bold">✓</span>
                        <span>{str}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-[#6B7280]">No prominent strengths identified.</p>
                )}
              </CardContent>
            </Card>

            {/* Critical Gaps & Missing Skills */}
            <Card className="border-[#E5E5E5] bg-white shadow-xs">
              <CardHeader className="pb-3 border-b border-[#F0F0F0] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  <h3 className="font-semibold text-base text-[#111827]">Identified Competency Gaps</h3>
                </div>
                <Badge variant={matchResult.critical_gaps.length > 0 ? "danger" : "neutral"} size="sm">
                  {matchResult.critical_gaps.length} Critical
                </Badge>
              </CardHeader>
              <CardContent className="p-5 space-y-4">
                {/* Critical Gaps */}
                {matchResult.critical_gaps.length > 0 && (
                  <div className="p-3 rounded-lg bg-red-50 border border-red-200 space-y-1.5">
                    <p className="text-xs font-semibold text-red-800 flex items-center gap-1.5">
                      <XCircle className="w-3.5 h-3.5 text-red-600" />
                      Critical High-Importance Gaps (Anti-Masking):
                    </p>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {matchResult.critical_gaps.map((cg, idx) => (
                        <span key={idx} className="px-2 py-0.5 rounded bg-white text-red-700 border border-red-200 text-xs font-medium">
                          {cg}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Other Gaps */}
                {matchResult.skill_gaps.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-medium text-[#4B5563]">Secondary Missing Skills:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {matchResult.skill_gaps.map((sg, idx) => (
                        <span key={idx} className="px-2 py-0.5 rounded bg-[#F3F4F6] text-[#4B5563] border border-[#E5E5E5] text-xs">
                          {sg}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Skill Matrix Detailed Table */}
          {matchResult.skill_matrix && matchResult.skill_matrix.length > 0 && (
            <Card className="border-[#E5E5E5] bg-white shadow-xs overflow-hidden">
              <CardHeader className="pb-3 border-b border-[#F0F0F0]">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-base text-[#111827]">Competency Evidence Matrix</h3>
                    <p className="text-xs text-[#6B7280] mt-0.5">
                      Verified evidence hierarchy with exact resume textual matches
                    </p>
                  </div>
                  <Badge variant="neutral" size="sm">{matchResult.skill_matrix.length} Requirements</Badge>
                </div>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-[#E5E5E5] bg-[#FAFAFA] text-[#6B7280] font-medium">
                      <th className="py-3 px-4">Requirement / Skill</th>
                      <th className="py-3 px-3">Importance</th>
                      <th className="py-3 px-3">Evidence Level</th>
                      <th className="py-3 px-3">Status</th>
                      <th className="py-3 px-4">Found Resume Evidence</th>
                      <th className="py-3 px-3 text-right">Score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#F0F0F0]">
                    {matchResult.skill_matrix.map((item: ResumeSkillMatrixItem, idx: number) => {
                      const evBadge = getEvidenceBadge(item.evidence_level);
                      return (
                        <tr key={idx} className="hover:bg-[#FAFAFA] transition-colors">
                          <td className="py-3 px-4 font-semibold text-[#111827] max-w-[180px] truncate">
                            {item.skill}
                          </td>
                          <td className="py-3 px-3">
                            <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                              item.importance === "HIGH" ? "bg-red-50 text-red-700 border border-red-200" :
                              item.importance === "MEDIUM" ? "bg-amber-50 text-amber-700 border border-amber-200" :
                              "bg-gray-100 text-gray-700"
                            }`}>
                              {item.importance}
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            <Badge variant={evBadge.variant} size="sm" className="text-[10px]">
                              {evBadge.label}
                            </Badge>
                          </td>
                          <td className="py-3 px-3">
                            <span className={`inline-flex items-center gap-1 font-medium ${
                              item.gap_status === "matched" ? "text-emerald-700" :
                              item.gap_status === "partial" ? "text-amber-700" : "text-rose-700"
                            }`}>
                              {item.gap_status === "matched" ? "Matched" :
                               item.gap_status === "partial" ? "Partial" : "Gap"}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-[#4B5563] max-w-[280px]">
                            {item.resume_evidence ? (
                              <span className="italic line-clamp-2">"{item.resume_evidence}"</span>
                            ) : (
                              <span className="text-[#9CA3AF] italic">No verifiable textual evidence</span>
                            )}
                          </td>
                          <td className="py-3 px-3 text-right font-mono font-bold text-[#111827]">
                            {Math.round(item.match_score)}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* Actionable Recommendations */}
          {matchResult.recommendations && matchResult.recommendations.length > 0 && (
            <Card className="border-[#E5E5E5] bg-white shadow-xs">
              <CardHeader className="pb-3 border-b border-[#F0F0F0]">
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-[#111827]" />
                  <h3 className="font-semibold text-base text-[#111827]">Actionable Improvement Recommendations</h3>
                </div>
              </CardHeader>
              <CardContent className="p-5">
                <div className="space-y-2.5">
                  {matchResult.recommendations.map((rec, idx) => (
                    <div key={idx} className="flex items-start gap-2.5 text-xs text-[#374151] leading-relaxed p-2.5 rounded-lg bg-[#FAFAFA] border border-[#E5E5E5]">
                      <span className="w-4 h-4 rounded-full bg-[#111827] text-white flex items-center justify-center shrink-0 mt-0.5 text-[10px] font-bold">
                        {idx + 1}
                      </span>
                      <span>{rec}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* CTAs to other modules */}
          <div className="p-6 rounded-xl border border-[#E5E5E5] bg-[#FAFAFA] text-center space-y-3">
            <h3 className="text-base font-semibold text-[#111827]">
              Next Steps for {matchResult.target_role || "your role"}
            </h3>
            <p className="text-xs text-[#6B7280] max-w-lg mx-auto leading-relaxed">
              Use your ATS score insights to target gap areas in mock interviews, explore personalized learning roadmaps, or receive Socratic guidance.
            </p>
            <div className="pt-2 flex flex-wrap gap-3 justify-center items-center">
              <Link href="/interviews">
                <Button variant="primary" size="md">
                  <span>Start Mock Interview</span>
                  <ArrowRight size={14} className="ml-1.5" />
                </Button>
              </Link>
              <Link href="/paths">
                <Button variant="secondary" size="md">
                  <Layers size={14} className="mr-1.5" />
                  <span>Adaptive Learning Path</span>
                </Button>
              </Link>
              <Link href="/competency">
                <Button variant="outline" size="md">
                  <Target size={14} className="mr-1.5" />
                  <span>Competency Dashboard</span>
                </Button>
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
