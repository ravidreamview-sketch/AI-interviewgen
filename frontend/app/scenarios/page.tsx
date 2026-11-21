"use client";

import React, { useState, useEffect } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/LoadingSkeleton";
import { apiClient } from "@/lib/api/client";
import { ScenarioDetail, SubmissionEvaluation } from "@/lib/types";
import {
  Sparkles,
  CheckCircle2,
  Clock,
  ArrowRight,
  Info,
  Check,
  AlertTriangle,
  FileText,
  Code2,
  ListOrdered,
} from "lucide-react";

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<ScenarioDetail[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<ScenarioDetail | null>(null);
  const [submissions, setSubmissions] = useState<SubmissionEvaluation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  // Submission Form State
  const [solutionText, setSolutionText] = useState("");
  const [codeSubmission, setCodeSubmission] = useState("");
  const [architecturalNotes, setArchitecturalNotes] = useState("");
  const [activeTab, setActiveTab] = useState<"brief" | "workspace" | "evaluations">("brief");

  useEffect(() => {
    fetchScenarios();
  }, []);

  useEffect(() => {
    if (selectedScenario) {
      fetchSubmissions(selectedScenario.scenario_id);
    }
  }, [selectedScenario]);

  async function fetchScenarios() {
    setIsLoading(true);
    try {
      const data = await apiClient<ScenarioDetail[]>("/api/v1/scenarios/list");
      setScenarios(data);
      if (data.length > 0 && !selectedScenario) {
        setSelectedScenario(data[0]);
      }
    } catch (err) {
      console.error("Failed to load scenarios:", err);
    } finally {
      setIsLoading(false);
    }
  }

  async function fetchSubmissions(scenarioId: string) {
    try {
      const data = await apiClient<SubmissionEvaluation[]>(`/api/v1/scenarios/${scenarioId}/submissions`);
      setSubmissions(data);
      if (data.length > 0) {
        setActiveTab("evaluations");
      }
    } catch (err) {
      console.error("Failed to load submissions:", err);
    }
  }

  async function handleGenerateNewScenario() {
    setIsGenerating(true);
    try {
      const newScen = await apiClient<ScenarioDetail>("/api/v1/scenarios/generate", {
        method: "POST",
        body: JSON.stringify({}),
      });
      setScenarios((prev) => [newScen, ...prev]);
      setSelectedScenario(newScen);
      setActiveTab("brief");
    } catch (err: any) {
      alert(err.message || "Failed to generate scenario.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleSubmitSolution(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedScenario || !solutionText.trim()) return;

    setIsSubmitting(true);
    try {
      const evalResult = await apiClient<SubmissionEvaluation>(
        `/api/v1/scenarios/${selectedScenario.scenario_id}/submit`,
        {
          method: "POST",
          body: JSON.stringify({
            solution_text: solutionText.trim(),
            code_submission: codeSubmission.trim() || undefined,
            architectural_notes: architecturalNotes.trim() || undefined,
          }),
        }
      );
      setSubmissions((prev) => [evalResult, ...prev]);
      setActiveTab("evaluations");
      // Update scenario completed state in list
      await fetchScenarios();
    } catch (err: any) {
      alert(err.message || "Failed to submit solution.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const getDifficultyBadgeVariant = (diff: string) => {
    switch (diff) {
      case "Expert": return "danger";
      case "Advanced": return "warning";
      case "Intermediate": return "info";
      default: return "default";
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto py-8 px-4">
        <LoadingSkeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <LoadingSkeleton className="h-96" />
          <LoadingSkeleton className="h-96 lg:col-span-2" />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-[#111827]">
              Real-World Scenario Studio
            </h1>
          </div>
          <p className="text-sm text-[#6B7280] mt-1">
            Production case studies, broken codebase challenges, and automated rubric evaluations.
          </p>
        </div>
        <div>
          <Button
            variant="primary"
            size="sm"
            isLoading={isGenerating}
            onClick={handleGenerateNewScenario}
          >
            <Sparkles className="w-3.5 h-3.5 mr-1.5" /> Generate Personalized Challenge
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 min-h-[680px]">
        {/* Scenario Discovery Sidebar */}
        <div className="lg:col-span-1 border border-[#E5E5E5] rounded-xl bg-white p-4 space-y-4 flex flex-col h-[680px] shadow-xs">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[#6B7280]">
            Available Challenges ({scenarios.length})
          </h2>

          <div className="space-y-2 overflow-y-auto flex-1 pr-1">
            {scenarios.map((scen) => (
              <div
                key={scen.scenario_id}
                onClick={() => {
                  setSelectedScenario(scen);
                  setActiveTab("brief");
                }}
                className={`p-3 rounded-lg cursor-pointer transition-all border ${selectedScenario?.scenario_id === scen.scenario_id
                  ? "border-[#111827] bg-[#F7F7F7] text-[#111827]"
                  : "border-[#E5E5E5] bg-white text-[#374151] hover:bg-[#F9FAFB]"
                  }`}
              >
                <div className="flex items-center justify-between text-xs mb-1">
                  <Badge variant={getDifficultyBadgeVariant(scen.difficulty)} size="sm">
                    {scen.difficulty}
                  </Badge>
                  {scen.is_completed ? (
                    <span className="text-xs text-emerald-700 font-semibold flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Passed
                    </span>
                  ) : (
                    <span className="text-[11px] text-[#6B7280] capitalize">
                      {scen.category.replace(/_/g, " ")}
                    </span>
                  )}
                </div>
                <h4 className="font-medium text-xs text-[#111827] line-clamp-2">{scen.title}</h4>
                <div className="text-[11px] text-[#6B7280] mt-1">{scen.domain}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Challenge Detail & Submission Area */}
        <div className="lg:col-span-2 border border-[#E5E5E5] rounded-xl bg-white flex flex-col h-[680px] shadow-xs overflow-hidden">
          {selectedScenario ? (
            <>
              {/* Header Bar */}
              <div className="p-4 border-b border-[#E5E5E5] bg-[#FAFAFA] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="info" size="sm">{selectedScenario.domain}</Badge>
                    <Badge variant={getDifficultyBadgeVariant(selectedScenario.difficulty)} size="sm">
                      Level {selectedScenario.difficulty_level}: {selectedScenario.difficulty}
                    </Badge>
                  </div>
                  <h3 className="text-base font-semibold text-[#111827] mt-1">
                    {selectedScenario.title}
                  </h3>
                </div>

                {/* Tabs */}
                <div className="flex bg-[#F3F4F6] p-1 rounded-lg shrink-0">
                  <button
                    onClick={() => setActiveTab("brief")}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${activeTab === "brief"
                      ? "bg-white text-[#111827] shadow-xs font-semibold"
                      : "text-[#6B7280] hover:text-[#111827]"
                      }`}
                  >
                    Brief
                  </button>
                  <button
                    onClick={() => setActiveTab("workspace")}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${activeTab === "workspace"
                      ? "bg-white text-[#111827] shadow-xs font-semibold"
                      : "text-[#6B7280] hover:text-[#111827]"
                      }`}
                  >
                    Workspace
                  </button>
                  <button
                    onClick={() => setActiveTab("evaluations")}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${activeTab === "evaluations"
                      ? "bg-white text-[#111827] shadow-xs font-semibold"
                      : "text-[#6B7280] hover:text-[#111827]"
                      }`}
                  >
                    Feedback ({submissions.length})
                  </button>
                </div>
              </div>

              {/* Tab Content Area */}
              <div className="flex-1 p-5 overflow-y-auto space-y-5 bg-white">
                {/* Brief Tab */}
                {activeTab === "brief" && (
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-[#6B7280] mb-1">
                        Context
                      </h4>
                      <p className="text-xs text-[#374151] leading-relaxed bg-[#F9FAFB] p-3.5 rounded-lg border border-[#E5E5E5]">
                        {selectedScenario.context}
                      </p>
                    </div>

                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-[#6B7280] mb-1">
                        Problem Statement
                      </h4>
                      <p className="text-xs font-medium text-[#111827] leading-relaxed bg-[#F9FAFB] p-3.5 rounded-lg border border-[#E5E5E5]">
                        {selectedScenario.problem_statement}
                      </p>
                    </div>

                    {/* Objectives & Constraints */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="p-3.5 bg-[#F9FAFB] border border-[#E5E5E5] rounded-lg">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-[#111827] mb-2 flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-[#2563EB]" /> Objectives
                        </h4>
                        <ul className="space-y-1 text-xs text-[#4B5563] list-disc list-inside">
                          {selectedScenario.objectives.map((obj, i) => (
                            <li key={i}>{obj}</li>
                          ))}
                        </ul>
                      </div>

                      <div className="p-3.5 bg-[#F9FAFB] border border-[#E5E5E5] rounded-lg">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-[#111827] mb-2 flex items-center gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> Technical Constraints
                        </h4>
                        <ul className="space-y-1 text-xs text-[#4B5563] list-disc list-inside">
                          {selectedScenario.constraints.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Evaluation Rubric Preview */}
                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-[#6B7280] mb-2">
                        Tailored Evaluation Rubric
                      </h4>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {Object.entries(selectedScenario.rubric).map(([dim, meta], idx) => (
                          <div key={idx} className="p-3 rounded-lg border border-[#E5E5E5] bg-white space-y-1 shadow-xs">
                            <div className="flex justify-between items-center text-xs">
                              <span className="font-semibold text-[#111827] capitalize">
                                {dim.replace(/_/g, " ")}
                              </span>
                              <Badge variant="neutral" size="sm">{(meta.weight * 100).toFixed(0)}%</Badge>
                            </div>
                            <p className="text-[11px] text-[#6B7280] leading-normal">{meta.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="flex justify-end pt-2">
                      <Button variant="primary" size="sm" onClick={() => setActiveTab("workspace")}>
                        Open Solution Workspace <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    </div>
                  </div>
                )}

                {/* Workspace Tab */}
                {activeTab === "workspace" && (
                  <form onSubmit={handleSubmitSolution} className="space-y-4">
                    <div>
                      <label className="text-xs font-semibold uppercase tracking-wider text-[#374151] block mb-1">
                        Solution Explanation & Architecture Write-up *
                      </label>
                      <textarea
                        required
                        value={solutionText}
                        onChange={(e) => setSolutionText(e.target.value)}
                        placeholder="Detail your solution, architectural trade-offs, concurrency handling, and error recovery..."
                        rows={6}
                        className="w-full bg-white border border-[#E5E5E5] rounded-lg p-3 text-xs text-[#111827] placeholder:text-[#9CA3AF] focus:outline-none focus:border-[#111827]"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-semibold uppercase tracking-wider text-[#374151] block mb-1">
                        Code Implementation (Static Analysis - No Execution)
                      </label>
                      <textarea
                        value={codeSubmission}
                        onChange={(e) => setCodeSubmission(e.target.value)}
                        placeholder="Paste Python, TypeScript, or SQL implementation..."
                        rows={8}
                        className="w-full bg-[#111827] border border-[#374151] rounded-lg p-3 text-xs font-mono text-[#F3F4F6] placeholder:text-[#6B7280] focus:outline-none focus:border-white"
                      />
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                      <Button type="button" variant="outline" size="sm" onClick={() => setActiveTab("brief")}>
                        Back to Brief
                      </Button>
                      <Button type="submit" variant="primary" size="sm" isLoading={isSubmitting}>
                        Submit for Evaluation
                      </Button>
                    </div>
                  </form>
                )}

                {/* Feedback Tab */}
                {activeTab === "evaluations" && (
                  <div className="space-y-4">
                    {submissions.length > 0 ? (
                      submissions.map((sub, sIdx) => (
                        <div key={sIdx} className="p-4 border border-[#E5E5E5] rounded-xl bg-white space-y-4 shadow-xs">
                          <div className="flex items-center justify-between pb-3 border-b border-[#F0F0F0]">
                            <div className="flex items-center gap-3">
                              <span className="text-xl font-bold text-[#111827]">
                                {sub.overall_score}%
                              </span>
                              <Badge variant={sub.status === "passed" ? "success" : "warning"}>
                                {sub.status.toUpperCase()}
                              </Badge>
                            </div>
                            <span className="text-xs text-[#9CA3AF]">
                              Evaluated {new Date(sub.evaluated_at).toLocaleString()}
                            </span>
                          </div>

                          {/* Dimension Scores Bar */}
                          <div>
                            <span className="text-xs text-[#6B7280] uppercase tracking-wider font-semibold block mb-2">
                              Rubric Dimension Scores:
                            </span>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                              {Object.entries(sub.dimension_scores).map(([dName, dScore], dIdx) => (
                                <div key={dIdx} className="p-2.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg">
                                  <div className="text-[11px] text-[#6B7280] capitalize">{dName.replace(/_/g, " ")}</div>
                                  <div className="text-xs font-semibold text-[#111827] mt-0.5">{dScore}%</div>
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Strengths & Improvements */}
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="p-3 bg-emerald-50/60 border border-emerald-200 rounded-lg space-y-1">
                              <h5 className="text-xs font-semibold text-emerald-800 uppercase tracking-wider">Strengths</h5>
                              <ul className="text-xs text-emerald-900 space-y-0.5 list-disc list-inside">
                                {sub.strengths.map((st, i) => (
                                  <li key={i}>{st}</li>
                                ))}
                              </ul>
                            </div>

                            <div className="p-3 bg-amber-50/60 border border-amber-200 rounded-lg space-y-1">
                              <h5 className="text-xs font-semibold text-amber-800 uppercase tracking-wider">Areas for Improvement</h5>
                              <ul className="text-xs text-amber-900 space-y-0.5 list-disc list-inside">
                                {sub.areas_for_improvement.map((imp, i) => (
                                  <li key={i}>{imp}</li>
                                ))}
                              </ul>
                            </div>
                          </div>

                          {/* Evaluator Feedback & Evidence */}
                          <div className="text-xs text-[#374151] bg-[#FAFAFA] p-3 rounded-lg border border-[#E5E5E5] space-y-1.5 leading-relaxed">
                            <div><strong>Evaluator Synthesis:</strong> {sub.feedback}</div>
                            <div><strong>Evidence Grounding:</strong> {sub.evidence}</div>
                          </div>

                          {/* Disclaimer */}
                          <div className="text-[11px] text-[#6B7280] italic flex items-center gap-1.5 pt-1">
                            <Info className="w-3.5 h-3.5 shrink-0" /> {sub.evaluation_disclaimer}
                          </div>
                        </div>
                      ))
                    ) : (
                      <EmptyState
                        title="No Submissions Yet"
                        description="Complete the solution in the workspace tab and submit to view your detailed rubric evaluation."
                        actionLabel="Go to Workspace"
                        onAction={() => setActiveTab("workspace")}
                      />
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full">
              <EmptyState
                title="Select a Challenge"
                description="Choose an industry scenario from the left to start."
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
