"use client";

import React, { useState, useEffect } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/LoadingSkeleton";
import { apiClient } from "@/lib/api/client";
import { LearnerProfile, SkillGap, CompetencyItem } from "@/lib/types";
import { Plus, RefreshCw, AlertCircle, CheckCircle2, ShieldAlert, X } from "lucide-react";

export default function LearnerIntelligencePage() {
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [gaps, setGaps] = useState<SkillGap[]>([]);
  const [matrix, setMatrix] = useState<CompetencyItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "matrix" | "gaps">("overview");

  // Self-report modal state
  const [showSelfReportModal, setShowSelfReportModal] = useState(false);
  const [skillInput, setSkillInput] = useState("");
  const [levelInput, setLevelInput] = useState(3);
  const [notesInput, setNotesInput] = useState("");

  useEffect(() => {
    fetchProfileAndData();
  }, []);

  async function fetchProfileAndData() {
    setIsLoading(true);
    try {
      const profileData = await apiClient<LearnerProfile>("/api/v1/learners/profile");
      setProfile(profileData);

      const [gapsData, matrixData] = await Promise.all([
        apiClient<SkillGap[]>("/api/v1/learners/skill-gaps"),
        apiClient<CompetencyItem[]>("/api/v1/learners/competency-matrix"),
      ]);
      setGaps(gapsData);
      setMatrix(matrixData);
    } catch (err) {
      console.error("Failed to load learner data:", err);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleResumeSync() {
    setIsSyncing(true);
    try {
      await apiClient("/api/v1/learners/sync-resume", { method: "POST" });
      await fetchProfileAndData();
    } catch (err: any) {
      alert(err.message || "Resume sync failed. Ensure a resume has been scanned.");
    } finally {
      setIsSyncing(false);
    }
  }

  async function handleAddSelfReportedSkill(e: React.FormEvent) {
    e.preventDefault();
    if (!skillInput.trim()) return;

    try {
      await apiClient("/api/v1/learners/skills/self-report", {
        method: "POST",
        body: JSON.stringify({
          skill: skillInput.trim(),
          level: Number(levelInput),
          notes: notesInput.trim() || undefined,
        }),
      });
      setShowSelfReportModal(false);
      setSkillInput("");
      setNotesInput("");
      await fetchProfileAndData();
    } catch (err: any) {
      alert(err.message || "Failed to record skill.");
    }
  }

  const getPriorityBadgeVariant = (priority: string) => {
    switch (priority) {
      case "CRITICAL": return "danger";
      case "HIGH": return "warning";
      case "MODERATE": return "info";
      case "LOW": return "neutral";
      case "ON_TRACK": return "success";
      default: return "default";
    }
  };

  const getEvidenceBadgeVariant = (type: string) => {
    switch (type) {
      case "VERIFIED": return "success";
      case "ASSESSED": return "info";
      case "SELF_REPORTED": return "warning";
      default: return "neutral";
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto">
        <LoadingSkeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <LoadingSkeleton className="h-44" />
          <LoadingSkeleton className="h-44" />
          <LoadingSkeleton className="h-44" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-[#E5E5E5] pb-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-[#111827]">
            Learner intelligence profile
          </h1>
          <p className="text-xs text-[#6B7280] mt-0.5">
            Unified competency framework, multi-source evidence verification, and deterministic gap analysis.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowSelfReportModal(true)}
          >
            <Plus size={13} strokeWidth={1.75} />
            <span>Add self-reported skill</span>
          </Button>
          <Button
            variant="primary"
            size="sm"
            isLoading={isSyncing}
            onClick={handleResumeSync}
          >
            <RefreshCw size={13} strokeWidth={1.75} />
            <span>Sync resume evidence</span>
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#E5E5E5] space-x-6 text-xs font-medium">
        <button
          onClick={() => setActiveTab("overview")}
          className={`pb-3 transition-colors border-b-2 ${
            activeTab === "overview"
              ? "border-[#111827] text-[#111827] font-semibold"
              : "border-transparent text-[#6B7280] hover:text-[#111827]"
          }`}
        >
          Profile & baseline
        </button>
        <button
          onClick={() => setActiveTab("gaps")}
          className={`pb-3 transition-colors border-b-2 ${
            activeTab === "gaps"
              ? "border-[#111827] text-[#111827] font-semibold"
              : "border-transparent text-[#6B7280] hover:text-[#111827]"
          }`}
        >
          Skill gap analysis ({gaps.filter(g => g.priority !== "ON_TRACK").length} gaps)
        </button>
        <button
          onClick={() => setActiveTab("matrix")}
          className={`pb-3 transition-colors border-b-2 ${
            activeTab === "matrix"
              ? "border-[#111827] text-[#111827] font-semibold"
              : "border-transparent text-[#6B7280] hover:text-[#111827]"
          }`}
        >
          Role competency matrix ({profile?.target_role})
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Target Role & Career Goals */}
            <Card title="Target role & goals">
              <div className="space-y-3">
                <div>
                  <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider block">Target role</span>
                  <p className="text-sm font-semibold text-[#111827] mt-0.5">{profile?.target_role || "Not set"}</p>
                </div>
                <div>
                  <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider block">Target level</span>
                  <p className="text-xs font-medium text-[#374151] mt-0.5">{profile?.target_level || "Mid-Level"}</p>
                </div>
                <div>
                  <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider block">Career goals</span>
                  <p className="text-xs text-[#4B5563] mt-0.5 leading-relaxed">
                    {profile?.career_goals || "Declare target roles and career vision to prioritize training."}
                  </p>
                </div>
              </div>
            </Card>

            {/* Education & Background */}
            <Card title="Education & experience">
              <div className="space-y-3">
                <div>
                  <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider block">Years of experience</span>
                  <p className="text-sm font-semibold text-[#111827] mt-0.5">{profile?.years_of_experience || 0} years</p>
                </div>
                <div>
                  <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider block">Current position</span>
                  <p className="text-xs text-[#4B5563] mt-0.5">
                    {profile?.current_role ? `${profile.current_role} at ${profile.current_company || "N/A"}` : "None specified"}
                  </p>
                </div>
                <div>
                  <span className="text-[11px] font-medium text-[#6B7280] uppercase tracking-wider block">Education</span>
                  <p className="text-xs text-[#4B5563] mt-0.5">
                    {profile?.education_level || "Not specified"} {profile?.institution ? `(${profile.institution})` : ""}
                  </p>
                </div>
              </div>
            </Card>

            {/* Evidence Breakdown */}
            <Card title="Evidence breakdown">
              <div className="space-y-2.5">
                <div className="flex justify-between items-center py-1 border-b border-[#F0F0F0] text-xs">
                  <span className="text-[#6B7280]">Verified (interviews & code):</span>
                  <Badge variant="success" size="sm">{gaps.filter(g => g.evidence_type === "VERIFIED").length}</Badge>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-[#F0F0F0] text-xs">
                  <span className="text-[#6B7280]">Assessed (analytics baseline):</span>
                  <Badge variant="info" size="sm">{gaps.filter(g => g.evidence_type === "ASSESSED").length}</Badge>
                </div>
                <div className="flex justify-between items-center py-1 border-b border-[#F0F0F0] text-xs">
                  <span className="text-[#6B7280]">Self-reported (unverified):</span>
                  <Badge variant="warning" size="sm">{Object.keys(profile?.self_reported_skills || {}).length}</Badge>
                </div>
                <div className="flex justify-between items-center py-1 text-xs">
                  <span className="text-[#6B7280]">Not evidenced:</span>
                  <Badge variant="neutral" size="sm">{gaps.filter(g => g.evidence_type === "NOT_EVIDENCED").length}</Badge>
                </div>
              </div>
            </Card>
          </div>

          {/* Assessed Skills Baseline Table */}
          <Card title="Assessed competency baseline" subtitle="Derived from interview performance and objective scoring.">
            {profile?.assessed_skills && profile.assessed_skills.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#E5E5E5] text-[#6B7280] font-medium uppercase tracking-wider text-[11px]">
                      <th className="pb-2.5">Skill</th>
                      <th className="pb-2.5">Score</th>
                      <th className="pb-2.5">Proficiency tier</th>
                      <th className="pb-2.5">Confidence</th>
                      <th className="pb-2.5">Trend</th>
                      <th className="pb-2.5">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#F0F0F0]">
                    {profile.assessed_skills.map((s, idx) => (
                      <tr key={idx} className="hover:bg-[#FAFAFA]">
                        <td className="py-2.5 font-medium text-[#111827]">{s.skill}</td>
                        <td className="py-2.5 text-[#374151]">{s.score}%</td>
                        <td className="py-2.5">
                          <Badge variant="default" size="sm">Level {s.level}: {s.level_title}</Badge>
                        </td>
                        <td className="py-2.5">
                          <Badge variant={s.confidence === "HIGH" ? "success" : s.confidence === "MEDIUM" ? "warning" : "neutral"} size="sm">
                            {s.confidence}
                          </Badge>
                        </td>
                        <td className="py-2.5 text-[#6B7280] capitalize">{s.trend}</td>
                        <td className="py-2.5 text-[#6B7280] capitalize">{s.weakness_status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No assessment baseline yet"
                description="Complete an AI mock interview or real-world practice scenario to establish your verified competency baseline."
              />
            )}
          </Card>
        </div>
      )}

      {/* Skill Gaps Tab */}
      {activeTab === "gaps" && (
        <Card
          title="Skill gap prioritization"
          subtitle={`Comparing demonstrated competence against ${profile?.target_role} requirements.`}
        >
          {gaps.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#E5E5E5] text-[#6B7280] font-medium uppercase tracking-wider text-[11px]">
                    <th className="pb-2.5">Skill</th>
                    <th className="pb-2.5">Category</th>
                    <th className="pb-2.5">Current level</th>
                    <th className="pb-2.5">Target level</th>
                    <th className="pb-2.5">Gap</th>
                    <th className="pb-2.5">Priority</th>
                    <th className="pb-2.5">Evidence type</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#F0F0F0]">
                  {gaps.map((g, idx) => (
                    <tr key={idx} className="hover:bg-[#FAFAFA]">
                      <td className="py-2.5">
                        <div className="font-medium text-[#111827]">{g.skill}</div>
                        <div className="text-[11px] text-[#6B7280] max-w-xs truncate">{g.description}</div>
                      </td>
                      <td className="py-2.5 text-[#4B5563]">{g.category}</td>
                      <td className="py-2.5 text-[#374151]">
                        {g.current_level > 0 ? `L${g.current_level} (${g.current_level_title})` : "None"}
                      </td>
                      <td className="py-2.5 text-[#111827] font-medium">
                        L{g.target_level} ({g.target_level_title})
                      </td>
                      <td className="py-2.5 font-semibold text-[#111827]">
                        {g.gap_level > 0 ? `-${g.gap_level} level${g.gap_level > 1 ? "s" : ""}` : "Met"}
                      </td>
                      <td className="py-2.5">
                        <Badge variant={getPriorityBadgeVariant(g.priority)} size="sm">
                          {g.priority}
                        </Badge>
                      </td>
                      <td className="py-2.5">
                        <Badge variant={getEvidenceBadgeVariant(g.evidence_type)} size="sm">
                          {g.evidence_type}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No skill gaps found"
              description="Your demonstrated skills fully meet or exceed the target role framework."
            />
          )}
        </Card>
      )}

      {/* Role Competency Matrix Tab */}
      {activeTab === "matrix" && (
        <Card
          title={`Competency matrix: ${profile?.target_role}`}
          subtitle="Curated expectations and standard proficiency tiers required for production mastery."
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {matrix.map((item, idx) => (
              <div key={idx} className="p-4 rounded-lg bg-[#FAFAFA] border border-[#E5E5E5] space-y-2">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-semibold text-xs text-[#111827]">{item.skill}</h4>
                    <span className="text-[11px] text-[#6B7280]">{item.category}</span>
                  </div>
                  <Badge variant="default" size="sm">Level {item.target_level} ({item.target_level_title})</Badge>
                </div>
                <p className="text-xs text-[#4B5563] leading-relaxed">{item.description}</p>
                <div className="text-[11px] text-[#6B7280]">
                  Criticality weight: {(item.role_criticality * 100).toFixed(0)}%
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Add Self-Reported Skill Modal */}
      {showSelfReportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white border border-[#E5E5E5] rounded-xl max-w-md w-full p-6 space-y-4 shadow-lg">
            <div className="flex items-center justify-between border-b border-[#F0F0F0] pb-3">
              <h3 className="text-sm font-semibold text-[#111827]">Add self-reported skill</h3>
              <button
                type="button"
                onClick={() => setShowSelfReportModal(false)}
                className="text-[#6B7280] hover:text-[#111827]"
              >
                <X size={16} strokeWidth={1.75} />
              </button>
            </div>

            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-start gap-2">
              <ShieldAlert size={14} strokeWidth={1.75} className="shrink-0 mt-0.5 text-amber-600" />
              <span>Self-reported skills provide learning direction but are strictly marked as unverified until evaluated in an assessment or interview.</span>
            </div>

            <form onSubmit={handleAddSelfReportedSkill} className="space-y-3.5">
              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">Skill name</label>
                <input
                  type="text"
                  required
                  value={skillInput}
                  onChange={(e) => setSkillInput(e.target.value)}
                  placeholder="e.g. Distributed Caching, Kubernetes, Go"
                  className="w-full px-3 py-2 bg-white border border-[#E5E5E5] rounded-lg text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">Declared proficiency</label>
                <select
                  value={levelInput}
                  onChange={(e) => setLevelInput(Number(e.target.value))}
                  className="w-full px-3 py-2 bg-white border border-[#E5E5E5] rounded-lg text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                >
                  <option value={1}>Level 1: Beginner (Foundational syntax/concepts)</option>
                  <option value={2}>Level 2: Basic (Routine tasks with supervision)</option>
                  <option value={3}>Level 3: Intermediate (Independent feature delivery)</option>
                  <option value={4}>Level 4: Advanced (Optimization, scale, concurrency)</option>
                  <option value={5}>Level 5: Expert (System architect, best practices)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">Notes / context (optional)</label>
                <textarea
                  value={notesInput}
                  onChange={(e) => setNotesInput(e.target.value)}
                  placeholder="e.g. 2 years usage on production services"
                  rows={3}
                  className="w-full p-2.5 bg-white border border-[#E5E5E5] rounded-lg text-xs text-[#111827] focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-900"
                />
              </div>

              <div className="flex justify-end gap-2.5 pt-2 border-t border-[#F0F0F0]">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowSelfReportModal(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary" size="sm">
                  Record skill
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
