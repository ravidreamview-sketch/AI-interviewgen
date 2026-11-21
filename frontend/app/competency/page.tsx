"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/LoadingSkeleton";
import { apiClient } from "@/lib/api/client";
import {
  CompetencyDashboardData,
  SkillCompetencyItem,
  RoleBenchmarkGap,
} from "@/lib/types";
import {
  ShieldCheck,
  TrendingUp,
  AlertTriangle,
  Award,
  BookOpen,
  Code2,
  Mic,
  FolderGit2,
  CheckCircle2,
  ArrowRight,
  Info,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

export default function CompetencyIntelligenceDashboard() {
  const [data, setData] = useState<CompetencyDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "matrix" | "evidence" | "recommendations">("overview");
  const [skillFilter, setSkillFilter] = useState<"all" | "multi_source_verified" | "assessed" | "self_reported">("all");
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await apiClient<CompetencyDashboardData>("/api/v1/competency/dashboard");
      setData(res);
    } catch (err: any) {
      setError(err.message || "Failed to load competency intelligence dashboard.");
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto py-8 px-4">
        <LoadingSkeleton className="h-40 rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <LoadingSkeleton className="h-24 rounded-xl" />
          <LoadingSkeleton className="h-24 rounded-xl" />
          <LoadingSkeleton className="h-24 rounded-xl" />
          <LoadingSkeleton className="h-24 rounded-xl" />
        </div>
        <LoadingSkeleton className="h-96 rounded-xl" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto py-8 px-4">
        <EmptyState
          title="Could Not Load Competency Intelligence"
          description={error || "Ensure your backend is running and you are authenticated."}
          actionLabel="Retry Loading"
          onAction={fetchDashboardData}
        />
      </div>
    );
  }

  const { readiness, role_gaps, skills, recommendations } = data;

  const filteredSkills = skills.filter((s) => {
    if (skillFilter === "all") return true;
    return s.verification_status === skillFilter;
  });

  const getTierVariant = (level: number): "neutral" | "info" | "default" | "success" | "warning" => {
    switch (level) {
      case 5:
        return "success";
      case 4:
        return "info";
      case 3:
        return "default";
      case 2:
        return "warning";
      default:
        return "neutral";
    }
  };

  const getGapStatusBadge = (gap: RoleBenchmarkGap) => {
    switch (gap.status) {
      case "met":
        return <Badge variant="success" size="sm">Met (+{gap.gap_delta} pts)</Badge>;
      case "near_benchmark":
        return <Badge variant="warning" size="sm">Near Target ({gap.gap_delta} pts)</Badge>;
      case "critical_gap":
        return <Badge variant="danger" size="sm">Critical Gap ({gap.gap_delta} pts)</Badge>;
      case "missing_evidence":
        return <Badge variant="neutral" size="sm">Missing Evidence</Badge>;
    }
  };

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 space-y-6 pb-12">
      {/* 1. Header Banner */}
      <div className="bg-white border border-[#E5E5E5] rounded-xl p-6 shadow-xs relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="neutral" size="sm" className="font-semibold uppercase tracking-wider">
                Competency Intelligence
              </Badge>
              <Badge variant="neutral" size="sm">
                Target: {readiness.target_role} ({readiness.target_level})
              </Badge>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-[#111827]">
              Competency Intelligence Dashboard
            </h1>
            <p className="mt-1 text-xs text-[#6B7280] leading-relaxed">
              Consolidated, evidence-backed evaluation across learner self-reports, baseline assessments,
              real-world code challenges, mock interviews, and technical portfolio projects. Zero fabricated scores.
            </p>
          </div>

          {/* Readiness Score Card */}
          <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl p-4 flex items-center gap-5 shrink-0 shadow-xs">
            <div className="relative w-18 h-18 flex items-center justify-center">
              <svg className="w-16 h-16 transform -rotate-90" viewBox="0 0 36 36">
                <path
                  className="text-[#E5E5E5]"
                  strokeWidth="3.5"
                  stroke="currentColor"
                  fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                <path
                  className={
                    readiness.readiness_index >= 75
                      ? "text-emerald-600"
                      : readiness.readiness_index >= 55
                      ? "text-amber-600"
                      : "text-rose-600"
                  }
                  strokeDasharray={`${readiness.readiness_index}, 100`}
                  strokeWidth="3.5"
                  strokeLinecap="round"
                  stroke="currentColor"
                  fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
              </svg>
              <div className="absolute text-center">
                <span className="text-lg font-bold text-[#111827]">{readiness.readiness_index}</span>
                <span className="text-[10px] block text-[#6B7280] -mt-1">/ 100</span>
              </div>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wider text-[#6B7280] font-semibold">Career Readiness</p>
              <p className="text-sm font-semibold text-[#111827]">{readiness.readiness_tier}</p>
              <p className="text-[11px] text-[#6B7280] mt-0.5">
                Evidence Coverage: <span className="text-[#111827] font-medium">{readiness.overall_coverage_pct}%</span>
              </p>
            </div>
          </div>
        </div>

        {/* Multi-Source Evidence Coverage Track */}
        <div className="mt-5 pt-4 border-t border-[#F0F0F0] grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg p-2.5">
            <div className="flex items-center justify-between text-xs text-[#6B7280]">
              <span className="flex items-center gap-1.5"><BookOpen className="w-3.5 h-3.5 text-[#111827]" /> Profile</span>
              <span className="font-semibold text-[#111827]">{readiness.evidence_coverage.profile_completed ? "100%" : "0%"}</span>
            </div>
            <div className="w-full bg-[#E5E5E5] h-1.5 rounded-full mt-2 overflow-hidden">
              <div className={`h-full rounded-full ${readiness.evidence_coverage.profile_completed ? "bg-[#111827] w-full" : "w-0"}`} />
            </div>
          </div>

          <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg p-2.5">
            <div className="flex items-center justify-between text-xs text-[#6B7280]">
              <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> Assessed</span>
              <span className="font-semibold text-[#111827]">{readiness.evidence_coverage.assessed_skills_count} Skills</span>
            </div>
            <div className="w-full bg-[#E5E5E5] h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-[#111827] h-full rounded-full"
                style={{ width: `${Math.min(100, readiness.evidence_coverage.assessed_skills_count * 20)}%` }}
              />
            </div>
          </div>

          <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg p-2.5">
            <div className="flex items-center justify-between text-xs text-[#6B7280]">
              <span className="flex items-center gap-1.5"><Code2 className="w-3.5 h-3.5 text-blue-600" /> Scenarios</span>
              <span className="font-semibold text-[#111827]">{readiness.evidence_coverage.scenarios_evaluated_count} Solved</span>
            </div>
            <div className="w-full bg-[#E5E5E5] h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-[#111827] h-full rounded-full"
                style={{ width: `${Math.min(100, readiness.evidence_coverage.scenarios_evaluated_count * 33)}%` }}
              />
            </div>
          </div>

          <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg p-2.5">
            <div className="flex items-center justify-between text-xs text-[#6B7280]">
              <span className="flex items-center gap-1.5"><Mic className="w-3.5 h-3.5 text-amber-600" /> Interviews</span>
              <span className="font-semibold text-[#111827]">{readiness.evidence_coverage.interviews_completed_count} Sessions</span>
            </div>
            <div className="w-full bg-[#E5E5E5] h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-[#111827] h-full rounded-full"
                style={{ width: `${Math.min(100, readiness.evidence_coverage.interviews_completed_count * 33)}%` }}
              />
            </div>
          </div>

          <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg p-2.5">
            <div className="flex items-center justify-between text-xs text-[#6B7280]">
              <span className="flex items-center gap-1.5"><FolderGit2 className="w-3.5 h-3.5 text-indigo-600" /> Projects</span>
              <span className="font-semibold text-[#111827]">{readiness.evidence_coverage.projects_mentored_count} Portfolio</span>
            </div>
            <div className="w-full bg-[#E5E5E5] h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className="bg-[#111827] h-full rounded-full"
                style={{ width: `${Math.min(100, readiness.evidence_coverage.projects_mentored_count * 50)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 2. Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-[#E5E5E5] pb-3 overflow-x-auto">
        <Button
          variant={activeTab === "overview" ? "primary" : "outline"}
          size="sm"
          onClick={() => setActiveTab("overview")}
        >
          <Award className="w-3.5 h-3.5 mr-1.5" /> Overview & Benchmarks
        </Button>
        <Button
          variant={activeTab === "matrix" ? "primary" : "outline"}
          size="sm"
          onClick={() => setActiveTab("matrix")}
        >
          <ShieldCheck className="w-3.5 h-3.5 mr-1.5" /> Skill Evidence Matrix ({skills.length})
        </Button>
        <Button
          variant={activeTab === "evidence" ? "primary" : "outline"}
          size="sm"
          onClick={() => setActiveTab("evidence")}
        >
          <BookOpen className="w-3.5 h-3.5 mr-1.5" /> Multi-Source Evidence Timeline
        </Button>
        <Button
          variant={activeTab === "recommendations" ? "primary" : "outline"}
          size="sm"
          onClick={() => setActiveTab("recommendations")}
        >
          <TrendingUp className="w-3.5 h-3.5 mr-1.5" /> Targeted Recommendations
        </Button>
      </div>

      {/* 3. Tab: Overview & Benchmarks */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Role Benchmark Visualizer */}
          <Card title={`Role Benchmark Gaps: ${readiness.target_role}`} subtitle={`Comparative analysis against ${readiness.target_level} benchmark expectations.`}>
            <div className="space-y-3">
              {role_gaps.map((gap) => {
                const pct = Math.min(100, gap.candidate_score);
                const benchPct = Math.min(100, gap.target_benchmark_score);
                return (
                  <div key={gap.skill} className="p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl space-y-2">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-xs text-[#111827]">{gap.skill}</span>
                          <span className="text-[10px] text-[#6B7280] bg-white border border-[#E5E5E5] px-2 py-0.5 rounded">
                            {gap.category}
                          </span>
                        </div>
                        <p className="text-xs text-[#6B7280] mt-0.5">
                          Candidate: <span className="font-medium text-[#111827]">{gap.candidate_score} pts</span> / Benchmark: {gap.target_benchmark_score} pts
                        </p>
                      </div>
                      <div>{getGapStatusBadge(gap)}</div>
                    </div>

                    {/* Dual Benchmark Bar */}
                    <div className="space-y-1">
                      <div className="relative w-full bg-[#E5E5E5] h-2 rounded-full overflow-hidden">
                        {/* Target Marker */}
                        <div
                          className="absolute top-0 bottom-0 border-r-2 border-[#111827] z-10 opacity-70"
                          style={{ left: `${benchPct}%` }}
                          title={`Target Benchmark: ${gap.target_benchmark_score}`}
                        />
                        {/* Candidate Fill */}
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            gap.candidate_score >= gap.target_benchmark_score
                              ? "bg-emerald-600"
                              : gap.candidate_score >= gap.target_benchmark_score - 15
                              ? "bg-amber-600"
                              : "bg-rose-600"
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-[10px] text-[#9CA3AF]">
                        <span>0</span>
                        <span style={{ marginLeft: `${benchPct - 5}%` }}>Target: {gap.target_benchmark_score}</span>
                        <span>100</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Missing Evidence & Contributing Factors Split */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="Missing Evidence Checklist" subtitle="Identified gaps in empirical demonstration required for high-confidence readiness.">
              {readiness.missing_evidence.length === 0 ? (
                <div className="flex items-center gap-2.5 p-3.5 bg-emerald-50/60 border border-emerald-200 rounded-xl text-emerald-800 text-xs">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>All critical evidence streams have empirical demonstration.</span>
                </div>
              ) : (
                <ul className="space-y-2">
                  {readiness.missing_evidence.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-2.5 p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg text-xs text-[#374151]">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Contributing Evidence Factors" subtitle="Evidence factors actively influencing your current readiness index.">
              <div className="space-y-2.5">
                {readiness.contributing_factors.positive.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-2 p-2.5 bg-emerald-50/60 border border-emerald-200 rounded-lg text-xs text-emerald-800">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                    <span>{item}</span>
                  </div>
                ))}
                {readiness.contributing_factors.risk_areas.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-2 p-2.5 bg-rose-50/60 border border-rose-200 rounded-lg text-xs text-rose-800">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-600 shrink-0 mt-0.5" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* Disclaimer Alert */}
          <div className="p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl flex items-start gap-3 text-xs text-[#6B7280]">
            <Info className="w-4 h-4 text-[#111827] shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-[#111827] mb-0.5">Objective Readiness Governance</p>
              <p>{readiness.readiness_disclaimer}</p>
            </div>
          </div>
        </div>
      )}

      {/* 4. Tab: Skill Evidence Matrix */}
      {activeTab === "matrix" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant={skillFilter === "all" ? "primary" : "outline"}
                size="sm"
                onClick={() => setSkillFilter("all")}
              >
                All Skills ({skills.length})
              </Button>
              <Button
                variant={skillFilter === "multi_source_verified" ? "primary" : "outline"}
                size="sm"
                onClick={() => setSkillFilter("multi_source_verified")}
              >
                Multi-Source Verified ({skills.filter((s) => s.verification_status === "multi_source_verified").length})
              </Button>
              <Button
                variant={skillFilter === "assessed" ? "primary" : "outline"}
                size="sm"
                onClick={() => setSkillFilter("assessed")}
              >
                Assessed ({skills.filter((s) => s.verification_status === "assessed").length})
              </Button>
              <Button
                variant={skillFilter === "self_reported" ? "primary" : "outline"}
                size="sm"
                onClick={() => setSkillFilter("self_reported")}
              >
                Self-Reported ({skills.filter((s) => s.verification_status === "self_reported").length})
              </Button>
            </div>
          </div>

          <Card title="Skill Inventory & Evidence Source Matrix" subtitle="Evidence breakdown distinguishing self-reports from empirical evaluations.">
            <div className="space-y-2.5">
              {filteredSkills.map((sk) => {
                const isExpanded = expandedSkill === sk.skill_name;
                const tierVariant = getTierVariant(sk.competency_tier.level);
                return (
                  <div key={sk.skill_name} className="bg-white border border-[#E5E5E5] rounded-xl p-3.5 transition-colors shadow-xs">
                    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="font-semibold text-xs text-[#111827]">{sk.skill_name}</h4>
                          <Badge variant={tierVariant} size="sm">
                            Tier {sk.competency_tier.level}: {sk.competency_tier.name}
                          </Badge>
                          {sk.verification_status === "multi_source_verified" && (
                            <Badge variant="success" size="sm" className="font-semibold">
                              Multi-Source Verified
                            </Badge>
                          )}
                          {sk.verification_status === "assessed" && (
                            <Badge variant="info" size="sm">
                              Assessed
                            </Badge>
                          )}
                          {sk.verification_status === "self_reported" && (
                            <Badge variant="neutral" size="sm">
                              Unverified Self-Report
                            </Badge>
                          )}
                          {sk.open_mistakes_count > 0 && (
                            <Badge variant="danger" size="sm">
                              {sk.open_mistakes_count} Open Mistake(s)
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-[#6B7280] mt-0.5">
                          Empirical Score: <span className="font-semibold text-[#111827]">{sk.overall_score} pts</span> • Trend: <span className="capitalize text-[#374151]">{sk.trend}</span>
                        </p>
                      </div>

                      {/* Evidence Source Stream Badges */}
                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1.5 text-[10px]">
                          <span className={`px-2 py-0.5 rounded border ${sk.evidence_sources.self_reported ? "bg-[#F3F4F6] border-[#D1D5DB] text-[#111827]" : "bg-white border-[#E5E5E5] text-[#9CA3AF]"}`}>
                            Profile
                          </span>
                          <span className={`px-2 py-0.5 rounded border ${sk.evidence_sources.assessed ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-white border-[#E5E5E5] text-[#9CA3AF]"}`}>
                            Assessed
                          </span>
                          <span className={`px-2 py-0.5 rounded border ${sk.evidence_sources.scenario ? "bg-blue-50 border-blue-200 text-blue-800" : "bg-white border-[#E5E5E5] text-[#9CA3AF]"}`}>
                            Scenario
                          </span>
                          <span className={`px-2 py-0.5 rounded border ${sk.evidence_sources.interview ? "bg-amber-50 border-amber-200 text-amber-800" : "bg-white border-[#E5E5E5] text-[#9CA3AF]"}`}>
                            Interview
                          </span>
                          <span className={`px-2 py-0.5 rounded border ${sk.evidence_sources.project ? "bg-indigo-50 border-indigo-200 text-indigo-800" : "bg-white border-[#E5E5E5] text-[#9CA3AF]"}`}>
                            Project
                          </span>
                        </div>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setExpandedSkill(isExpanded ? null : sk.skill_name)}
                        >
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </Button>
                      </div>
                    </div>

                    {/* Drill-down Drawer */}
                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t border-[#F0F0F0] text-xs space-y-3 bg-[#FAFAFA] p-3 rounded-lg">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <p className="font-semibold text-[#111827] mb-0.5">Self-Reported Evidence:</p>
                            {sk.evidence_sources.self_reported ? (
                              <p className="text-[#6B7280]">
                                Claimed Level: <span className="text-[#111827]">{sk.evidence_sources.self_reported.claimed_level}</span> (Est. score: {sk.evidence_sources.self_reported.estimated_score} pts)
                              </p>
                            ) : (
                              <p className="text-[#9CA3AF] italic">No self-report entry in candidate profile.</p>
                            )}
                          </div>

                          <div>
                            <p className="font-semibold text-[#111827] mb-0.5">Assessment Analytics:</p>
                            {sk.evidence_sources.assessed ? (
                              <p className="text-[#6B7280]">
                                Assessment Score: <span className="text-[#111827]">{sk.evidence_sources.assessed.score} pts</span> • Confidence: {sk.evidence_sources.assessed.confidence} • Evidence Items: {sk.evidence_sources.assessed.evidence_count}
                              </p>
                            ) : (
                              <p className="text-[#9CA3AF] italic">No baseline quiz or technical assessment recorded.</p>
                            )}
                          </div>
                        </div>

                        {sk.evidence_sources.scenario && sk.evidence_sources.scenario.length > 0 && (
                          <div>
                            <p className="font-semibold text-[#111827] mb-0.5">Scenario Submissions Evaluated:</p>
                            <div className="space-y-0.5">
                              {sk.evidence_sources.scenario.map((sub, idx) => (
                                <p key={idx} className="text-[#6B7280]">
                                  • {sub.scenario_title} — Score: <span className="text-[#111827] font-medium">{sub.score} pts</span> ({sub.status})
                                </p>
                              ))}
                            </div>
                          </div>
                        )}

                        {sk.evidence_sources.project && sk.evidence_sources.project.length > 0 && (
                          <div>
                            <p className="font-semibold text-[#111827] mb-0.5">Portfolio Project Implementation:</p>
                            <div className="space-y-0.5">
                              {sk.evidence_sources.project.map((p, idx) => (
                                <p key={idx} className="text-[#6B7280]">
                                  • {p.title} ({p.status}) — Mentorship Turns: {p.mentorship_turns_count} (Stages: {p.stages_engaged.join(", ") || "Planning"})
                                </p>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      )}

      {/* 5. Tab: Evidence Timeline */}
      {activeTab === "evidence" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="Scenario Evaluations" subtitle="Practical real-world code challenge submissions evaluated against rubrics.">
              {data.scenario_evidence.length === 0 ? (
                <p className="text-xs text-[#9CA3AF] italic p-4 text-center">No scenario code submissions evaluated yet.</p>
              ) : (
                <div className="space-y-2">
                  {data.scenario_evidence.map((s, idx) => (
                    <div key={idx} className="p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg flex items-center justify-between">
                      <div>
                        <p className="font-medium text-xs text-[#111827]">{s.scenario_title}</p>
                        <p className="text-[11px] text-[#6B7280]">Status: <span className="capitalize text-[#374151]">{s.status}</span></p>
                      </div>
                      <Badge variant={s.overall_score >= 80 ? "success" : "warning"} size="sm">
                        {s.overall_score} pts
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Mock Interview Transcripts" subtitle="Multi-turn interview simulations evaluated for technical accuracy & STAR depth.">
              {data.interview_evidence.length === 0 ? (
                <p className="text-xs text-[#9CA3AF] italic p-4 text-center">No mock interview sessions completed yet.</p>
              ) : (
                <div className="space-y-2">
                  {data.interview_evidence.map((inv, idx) => (
                    <div key={idx} className="p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg flex items-center justify-between">
                      <div>
                        <p className="font-medium text-xs text-[#111827]">{inv.role}</p>
                        <p className="text-[11px] text-[#6B7280]">Interviewer: {inv.interviewer_persona} • Accuracy: {inv.technical_accuracy}%</p>
                      </div>
                      <Badge variant={inv.score >= 80 ? "success" : "warning"} size="sm">
                        {inv.score} pts
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="Portfolio Projects & Mentorship" subtitle="Verified project milestones and architectural mentorship turns.">
              {data.project_evidence.length === 0 ? (
                <p className="text-xs text-[#9CA3AF] italic p-4 text-center">No portfolio projects registered yet.</p>
              ) : (
                <div className="space-y-2">
                  {data.project_evidence.map((p, idx) => (
                    <div key={idx} className="p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg flex items-center justify-between">
                      <div>
                        <p className="font-medium text-xs text-[#111827]">{p.title}</p>
                        <p className="text-[11px] text-[#6B7280]">Domain: {p.domain} • Status: {p.status}</p>
                      </div>
                      <Badge variant="info" size="sm">
                        {p.mentorship_turns_count} Turn(s)
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Active Curriculum Progression" subtitle="Adaptive roadmap completion and AI Socratic tutor engagement.">
              <div className="p-4 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[#6B7280]">Roadmap:</span>
                  <span className="font-semibold text-[#111827]">{data.learning_progress.roadmap_title || "None Active"}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[#6B7280]">Activities Completed:</span>
                  <span className="font-semibold text-[#111827]">
                    {data.learning_progress.completed_activities_count} / {data.learning_progress.total_activities_count}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[#6B7280]">AI Tutor Sessions:</span>
                  <span className="font-semibold text-[#111827]">{data.learning_progress.tutor_sessions_count} Sessions</span>
                </div>
                <div className="w-full bg-[#E5E5E5] h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-[#111827] h-full rounded-full"
                    style={{ width: `${data.learning_progress.overall_progress_pct}%` }}
                  />
                </div>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* 6. Tab: Targeted Recommendations */}
      {activeTab === "recommendations" && (
        <div className="space-y-6">
          <Card title="Priority Focus Areas" subtitle="Skills with largest target role benchmark gaps or open mistake records.">
            <div className="flex flex-wrap gap-2">
              {recommendations.skills_to_improve.map((sk) => (
                <Badge key={sk} variant="danger" size="md" className="font-semibold">
                  {sk}
                </Badge>
              ))}
            </div>
          </Card>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="Recommended Learning Activities" subtitle="Connected directly to your active adaptive roadmap.">
              <div className="space-y-2.5">
                {recommendations.learning_activities.map((act, idx) => (
                  <div key={idx} className="p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                    <div>
                      <p className="font-semibold text-xs text-[#111827]">{act.title}</p>
                      <p className="text-[11px] text-[#6B7280] mt-0.5">Focus Skill: {act.skill}</p>
                    </div>
                    <Link href={act.action_url}>
                      <Button variant="outline" size="sm">
                        Resume <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    </Link>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Recommended Scenario Challenges" subtitle="Connected directly to real-world scenario challenges.">
              <div className="space-y-2.5">
                {recommendations.scenarios.map((sc, idx) => (
                  <div key={idx} className="p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-semibold text-xs text-[#111827]">{sc.title}</p>
                        <Badge variant="warning" size="sm">{sc.difficulty}</Badge>
                      </div>
                      <p className="text-[11px] text-[#6B7280] mt-0.5">Category: {sc.category}</p>
                    </div>
                    <Link href={sc.action_url}>
                      <Button variant="outline" size="sm">
                        Start <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    </Link>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="Recommended Project Mentorship" subtitle="Connected directly to portfolio project reviews.">
              <div className="space-y-2.5">
                {recommendations.projects.map((proj, idx) => (
                  <div key={idx} className="p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                    <div>
                      <p className="font-semibold text-xs text-[#111827]">{proj.title}</p>
                      <p className="text-[11px] text-[#6B7280] mt-0.5">Stage: <span className="capitalize">{proj.stage}</span> • {proj.focus}</p>
                    </div>
                    <Link href={proj.action_url}>
                      <Button variant="outline" size="sm">
                        Consult Mentor <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    </Link>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Recommended Mock Interview Simulation" subtitle="Connected directly to adaptive mock interview studio.">
              <div className="p-4 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl space-y-3">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-xs text-[#111827]">{recommendations.interview_practice.role}</p>
                    <Badge variant="info" size="sm">{recommendations.interview_practice.interview_type}</Badge>
                  </div>
                  <p className="text-xs text-[#6B7280] mt-1">{recommendations.interview_practice.recommended_focus}</p>
                </div>
                <Link href={recommendations.interview_practice.action_url}>
                  <Button variant="primary" size="sm" className="w-full mt-2">
                    Launch Targeted Interview <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                  </Button>
                </Link>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
