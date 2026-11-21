"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { apiClient } from "@/lib/api/client";
import {
  CandidateSkillEntry,
  OnboardingAssessmentResponse,
  CompleteOnboardingResponse,
  ResumeUploadExtractResponse,
  WorkExperienceEntry,
  ProjectEntry,
} from "@/lib/types";
import {
  UploadCloud,
  FileText,
  X,
  Plus,
  Trash2,
  Check,
  AlertCircle,
  ArrowRight,
  BookOpen,
  BarChart3,
  CheckCircle2,
  Briefcase,
  GraduationCap,
  Award,
} from "lucide-react";

const RECOMMENDED_ROLES = [
  "AI Engineer",
  "Software Engineer",
  "Frontend Developer",
  "Backend Developer",
  "Full Stack Developer",
  "Data Analyst",
  "Data Scientist",
  "UI/UX Designer",
  "Product Designer",
  "DevOps Engineer",
  "Cloud Engineer",
  "Machine Learning Engineer",
  "QA Engineer",
  "Business Analyst",
];

const SUGGESTED_QUICK_SKILLS = [
  "Python", "JavaScript", "TypeScript", "React", "Next.js", "FastAPI",
  "Node.js", "PostgreSQL", "Docker", "Kubernetes", "AWS", "Google Cloud",
  "Machine Learning", "Generative AI", "RAG", "System Design", "CI/CD", "Git"
];

export default function CandidateOnboardingPage() {
  const [viewState, setViewState] = useState<"form" | "assessed">("form");

  // Resume Upload & Extraction State
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [uploadedFileSize, setUploadedFileSize] = useState<number>(0);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "parsing" | "completed" | "error">("idle");
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [rawResumeText, setRawResumeText] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Form Fields: 1. Candidate Information
  const [fullName, setFullName] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [phone, setPhone] = useState<string>("");
  const [summary, setSummary] = useState<string>("");

  // Form Fields: 2. Education
  const [educationLevel, setEducationLevel] = useState<string>("");
  const [institution, setInstitution] = useState<string>("");
  const [graduationYear, setGraduationYear] = useState<number | "">(2023);

  // Form Fields: 3. Experience
  const [currentRole, setCurrentRole] = useState<string>("");
  const [currentCompany, setCurrentCompany] = useState<string>("");
  const [yearsOfExperience, setYearsOfExperience] = useState<number>(2.0);
  const [workExperience, setWorkExperience] = useState<WorkExperienceEntry[]>([
    { company: "", role: "", duration: "", description: "" },
  ]);

  // Form Fields: 4. Skills
  const [skillsList, setSkillsList] = useState<CandidateSkillEntry[]>([]);
  const [newSkillInput, setNewSkillInput] = useState<string>("");

  // Form Fields: 5. Projects
  const [projectsList, setProjectsList] = useState<ProjectEntry[]>([
    { name: "", description: "", technologies: [] },
  ]);

  // Form Fields: 6. Certifications
  const [certificationsList, setCertificationsList] = useState<string[]>([]);
  const [newCertInput, setNewCertInput] = useState<string>("");

  // Form Fields: 7. Target Job Role & Level
  const [targetRole, setTargetRole] = useState<string>("AI Engineer");
  const [targetLevel, setTargetLevel] = useState<"Junior" | "Mid-Level" | "Senior">("Mid-Level");
  const [customRoleInput, setCustomRoleInput] = useState<string>("");
  const [isCustomRole, setIsCustomRole] = useState<boolean>(false);

  // Submission & Results State
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [assessmentResult, setAssessmentResult] = useState<OnboardingAssessmentResponse | null>(null);
  const [completionResult, setCompletionResult] = useState<CompleteOnboardingResponse | null>(null);

  useEffect(() => {
    async function fetchUser() {
      try {
        const user = await apiClient<{ email?: string; full_name?: string }>("/api/v1/auth/me").catch(() => null);
        if (user) {
          if (user.full_name && !fullName) setFullName(user.full_name);
          if (user.email && !email) setEmail(user.email);
        }
      } catch {
        // Fallback
      }
    }
    fetchUser();
  }, []);

  const activeRole = isCustomRole ? customRoleInput.trim() || "Full Stack Developer" : targetRole;

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  };

  const handleFileSelected = async (file: File) => {
    setResumeError(null);
    const validExts = [".pdf", ".docx", ".doc", ".txt"];
    const fileExt = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (!validExts.includes(fileExt)) {
      setResumeError("Unsupported format. Please upload a PDF, DOCX, or TXT resume document.");
      setUploadStatus("error");
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setResumeError("File size exceeds 5MB limit. Please upload a smaller resume document.");
      setUploadStatus("error");
      return;
    }

    setResumeFile(file);
    setUploadedFileName(file.name);
    setUploadedFileSize(file.size);
    setUploadStatus("parsing");

    await triggerAutoExtraction(file);
  };

  const triggerAutoExtraction = async (file: File) => {
    setIsExtracting(true);
    setResumeError(null);
    setUploadStatus("parsing");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await apiClient<ResumeUploadExtractResponse>("/api/v1/learners/upload-resume", {
        method: "POST",
        body: formData,
      });

      setRawResumeText(res.raw_text || "");

      if (res.candidate_name) setFullName(res.candidate_name);
      if (res.email) setEmail(res.email);
      if (res.phone) setPhone(res.phone);
      if (res.summary) setSummary(res.summary);

      if (res.education) setEducationLevel(res.education);
      if (res.institution) setInstitution(res.institution);
      if (res.graduation_year) setGraduationYear(res.graduation_year);

      if (res.current_role) setCurrentRole(res.current_role);
      if (res.current_company) setCurrentCompany(res.current_company);
      if (res.years_of_experience !== undefined) {
        setYearsOfExperience(res.years_of_experience);
        if (res.years_of_experience >= 5) setTargetLevel("Senior");
        else if (res.years_of_experience >= 2) setTargetLevel("Mid-Level");
        else setTargetLevel("Junior");
      }

      if (res.work_experience && res.work_experience.length > 0) {
        setWorkExperience(res.work_experience);
      }

      if (res.skills && res.skills.length > 0) {
        const mappedSkills: CandidateSkillEntry[] = res.skills.map((s) => ({
          skill: s.skill,
          category: s.category || "Technical Skills",
          proficiency: s.proficiency || "Intermediate",
          source: "RESUME_EXTRACTED",
        }));
        setSkillsList(mappedSkills);
      }

      if (res.projects_detail && res.projects_detail.length > 0) {
        setProjectsList(res.projects_detail);
      } else if (res.projects && res.projects.length > 0) {
        setProjectsList(
          res.projects.map((pName) => ({
            name: pName,
            description: "",
            technologies: [],
          }))
        );
      }

      if (res.certifications && res.certifications.length > 0) {
        setCertificationsList(res.certifications);
      }
      setUploadStatus("completed");
    } catch (err: any) {
      console.error("Auto extraction error:", err);
      setUploadStatus("error");
      setResumeError(err.message || "Failed to extract information from resume. Please verify the document or edit manually.");
    } finally {
      setIsExtracting(false);
    }
  };

  const handleRemoveResume = () => {
    setResumeFile(null);
    setUploadedFileName(null);
    setUploadedFileSize(0);
    setRawResumeText("");
    setResumeError(null);
    setUploadStatus("idle");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setSkillsList((prev) => prev.filter((s) => s.skill.toLowerCase() !== skillToRemove.toLowerCase()));
  };

  const handleAddManualSkill = () => {
    const trimmed = newSkillInput.trim();
    if (!trimmed) return;
    if (skillsList.some((s) => s.skill.toLowerCase() === trimmed.toLowerCase())) {
      setNewSkillInput("");
      return;
    }
    setSkillsList((prev) => [
      ...prev,
      {
        skill: trimmed,
        category: "Technical Skills",
        proficiency: "Intermediate",
        source: "SELF_REPORTED",
      },
    ]);
    setNewSkillInput("");
  };

  const handleToggleQuickSkill = (skillName: string) => {
    const exists = skillsList.some((s) => s.skill.toLowerCase() === skillName.toLowerCase());
    if (exists) {
      handleRemoveSkill(skillName);
    } else {
      setSkillsList((prev) => [
        ...prev,
        {
          skill: skillName,
          category: "Technical Skills",
          proficiency: "Intermediate",
          source: "SELF_REPORTED",
        },
      ]);
    }
  };

  const handleAddWorkExperience = () => {
    setWorkExperience((prev) => [
      ...prev,
      { company: "", role: "", duration: "", description: "" },
    ]);
  };

  const handleUpdateWorkExperience = (index: number, field: keyof WorkExperienceEntry, value: string) => {
    setWorkExperience((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handleRemoveWorkExperience = (index: number) => {
    setWorkExperience((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddProject = () => {
    setProjectsList((prev) => [
      ...prev,
      { name: "", description: "", technologies: [] },
    ]);
  };

  const handleUpdateProject = (index: number, field: keyof ProjectEntry, value: any) => {
    setProjectsList((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handleRemoveProject = (index: number) => {
    setProjectsList((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddCertification = () => {
    const trimmed = newCertInput.trim();
    if (!trimmed) return;
    if (!certificationsList.includes(trimmed)) {
      setCertificationsList((prev) => [...prev, trimmed]);
    }
    setNewCertInput("");
  };

  const handleRemoveCertification = (index: number) => {
    setCertificationsList((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmitAndAssess = async () => {
    if (!activeRole) {
      alert("Please select or specify your target job role.");
      return;
    }
    if (skillsList.length === 0 && !resumeFile && !summary) {
      alert("Please provide at least a few skills, a summary, or upload your resume.");
      return;
    }

    setIsSubmitting(true);

    try {
      const cleanedWorkExp = workExperience.filter((w) => w.company.trim() || w.role.trim() || w.description?.trim());
      const cleanedProjects = projectsList.filter((p) => p.name.trim() || p.description?.trim());

      const res = await apiClient<CompleteOnboardingResponse>("/api/v1/learners/complete-onboarding", {
        method: "POST",
        body: JSON.stringify({
          full_name: fullName.trim() || undefined,
          email: email.trim() || undefined,
          phone: phone.trim() || undefined,
          summary: summary.trim() || undefined,
          education_level: educationLevel.trim() || undefined,
          institution: institution.trim() || undefined,
          graduation_year: typeof graduationYear === "number" ? graduationYear : undefined,
          target_role: activeRole,
          target_level: targetLevel,
          years_of_experience: Number(yearsOfExperience) || 0.0,
          current_role: currentRole.trim() || undefined,
          current_company: currentCompany.trim() || undefined,
          work_experience: cleanedWorkExp,
          projects: cleanedProjects,
          certifications: certificationsList,
          skills: skillsList,
          raw_resume_text: rawResumeText || undefined,
          resume_filename: uploadedFileName || undefined,
        }),
      });

      setCompletionResult(res);
      if (res.assessment) {
        setAssessmentResult(res.assessment);
      }
      setViewState("assessed");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err: any) {
      console.error("Submission failed:", err);
      alert(err.message || "Failed to submit profile and generate assessment.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const strongSkills = assessmentResult?.evaluated_skills.filter((s) => s.status === "Matched") || [];
  const skillsToImprove = assessmentResult?.evaluated_skills.filter((s) => s.status === "Partial Match") || [];
  const missingSkills = assessmentResult?.evaluated_skills.filter((s) => s.status === "Gap") || [];

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-12">
      {/* Header */}
      <div className="border-b border-[#E5E5E5] pb-5">
        <h1 className="text-xl font-semibold tracking-tight text-[#111827]">
          Candidate onboarding & skill assessment
        </h1>
        <p className="text-xs text-[#6B7280] mt-1 leading-relaxed">
          Upload your resume to extract candidate data automatically, refine your profile fields below, and receive a target-role competency match assessment.
        </p>
      </div>

      {/* ======================================================================= */}
      {/* 1. EDITABLE ONBOARDING FORM VIEW */}
      {/* ======================================================================= */}
      {viewState === "form" && (
        <div className="space-y-6">
          {/* UPLOAD SECTION */}
          <Card className="p-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-[#111827]">Resume upload</h2>
                  <p className="text-xs text-[#6B7280] mt-0.5">
                    PDF or DOCX documents are extracted automatically into the fields below.
                  </p>
                </div>
                <Badge variant="default" size="sm">
                  PDF & DOCX
                </Badge>
              </div>

              {!uploadedFileName ? (
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                    isDragging
                      ? "border-[#111827] bg-[#F7F7F7]"
                      : "border-[#E5E5E5] bg-[#FAFAFA] hover:border-slate-400 hover:bg-[#F3F3F3]"
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.docx,.doc,.txt"
                    onChange={handleFileInputChange}
                    className="hidden"
                  />
                  <div className="flex flex-col items-center justify-center space-y-2.5">
                    {isExtracting ? (
                      <div className="flex flex-col items-center space-y-2">
                        <div className="w-6 h-6 border-2 border-[#111827] border-t-transparent rounded-full animate-spin" />
                        <p className="text-xs font-medium text-[#111827]">
                          Extracting resume information...
                        </p>
                        <p className="text-[11px] text-[#6B7280]">Populating form fields automatically</p>
                      </div>
                    ) : (
                      <>
                        <div className="w-10 h-10 rounded-full bg-white border border-[#E5E5E5] flex items-center justify-center text-[#4B5563] shadow-2xs">
                          <UploadCloud size={20} strokeWidth={1.75} />
                        </div>
                        <div>
                          <p className="text-xs font-medium text-[#111827]">
                            Click to select a resume or drag and drop here
                          </p>
                          <p className="text-[11px] text-[#6B7280] mt-0.5">
                            PDF, DOCX, or TXT format (up to 5MB)
                          </p>
                        </div>
                        <Button variant="secondary" size="sm" type="button" className="mt-1">
                          Select file
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              ) : (
                <div className="p-3.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <FileText size={18} strokeWidth={1.75} className="text-[#374151] shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-[#111827] truncate">{uploadedFileName}</p>
                      {uploadStatus === "parsing" ? (
                        <p className="text-[11px] text-blue-600 flex items-center gap-1.5">
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
                          {(uploadedFileSize / 1024).toFixed(1)} KB • Extracting details with AI...
                        </p>
                      ) : uploadStatus === "error" ? (
                        <p className="text-[11px] text-red-600">
                          {(uploadedFileSize / 1024).toFixed(1)} KB • Extraction failed
                        </p>
                      ) : (
                        <p className="text-[11px] text-[#065F46]">
                          {(uploadedFileSize / 1024).toFixed(1)} KB • Extracted into form below
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isExtracting}
                    >
                      Replace
                    </Button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.docx,.doc,.txt"
                      onChange={handleFileInputChange}
                      className="hidden"
                    />
                    <button
                      type="button"
                      onClick={handleRemoveResume}
                      className="text-xs text-[#6B7280] hover:text-rose-600 px-2 py-1"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}

              {resumeError && (
                <div className="p-3.5 rounded-lg border border-red-200 bg-red-50 text-red-800 text-xs flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2">
                    <AlertCircle size={16} strokeWidth={1.75} className="text-red-600 mt-0.5 shrink-0" />
                    <div>
                      <p className="font-medium text-red-900">Resume extraction notice</p>
                      <p className="mt-0.5 text-red-700 leading-relaxed">{resumeError}</p>
                      <p className="mt-1 text-[11px] text-red-600">You can also fill out or edit your profile fields directly below.</p>
                    </div>
                  </div>
                  {resumeFile && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => triggerAutoExtraction(resumeFile)}
                      disabled={isExtracting}
                      className="shrink-0 text-xs"
                    >
                      Retry
                    </Button>
                  )}
                </div>
              )}
            </div>
          </Card>

          {/* EDITABLE FORM SECTIONS */}
          <div className="space-y-6">
            {/* SECTION 1: CANDIDATE INFO */}
            <Card className="p-6 space-y-4">
              <div className="border-b border-[#F0F0F0] pb-3">
                <h2 className="text-sm font-semibold text-[#111827]">1. Candidate information</h2>
                <p className="text-xs text-[#6B7280] mt-0.5">
                  Contact details and summary extracted from your resume.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Full name <span className="text-rose-600">*</span>
                  </label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Alex River"
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Email address
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="e.g. alex@example.com"
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Phone number
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="e.g. +1 (555) 019-2834"
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">
                  Professional summary
                </label>
                <textarea
                  rows={3}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="Overview of your technical background, specialties, and career objectives..."
                  className="w-full bg-white border border-[#E5E5E5] rounded-lg p-3 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900 leading-relaxed"
                />
              </div>
            </Card>

            {/* SECTION 2: EDUCATION */}
            <Card className="p-6 space-y-4">
              <div className="border-b border-[#F0F0F0] pb-3">
                <h2 className="text-sm font-semibold text-[#111827]">2. Education</h2>
                <p className="text-xs text-[#6B7280] mt-0.5">
                  Degree qualification, university or institution, and graduation year.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Degree / Qualification
                  </label>
                  <input
                    type="text"
                    value={educationLevel}
                    onChange={(e) => setEducationLevel(e.target.value)}
                    placeholder="e.g. B.S. in Computer Science"
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Institution / University
                  </label>
                  <input
                    type="text"
                    value={institution}
                    onChange={(e) => setInstitution(e.target.value)}
                    placeholder="e.g. Stanford University"
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Graduation year
                  </label>
                  <input
                    type="number"
                    value={graduationYear}
                    onChange={(e) => setGraduationYear(e.target.value ? parseInt(e.target.value) : "")}
                    placeholder="e.g. 2023"
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>
              </div>
            </Card>

            {/* SECTION 3: EXPERIENCE */}
            <Card className="p-6 space-y-4">
              <div className="border-b border-[#F0F0F0] pb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-[#111827]">3. Professional experience</h2>
                  <p className="text-xs text-[#6B7280] mt-0.5">
                    Current role, total duration, and prior work history.
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  type="button"
                  onClick={handleAddWorkExperience}
                >
                  <Plus size={13} strokeWidth={1.75} />
                  <span>Add position</span>
                </Button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Current role / title
                  </label>
                  <input
                    type="text"
                    value={currentRole}
                    onChange={(e) => setCurrentRole(e.target.value)}
                    placeholder="e.g. Full-Stack Engineer"
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Current company / organization
                  </label>
                  <input
                    type="text"
                    value={currentCompany}
                    onChange={(e) => setCurrentCompany(e.target.value)}
                    placeholder="e.g. Acme Tech"
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-[#374151] block mb-1">
                    Total years of experience
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    max="50"
                    value={yearsOfExperience}
                    onChange={(e) => setYearsOfExperience(parseFloat(e.target.value) || 0)}
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                  />
                </div>
              </div>

              {/* Work Experience Entries */}
              <div className="space-y-3 pt-2">
                <span className="text-xs font-semibold text-[#374151] block">
                  Work history entries ({workExperience.length}):
                </span>

                {workExperience.map((exp, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-[#111827]">Position #{idx + 1}</span>
                      {workExperience.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveWorkExperience(idx)}
                          className="text-xs text-[#6B7280] hover:text-rose-600 inline-flex items-center gap-1"
                        >
                          <Trash2 size={12} strokeWidth={1.75} />
                          <span>Remove</span>
                        </button>
                      )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div>
                        <label className="text-[11px] text-[#6B7280] block mb-1">Company</label>
                        <input
                          type="text"
                          value={exp.company}
                          onChange={(e) => handleUpdateWorkExperience(idx, "company", e.target.value)}
                          placeholder="Company name"
                          className="w-full bg-white border border-[#E5E5E5] rounded px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-slate-900"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-[#6B7280] block mb-1">Role / Title</label>
                        <input
                          type="text"
                          value={exp.role}
                          onChange={(e) => handleUpdateWorkExperience(idx, "role", e.target.value)}
                          placeholder="e.g. Senior Backend Dev"
                          className="w-full bg-white border border-[#E5E5E5] rounded px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-slate-900"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-[#6B7280] block mb-1">Duration</label>
                        <input
                          type="text"
                          value={exp.duration || ""}
                          onChange={(e) => handleUpdateWorkExperience(idx, "duration", e.target.value)}
                          placeholder="e.g. 2021 - 2023"
                          className="w-full bg-white border border-[#E5E5E5] rounded px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-slate-900"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="text-[11px] text-[#6B7280] block mb-1">Responsibilities & technologies</label>
                      <textarea
                        rows={2}
                        value={exp.description || ""}
                        onChange={(e) => handleUpdateWorkExperience(idx, "description", e.target.value)}
                        placeholder="Key responsibilities and technical accomplishments..."
                        className="w-full bg-white border border-[#E5E5E5] rounded p-2 text-xs text-[#111827] focus:outline-none focus:border-slate-900 leading-relaxed"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            {/* SECTION 4: SKILLS */}
            <Card className="p-6 space-y-4">
              <div className="border-b border-[#F0F0F0] pb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-[#111827]">4. Skills inventory</h2>
                  <p className="text-xs text-[#6B7280] mt-0.5">
                    Extracted skills list. Add missing skills or remove incorrect tags (no manual rating needed).
                  </p>
                </div>
                <Badge variant="default" size="sm">
                  {skillsList.length} skills identified
                </Badge>
              </div>

              {/* Skills Chips */}
              <div className="p-3.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] min-h-[80px] flex flex-wrap gap-2 items-center">
                {skillsList.length > 0 ? (
                  skillsList.map((s, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-white text-[#111827] border border-[#E5E5E5] shadow-2xs"
                    >
                      <span className="font-medium">{s.skill}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(s.skill)}
                        className="text-[#9CA3AF] hover:text-rose-600 transition-colors ml-0.5"
                        title="Remove skill"
                      >
                        <X size={13} strokeWidth={1.75} />
                      </button>
                    </span>
                  ))
                ) : (
                  <p className="text-xs text-[#6B7280] italic">
                    No skills identified yet. Upload a resume or add skills using the input below.
                  </p>
                )}
              </div>

              {/* Add Custom Skill Input */}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newSkillInput}
                  onChange={(e) => setNewSkillInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleAddManualSkill())}
                  placeholder="Type a skill name and press Enter (e.g. Next.js, Redis, PyTorch)..."
                  className="flex-1 bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                />
                <Button variant="secondary" size="sm" type="button" onClick={handleAddManualSkill}>
                  <Plus size={13} strokeWidth={1.75} />
                  <span>Add skill</span>
                </Button>
              </div>

              {/* Quick Add Pills */}
              <div className="space-y-1.5 pt-1">
                <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider block">
                  Quick-add common technologies:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {SUGGESTED_QUICK_SKILLS.map((sk) => {
                    const isAdded = skillsList.some((s) => s.skill.toLowerCase() === sk.toLowerCase());
                    return (
                      <button
                        key={sk}
                        type="button"
                        onClick={() => handleToggleQuickSkill(sk)}
                        className={`text-xs px-2.5 py-1 rounded-md border transition-colors flex items-center gap-1 ${
                          isAdded
                            ? "border-[#111827] bg-[#111827] text-white font-medium"
                            : "border-[#E5E5E5] bg-white text-[#374151] hover:bg-[#F3F3F3]"
                        }`}
                      >
                        {isAdded ? (
                          <Check size={12} strokeWidth={2} />
                        ) : (
                          <Plus size={12} strokeWidth={2} />
                        )}
                        <span>{sk}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </Card>

            {/* SECTION 5: PROJECTS */}
            <Card className="p-6 space-y-4">
              <div className="border-b border-[#F0F0F0] pb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-[#111827]">5. Technical projects</h2>
                  <p className="text-xs text-[#6B7280] mt-0.5">
                    Key projects demonstrating practical architecture and code execution.
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  type="button"
                  onClick={handleAddProject}
                >
                  <Plus size={13} strokeWidth={1.75} />
                  <span>Add project</span>
                </Button>
              </div>

              <div className="space-y-3">
                {projectsList.map((proj, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-[#111827]">Project #{idx + 1}</span>
                      {projectsList.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveProject(idx)}
                          className="text-xs text-[#6B7280] hover:text-rose-600 inline-flex items-center gap-1"
                        >
                          <Trash2 size={12} strokeWidth={1.75} />
                          <span>Remove</span>
                        </button>
                      )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="text-[11px] text-[#6B7280] block mb-1">Project name</label>
                        <input
                          type="text"
                          value={proj.name}
                          onChange={(e) => handleUpdateProject(idx, "name", e.target.value)}
                          placeholder="e.g. Distributed Task Queue"
                          className="w-full bg-white border border-[#E5E5E5] rounded px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-slate-900"
                        />
                      </div>

                      <div>
                        <label className="text-[11px] text-[#6B7280] block mb-1">Technologies used (comma-separated)</label>
                        <input
                          type="text"
                          value={proj.technologies ? proj.technologies.join(", ") : ""}
                          onChange={(e) =>
                            handleUpdateProject(
                              idx,
                              "technologies",
                              e.target.value.split(",").map((t) => t.trim()).filter(Boolean)
                            )
                          }
                          placeholder="e.g. Python, Redis, FastAPI, Docker"
                          className="w-full bg-white border border-[#E5E5E5] rounded px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-slate-900"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="text-[11px] text-[#6B7280] block mb-1">Description</label>
                      <textarea
                        rows={2}
                        value={proj.description || ""}
                        onChange={(e) => handleUpdateProject(idx, "description", e.target.value)}
                        placeholder="Architectural overview, challenge solved, and measurable impact..."
                        className="w-full bg-white border border-[#E5E5E5] rounded p-2 text-xs text-[#111827] focus:outline-none focus:border-slate-900 leading-relaxed"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            {/* SECTION 6: CERTIFICATIONS */}
            <Card className="p-6 space-y-4">
              <div className="border-b border-[#F0F0F0] pb-3">
                <h2 className="text-sm font-semibold text-[#111827]">6. Certifications & credentials</h2>
                <p className="text-xs text-[#6B7280] mt-0.5">
                  Professional certifications, verified accreditations, or diplomas.
                </p>
              </div>

              {certificationsList.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {certificationsList.map((cert, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs bg-[#FAFAFA] text-[#111827] border border-[#E5E5E5]"
                    >
                      <Award size={13} strokeWidth={1.75} className="text-[#6B7280]" />
                      <span>{cert}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveCertification(idx)}
                        className="text-[#9CA3AF] hover:text-rose-600 ml-1 text-xs"
                      >
                        <X size={12} strokeWidth={1.75} />
                      </button>
                    </span>
                  ))}
                </div>
              )}

              <div className="flex gap-2">
                <input
                  type="text"
                  value={newCertInput}
                  onChange={(e) => setNewCertInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleAddCertification())}
                  placeholder="e.g. AWS Certified Solutions Architect, CKA..."
                  className="flex-1 bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                />
                <Button variant="secondary" size="sm" type="button" onClick={handleAddCertification}>
                  <Plus size={13} strokeWidth={1.75} />
                  <span>Add</span>
                </Button>
              </div>
            </Card>

            {/* SECTION 7: TARGET JOB ROLE */}
            <Card className="p-6 space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-[#111827]">7. Target job role & level</h2>
                <p className="text-xs text-[#6B7280] mt-0.5">
                  Select your target job role and seniority to benchmark your competency match.
                </p>
              </div>

              {!isCustomRole ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider">
                      Recommended roles:
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setIsCustomRole(true);
                        setCustomRoleInput("");
                      }}
                      className="text-xs text-[#111827] hover:underline font-medium"
                    >
                      + Enter custom role
                    </button>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {RECOMMENDED_ROLES.map((role) => {
                      const isSelected = targetRole === role;
                      return (
                        <button
                          key={role}
                          type="button"
                          onClick={() => setTargetRole(role)}
                          className={`text-xs px-3 py-1.5 rounded-lg border transition-colors font-medium ${
                            isSelected
                              ? "border-[#111827] bg-[#111827] text-white"
                              : "border-[#E5E5E5] bg-white text-[#374151] hover:bg-[#F3F3F3]"
                          }`}
                        >
                          {role}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="space-y-2 p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-[#111827]">Custom target role:</label>
                    <button
                      type="button"
                      onClick={() => setIsCustomRole(false)}
                      className="text-xs text-[#6B7280] hover:text-[#111827] underline"
                    >
                      Back to list
                    </button>
                  </div>
                  <input
                    type="text"
                    value={customRoleInput}
                    onChange={(e) => setCustomRoleInput(e.target.value)}
                    placeholder="e.g. Platform Reliability Engineer, Security Architect..."
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-2 text-xs text-[#111827] focus:outline-none focus:border-slate-900"
                  />
                </div>
              )}

              {/* Target Seniority Level */}
              <div className="pt-2">
                <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider block mb-2">
                  Target seniority level:
                </span>
                <div className="flex gap-2">
                  {(["Junior", "Mid-Level", "Senior"] as const).map((lvl) => (
                    <button
                      key={lvl}
                      type="button"
                      onClick={() => setTargetLevel(lvl)}
                      className={`text-xs px-3.5 py-1.5 rounded-lg border transition-colors font-medium ${
                        targetLevel === lvl
                          ? "border-[#111827] bg-[#111827] text-white"
                          : "border-[#E5E5E5] bg-white text-[#4B5563] hover:bg-[#F3F3F3]"
                      }`}
                    >
                      {lvl}
                    </button>
                  ))}
                </div>
              </div>
            </Card>

            {/* SUBMIT BUTTON */}
            <div className="pt-2 text-center space-y-2">
              <Button
                variant="primary"
                size="lg"
                isLoading={isSubmitting}
                onClick={handleSubmitAndAssess}
                className="w-full sm:w-80 py-3 text-sm font-semibold rounded-lg shadow-sm"
              >
                <span>Submit profile & assess my skills</span>
                <ArrowRight size={15} strokeWidth={1.75} />
              </Button>
              <p className="text-xs text-[#6B7280] max-w-md mx-auto">
                Saves your profile, registers initial competency baselines, and benchmarks your skills against the {activeRole} framework.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================================= */}
      {/* 2. FULL ASSESSMENT RESULTS DASHBOARD VIEW */}
      {/* ======================================================================= */}
      {viewState === "assessed" && completionResult && assessmentResult && (
        <div className="space-y-6">
          {/* Top Summary Card */}
          <div className="border border-[#E5E5E5] rounded-xl p-6 bg-white shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-6">
            <div className="space-y-1">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-medium">
                <CheckCircle2 size={13} strokeWidth={2} className="text-emerald-600" />
                <span>Profile saved & assessed</span>
              </div>
              <h2 className="text-xl font-semibold text-[#111827] tracking-tight">
                {completionResult.full_name || fullName || "Candidate"}&apos;s career assessment
              </h2>
              <p className="text-xs text-[#6B7280]">
                Target role: <strong className="text-[#111827] font-medium">{completionResult.target_role}</strong> ({completionResult.target_level})
              </p>
            </div>

            <div className="flex items-center gap-6 sm:border-l sm:border-[#E5E5E5] sm:pl-6">
              <div className="text-center">
                <span className="text-[11px] text-[#6B7280] uppercase font-medium block">Overall match</span>
                <span className="text-3xl font-bold text-[#111827]">
                  {completionResult.overall_match_score}%
                </span>
              </div>
              <div>
                <span className="text-[11px] text-[#6B7280] uppercase font-medium block">Readiness status</span>
                <Badge variant="default" size="md" className="mt-1 font-medium">
                  {completionResult.readiness_status}
                </Badge>
              </div>
            </div>
          </div>

          {/* 4 Metrics Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Card className="p-4 text-center">
              <span className="text-xs text-[#6B7280] block">Overall match</span>
              <span className="text-2xl font-bold text-[#111827] mt-1 block">
                {completionResult.overall_match_score}%
              </span>
              <span className="text-[11px] text-[#6B7280] mt-0.5 block">Role competency coverage</span>
            </Card>

            <Card className="p-4 text-center">
              <span className="text-xs text-[#6B7280] block">Skills identified</span>
              <span className="text-2xl font-bold text-[#111827] mt-1 block">
                {assessmentResult.skills_identified_count}
              </span>
              <span className="text-[11px] text-[#6B7280] mt-0.5 block">From submitted profile</span>
            </Card>

            <Card className="p-4 text-center">
              <span className="text-xs text-[#6B7280] block">Strong skills</span>
              <span className="text-2xl font-bold text-[#065F46] mt-1 block">
                {strongSkills.length}
              </span>
              <span className="text-[11px] text-[#6B7280] mt-0.5 block">Evidenced & matched</span>
            </Card>

            <Card className="p-4 text-center">
              <span className="text-xs text-[#6B7280] block">Skill gaps</span>
              <span className="text-2xl font-bold text-[#991B1B] mt-1 block">
                {missingSkills.length}
              </span>
              <span className="text-[11px] text-[#6B7280] mt-0.5 block">Prioritized for roadmap</span>
            </Card>
          </div>

          {/* 3-Column Breakdown */}
          <Card className="p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-[#F0F0F0] pb-3">
              <div>
                <h3 className="text-sm font-semibold text-[#111827]">Competency breakdown</h3>
                <p className="text-xs text-[#6B7280] mt-0.5">
                  Comparison against {completionResult.target_role} benchmark framework.
                </p>
              </div>
              <Badge variant="default" size="sm">Evidence-aware</Badge>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Strong */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-[#065F46] uppercase tracking-wider">
                    Strong skills ({strongSkills.length})
                  </h4>
                  <Badge variant="success" size="sm">Matched</Badge>
                </div>
                <div className="space-y-2">
                  {strongSkills.length > 0 ? (
                    strongSkills.map((item, idx) => (
                      <div key={idx} className="p-2.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA]">
                        <p className="text-xs font-medium text-[#111827]">{item.skill}</p>
                        <p className="text-[11px] text-[#6B7280] mt-0.5">
                          Level: {item.candidate_level_title} • {item.category}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-[#6B7280] italic">No direct matches identified yet.</p>
                  )}
                </div>
              </div>

              {/* To Improve */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-[#92400E] uppercase tracking-wider">
                    Skills to improve ({skillsToImprove.length})
                  </h4>
                  <Badge variant="warning" size="sm">Partial</Badge>
                </div>
                <div className="space-y-2">
                  {skillsToImprove.length > 0 ? (
                    skillsToImprove.map((item, idx) => (
                      <div key={idx} className="p-2.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA]">
                        <p className="text-xs font-medium text-[#111827]">{item.skill}</p>
                        <p className="text-[11px] text-[#6B7280] mt-0.5">
                          Candidate: {item.candidate_level_title} (Target: {item.required_level_title})
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-[#6B7280] italic">No partial matches.</p>
                  )}
                </div>
              </div>

              {/* Missing */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold text-[#991B1B] uppercase tracking-wider">
                    Missing skills ({missingSkills.length})
                  </h4>
                  <Badge variant="danger" size="sm">Gap</Badge>
                </div>
                <div className="space-y-2">
                  {missingSkills.length > 0 ? (
                    missingSkills.map((item, idx) => (
                      <div key={idx} className="p-2.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA]">
                        <p className="text-xs font-medium text-[#111827]">{item.skill}</p>
                        <p className="text-[11px] text-[#6B7280] mt-0.5">
                          Required target: {item.required_level_title}
                        </p>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-[#6B7280] italic">No major competency gaps.</p>
                  )}
                </div>
              </div>
            </div>

            <div className="text-[11px] text-[#6B7280] border-t border-[#F0F0F0] pt-3 flex items-center gap-1.5">
              <AlertCircle size={13} strokeWidth={1.75} className="shrink-0" />
              <span>{assessmentResult.disclaimer}</span>
            </div>
          </Card>

          {/* Submitted Profile Review */}
          <Card className="p-6 space-y-4">
            <div className="border-b border-[#F0F0F0] pb-3 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-[#111827]">Submitted profile details</h3>
                <p className="text-xs text-[#6B7280] mt-0.5">
                  Profile data saved and registered for your personalized learning roadmap.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setViewState("form")}
                className="text-xs text-[#111827] hover:underline font-medium"
              >
                Edit profile & re-assess
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="p-3.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] space-y-2">
                <span className="font-semibold text-[#111827] block">Candidate details</span>
                <div className="space-y-1 text-[#374151]">
                  <p><span className="text-[#6B7280]">Name:</span> {fullName || "Not provided"}</p>
                  <p><span className="text-[#6B7280]">Email:</span> {email || "Not provided"}</p>
                  <p><span className="text-[#6B7280]">Phone:</span> {phone || "Not provided"}</p>
                  <p><span className="text-[#6B7280]">Target role:</span> {completionResult.target_role} ({completionResult.target_level})</p>
                </div>
                {summary && (
                  <div className="pt-2 border-t border-[#E5E5E5]">
                    <span className="text-[#6B7280] font-medium block mb-0.5">Summary:</span>
                    <p className="text-[#4B5563] leading-relaxed">{summary}</p>
                  </div>
                )}
              </div>

              <div className="p-3.5 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] space-y-2">
                <span className="font-semibold text-[#111827] block">Education & experience</span>
                <div className="space-y-1 text-[#374151]">
                  <p><span className="text-[#6B7280]">Degree:</span> {educationLevel || "Not provided"}</p>
                  <p><span className="text-[#6B7280]">Institution:</span> {institution || "Not provided"}</p>
                  <p><span className="text-[#6B7280]">Graduation:</span> {graduationYear || "Not provided"}</p>
                  <p><span className="text-[#6B7280]">Current role:</span> {currentRole || "Not provided"}</p>
                  <p><span className="text-[#6B7280]">Company:</span> {currentCompany || "Not provided"}</p>
                  <p><span className="text-[#6B7280]">Experience:</span> {yearsOfExperience} years</p>
                </div>
              </div>
            </div>

            {/* Submitted Skills */}
            <div className="space-y-2 pt-1">
              <span className="text-xs font-semibold text-[#111827] block">
                Submitted skills ({skillsList.length}):
              </span>
              <div className="flex flex-wrap gap-1.5">
                {skillsList.map((s, idx) => (
                  <span key={idx} className="px-2.5 py-0.5 rounded-md bg-[#FAFAFA] border border-[#E5E5E5] text-[#374151] text-xs">
                    {s.skill}
                  </span>
                ))}
              </div>
            </div>
          </Card>

          {/* CTA Banner */}
          <div className="p-6 rounded-xl border border-[#E5E5E5] bg-[#FAFAFA] text-center space-y-3">
            <h3 className="text-base font-semibold text-[#111827]">Your personalized learning path is ready</h3>
            <p className="text-xs text-[#6B7280] max-w-lg mx-auto leading-relaxed">
              An adaptive learning roadmap has been synthesized to address your specific competency gaps for {completionResult.target_role}.
            </p>
            <div className="pt-2 flex flex-wrap gap-3 justify-center items-center">
              <Link href="/paths">
                <Button variant="primary" size="md">
                  <span>Start my personalized learning path</span>
                  <ArrowRight size={14} strokeWidth={1.75} />
                </Button>
              </Link>
              <Link href="/tutor">
                <Button variant="secondary" size="md">
                  <BookOpen size={14} strokeWidth={1.75} />
                  <span>Ask AI tutor</span>
                </Button>
              </Link>
              <Link href="/competency">
                <Button variant="outline" size="md">
                  <BarChart3 size={14} strokeWidth={1.75} />
                  <span>Competency dashboard</span>
                </Button>
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
