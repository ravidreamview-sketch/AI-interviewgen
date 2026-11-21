"use client";

import React, { useState, useEffect } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/LoadingSkeleton";
import { apiClient } from "@/lib/api/client";
import {
  InterviewHistoryItem,
  ProjectItem,
  ProjectMentorshipTurn,
} from "@/lib/types";
import {
  Mic,
  FolderGit2,
  Plus,
  Send,
  ArrowRight,
  CheckCircle2,
  Clock,
  Sparkles,
  X,
  FileCode,
  Layers,
} from "lucide-react";

export default function InterviewMentorPage() {
  const [activeMainTab, setActiveMainTab] = useState<"interview" | "project_mentor">("interview");

  // Interview Studio State
  const [history, setHistory] = useState<InterviewHistoryItem[]>([]);
  const [isStartingInterview, setIsStartingInterview] = useState(false);
  const [activeInterview, setActiveInterview] = useState<any | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [turnIndex, setTurnIndex] = useState(1);
  const [answerInput, setAnswerInput] = useState("");
  const [isSubmittingTurn, setIsSubmittingTurn] = useState(false);
  const [turnFeedback, setTurnFeedback] = useState<any | null>(null);
  const [isInterviewCompleted, setIsInterviewCompleted] = useState(false);

  // Interview Setup Form State
  const [targetRoleInput, setTargetRoleInput] = useState("Full-Stack Engineer");
  const [personaInput, setPersonaInput] = useState("alex");
  const [interviewTypeInput, setInterviewTypeInput] = useState("technical");
  const [questionCountInput, setQuestionCountInput] = useState(3);

  // Project Mentor State
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [selectedProject, setSelectedProject] = useState<ProjectItem | null>(null);
  const [mentorshipTurns, setMentorshipTurns] = useState<ProjectMentorshipTurn[]>([]);
  const [projectStage, setProjectStage] = useState("architecture");
  const [projectQueryInput, setProjectQueryInput] = useState("");
  const [isSendingMentorship, setIsSendingMentorship] = useState(false);

  // Register Project Modal
  const [showProjectModal, setShowProjectModal] = useState(false);
  const [newProjectTitle, setNewProjectTitle] = useState("");
  const [newProjectRole, setNewProjectRole] = useState("Backend Engineer (Python / Cloud)");
  const [newProjectDomain, setNewProjectDomain] = useState("High-Concurrency API Services");
  const [newProjectDesc, setNewProjectDesc] = useState("");
  const [newProjectStack, setNewProjectStack] = useState("Python, FastAPI, PostgreSQL, Redis, Docker");

  useEffect(() => {
    fetchInterviewHistory();
    fetchProjects();
  }, []);

  useEffect(() => {
    if (selectedProject) {
      fetchMentorshipHistory(selectedProject.project_id);
    }
  }, [selectedProject]);

  async function fetchInterviewHistory() {
    try {
      const data = await apiClient<InterviewHistoryItem[]>("/api/v1/interviews/history");
      setHistory(data);
    } catch (err) {
      console.error("Failed to load interview history:", err);
    }
  }

  async function fetchProjects() {
    try {
      const data = await apiClient<ProjectItem[]>("/api/v1/interviews/projects");
      setProjects(data);
      if (data.length > 0 && !selectedProject) {
        setSelectedProject(data[0]);
      }
    } catch (err) {
      console.error("Failed to load projects:", err);
    }
  }

  async function fetchMentorshipHistory(projectId: string) {
    try {
      const data = await apiClient<ProjectMentorshipTurn[]>(`/api/v1/interviews/projects/${projectId}/history`);
      setMentorshipTurns(data);
    } catch (err) {
      console.error("Failed to load mentorship history:", err);
    }
  }

  async function handleStartInterview(e: React.FormEvent) {
    e.preventDefault();
    setIsStartingInterview(true);
    setTurnFeedback(null);
    setIsInterviewCompleted(false);

    try {
      const session = await apiClient<any>("/api/v1/interviews/start", {
        method: "POST",
        body: JSON.stringify({
          role: targetRoleInput,
          persona: personaInput,
          interview_type: interviewTypeInput,
          mode: "text",
          question_count: questionCountInput,
        }),
      });
      setActiveInterview(session);
      setCurrentQuestion(session.first_question);
      setTurnIndex(1);
      setAnswerInput("");
    } catch (err: any) {
      alert(err.message || "Failed to start interview session.");
    } finally {
      setIsStartingInterview(false);
    }
  }

  async function handleSubmitTurn(e: React.FormEvent) {
    e.preventDefault();
    if (!activeInterview || !answerInput.trim()) return;

    setIsSubmittingTurn(true);
    try {
      const res = await apiClient<any>(`/api/v1/interviews/${activeInterview.interview_id}/turn`, {
        method: "POST",
        body: JSON.stringify({
          turn_index: turnIndex,
          candidate_answer: answerInput.trim(),
          is_final: turnIndex >= questionCountInput,
        }),
      });

      setTurnFeedback(res.evaluation);
      if (res.is_complete || !res.next_question) {
        setIsInterviewCompleted(true);
        await fetchInterviewHistory();
      } else {
        setCurrentQuestion(res.next_question);
        setTurnIndex((prev) => prev + 1);
        setAnswerInput("");
      }
    } catch (err: any) {
      alert(err.message || "Failed to evaluate answer.");
    } finally {
      setIsSubmittingTurn(false);
    }
  }

  async function handleRegisterProject(e: React.FormEvent) {
    e.preventDefault();
    if (!newProjectTitle.trim() || !newProjectDesc.trim()) return;

    const stackList = newProjectStack.split(",").map((s) => s.trim()).filter(Boolean);

    try {
      const p = await apiClient<ProjectItem>("/api/v1/interviews/projects", {
        method: "POST",
        body: JSON.stringify({
          title: newProjectTitle.trim(),
          target_role: newProjectRole,
          domain: newProjectDomain,
          description: newProjectDesc.trim(),
          tech_stack: stackList.length > 0 ? stackList : ["Python", "FastAPI"],
        }),
      });
      setShowProjectModal(false);
      setProjects((prev) => [p, ...prev]);
      setSelectedProject(p);
      setNewProjectTitle("");
      setNewProjectDesc("");
    } catch (err: any) {
      alert(err.message || "Failed to register project.");
    }
  }

  async function handleSendMentorship(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedProject || !projectQueryInput.trim()) return;

    setIsSendingMentorship(true);
    const query = projectQueryInput.trim();
    setProjectQueryInput("");

    try {
      await apiClient<any>(`/api/v1/interviews/projects/${selectedProject.project_id}/mentor`, {
        method: "POST",
        body: JSON.stringify({
          stage: projectStage,
          user_query: query,
        }),
      });
      await fetchMentorshipHistory(selectedProject.project_id);
    } catch (err: any) {
      alert(err.message || "Mentorship inquiry failed.");
    } finally {
      setIsSendingMentorship(false);
    }
  }

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-[#111827]">
              AI Interview & Project Mentor
            </h1>
          </div>
          <p className="text-sm text-[#6B7280] mt-1">
            Context-aware conversational interviews, adaptive follow-ups, and portfolio technical project mentorship.
          </p>
        </div>

        {/* Mode Switcher */}
        <div className="flex bg-[#F3F4F6] p-1 rounded-lg shrink-0">
          <button
            onClick={() => setActiveMainTab("interview")}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5 ${
              activeMainTab === "interview"
                ? "bg-white text-[#111827] shadow-xs font-semibold"
                : "text-[#6B7280] hover:text-[#111827]"
            }`}
          >
            <Mic className="w-3.5 h-3.5" /> Mock Interview Studio
          </button>
          <button
            onClick={() => setActiveMainTab("project_mentor")}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5 ${
              activeMainTab === "project_mentor"
                ? "bg-white text-[#111827] shadow-xs font-semibold"
                : "text-[#6B7280] hover:text-[#111827]"
            }`}
          >
            <FolderGit2 className="w-3.5 h-3.5" /> Portfolio Project Mentor
          </button>
        </div>
      </div>

      {/* TAB 1: MOCK INTERVIEW STUDIO */}
      {activeMainTab === "interview" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Launcher & History Pane */}
          <div className="space-y-6">
            <Card title="Start Context-Aware Interview" subtitle="Seeded with your profile and competency gaps.">
              <form onSubmit={handleStartInterview} className="space-y-3.5">
                <div>
                  <label className="text-xs text-[#6B7280] block mb-1">Target Role</label>
                  <input
                    type="text"
                    value={targetRoleInput}
                    onChange={(e) => setTargetRoleInput(e.target.value)}
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-[#6B7280] block mb-1">Interviewer Persona</label>
                    <select
                      value={personaInput}
                      onChange={(e) => setPersonaInput(e.target.value)}
                      className="w-full bg-white border border-[#E5E5E5] rounded-lg px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                    >
                      <option value="alex">Alex (Tech Lead)</option>
                      <option value="elena">Elena (Systems Architect)</option>
                      <option value="marcus">Marcus (VP People / STAR)</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-xs text-[#6B7280] block mb-1">Interview Type</label>
                    <select
                      value={interviewTypeInput}
                      onChange={(e) => setInterviewTypeInput(e.target.value)}
                      className="w-full bg-white border border-[#E5E5E5] rounded-lg px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                    >
                      <option value="technical">Technical</option>
                      <option value="system_design">System Design</option>
                      <option value="coding">Coding & Algorithms</option>
                      <option value="behavioral">Behavioral (STAR)</option>
                      <option value="project_based">Project-Based</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="text-xs text-[#6B7280] block mb-1">Question Count</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={questionCountInput}
                    onChange={(e) => setQuestionCountInput(Number(e.target.value))}
                    className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                  />
                </div>

                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  isLoading={isStartingInterview}
                  className="w-full mt-2"
                >
                  <Mic className="w-3.5 h-3.5 mr-1.5" /> Launch Mock Interview
                </Button>
              </form>
            </Card>

            {/* Past Interviews List */}
            <Card title="Past Interview History">
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {history.length > 0 ? (
                  history.map((item, idx) => (
                    <div key={idx} className="p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg text-xs space-y-1">
                      <div className="flex justify-between items-center">
                        <span className="font-semibold text-[#111827]">{item.role}</span>
                        <Badge variant="info" size="sm">{item.score}%</Badge>
                      </div>
                      <div className="text-[11px] text-[#6B7280]">{item.interviewer_persona}</div>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-[#9CA3AF] text-center py-4">No completed interviews yet.</div>
                )}
              </div>
            </Card>
          </div>

          {/* Active Interview Console Pane */}
          <div className="lg:col-span-2">
            <Card className="min-h-[550px] flex flex-col">
              {activeInterview ? (
                <div className="flex-1 flex flex-col justify-between space-y-5">
                  {/* Persona & Turn Bar */}
                  <div className="flex items-center justify-between pb-3 border-b border-[#F0F0F0]">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-full bg-[#F3F4F6] flex items-center justify-center text-[#111827]">
                        <Mic className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="font-semibold text-[#111827] text-sm">
                          {activeInterview.persona?.name} ({activeInterview.persona?.role})
                        </h4>
                        <span className="text-xs text-[#6B7280] capitalize">{activeInterview.mode} mode</span>
                      </div>
                    </div>
                    <Badge variant="info">
                      Question {turnIndex} of {questionCountInput}
                    </Badge>
                  </div>

                  {/* Question Box */}
                  <div className="p-4 bg-[#F9FAFB] border border-[#E5E5E5] rounded-xl space-y-1.5">
                    <span className="text-xs text-[#6B7280] uppercase tracking-wider font-semibold block">
                      Current Question
                    </span>
                    <p className="text-sm text-[#111827] leading-relaxed font-medium">
                      {currentQuestion}
                    </p>
                  </div>

                  {/* Feedback Preview (if turn completed) */}
                  {turnFeedback && (
                    <div className="p-4 bg-emerald-50/60 border border-emerald-200 rounded-xl space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-emerald-800 uppercase tracking-wider font-semibold">
                          Turn Evaluation & Competency Mapping
                        </span>
                        {turnFeedback.competency_tier && (
                          <Badge variant="success">
                            Level {turnFeedback.competency_tier.level}: {turnFeedback.competency_tier.title}
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-emerald-900 leading-relaxed">
                        {turnFeedback.summary || turnFeedback.feedback || "Answer evaluated with STAR alignment and technical depth."}
                      </p>
                    </div>
                  )}

                  {/* Candidate Answer Form */}
                  {!isInterviewCompleted ? (
                    <form onSubmit={handleSubmitTurn} className="space-y-3">
                      <div>
                        <label className="text-xs font-semibold text-[#374151] block mb-1">Your Answer</label>
                        <textarea
                          required
                          value={answerInput}
                          onChange={(e) => setAnswerInput(e.target.value)}
                          placeholder="Structure using STAR: Situation, Task, Action, and Result. Include architectural trade-offs..."
                          rows={6}
                          className="w-full bg-white border border-[#E5E5E5] rounded-lg p-3 text-xs text-[#111827] placeholder:text-[#9CA3AF] focus:outline-none focus:border-[#111827]"
                        />
                      </div>

                      <div className="flex justify-end gap-3">
                        <Button
                          type="submit"
                          variant="primary"
                          size="sm"
                          isLoading={isSubmittingTurn}
                        >
                          Submit Answer <ArrowRight className="w-3.5 h-3.5 ml-1" />
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <div className="p-6 text-center space-y-3 border border-emerald-200 rounded-xl bg-emerald-50/50">
                      <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto" />
                      <h3 className="text-base font-bold text-emerald-900">Interview Session Completed</h3>
                      <p className="text-xs text-emerald-800 max-w-md mx-auto">
                        All planned questions evaluated. Your verified competency baseline has been updated.
                      </p>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => setActiveInterview(null)}
                      >
                        Start New Session
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex items-center justify-center h-full my-auto">
                  <EmptyState
                    title="Mock Interview Console Ready"
                    description="Configure your target role and persona on the left, then click 'Launch Mock Interview'."
                  />
                </div>
              )}
            </Card>
          </div>
        </div>
      )}

      {/* TAB 2: AI PROJECT MENTOR */}
      {activeMainTab === "project_mentor" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Projects Sidebar */}
          <div className="border border-[#E5E5E5] rounded-xl bg-white p-4 space-y-4 flex flex-col h-[650px] shadow-xs">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[#6B7280]">
                Portfolio Projects ({projects.length})
              </h2>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowProjectModal(true)}
              >
                <Plus className="w-3.5 h-3.5 mr-1" /> Register Project
              </Button>
            </div>

            <div className="space-y-2 overflow-y-auto flex-1 pr-1">
              {projects.length > 0 ? (
                projects.map((proj) => (
                  <div
                    key={proj.project_id}
                    onClick={() => setSelectedProject(proj)}
                    className={`p-3 rounded-lg cursor-pointer transition-all border ${
                      selectedProject?.project_id === proj.project_id
                        ? "border-[#111827] bg-[#F7F7F7] text-[#111827]"
                        : "border-[#E5E5E5] bg-white text-[#374151] hover:bg-[#F9FAFB]"
                    }`}
                  >
                    <div className="flex justify-between items-center text-xs mb-1">
                      <Badge variant="info" size="sm">{proj.domain}</Badge>
                      <span className="text-[11px] text-[#6B7280] capitalize">{proj.status.replace(/_/g, " ")}</span>
                    </div>
                    <h4 className="font-semibold text-xs text-[#111827]">{proj.title}</h4>
                    <p className="text-xs text-[#6B7280] line-clamp-2 mt-1">{proj.description}</p>
                  </div>
                ))
              ) : (
                <div className="text-xs text-[#9CA3AF] text-center py-8">
                  No projects registered. Register a project to receive technical mentoring!
                </div>
              )}
            </div>
          </div>

          {/* Mentorship Console Area */}
          <div className="lg:col-span-2 border border-[#E5E5E5] rounded-xl bg-white flex flex-col h-[650px] shadow-xs overflow-hidden">
            {selectedProject ? (
              <>
                {/* Project Header Bar */}
                <div className="p-3.5 border-b border-[#E5E5E5] bg-[#FAFAFA] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-sm text-[#111827]">{selectedProject.title}</h3>
                    <div className="flex gap-2 text-xs text-[#6B7280] mt-0.5">
                      <span>Stack: {selectedProject.tech_stack.join(", ")}</span>
                    </div>
                  </div>

                  {/* Stage Selector */}
                  <select
                    value={projectStage}
                    onChange={(e) => setProjectStage(e.target.value)}
                    className="bg-white border border-[#E5E5E5] rounded-lg px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                  >
                    <option value="planning">Planning & Scope</option>
                    <option value="requirements">Requirements & Contracts</option>
                    <option value="architecture">Architecture Guidance</option>
                    <option value="debugging">Debugging & Profiling</option>
                    <option value="design_review">Code & Design Review</option>
                    <option value="presentation_prep">Interview Presentation Prep</option>
                  </select>
                </div>

                {/* Mentorship Guidance Stream */}
                <div className="flex-1 p-5 overflow-y-auto space-y-4 bg-white">
                  {mentorshipTurns.length > 0 ? (
                    mentorshipTurns.map((turn, tIdx) => (
                      <div key={tIdx} className="space-y-3 p-4 rounded-xl border border-[#E5E5E5] bg-white shadow-xs">
                        <div className="flex justify-between items-center text-xs pb-2 border-b border-[#F0F0F0]">
                          <Badge variant="info" size="sm">
                            {turn.mentorship_stage.toUpperCase()}
                          </Badge>
                          <span className="text-[11px] text-[#9CA3AF]">
                            {new Date(turn.created_at).toLocaleTimeString()}
                          </span>
                        </div>

                        <div className="text-xs text-[#4B5563] bg-[#FAFAFA] p-2.5 rounded-lg border border-[#E5E5E5]">
                          <strong>Your Question:</strong> {turn.user_query}
                        </div>

                        <div className="text-xs text-[#111827] leading-relaxed whitespace-pre-wrap">
                          {turn.mentor_guidance}
                        </div>

                        {turn.action_items.length > 0 && (
                          <div className="pt-2 border-t border-[#F0F0F0]">
                            <span className="text-[11px] font-semibold text-[#111827] uppercase tracking-wider block mb-1">
                              Action Items:
                            </span>
                            <ul className="text-xs text-[#4B5563] space-y-1 list-disc list-inside">
                              {turn.action_items.map((act, aIdx) => (
                                <li key={aIdx}>{act}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    ))
                  ) : (
                    <EmptyState
                      title="AI Project Mentor Ready"
                      description="Ask about database architecture, concurrency trade-offs, or preparing your pitch for interviewers."
                    />
                  )}
                </div>

                {/* Question Input */}
                <form onSubmit={handleSendMentorship} className="p-3.5 border-t border-[#E5E5E5] bg-[#FAFAFA] flex gap-2">
                  <input
                    type="text"
                    required
                    value={projectQueryInput}
                    onChange={(e) => setProjectQueryInput(e.target.value)}
                    placeholder={`Ask about ${projectStage.replace(/_/g, ' ')} for ${selectedProject.title}...`}
                    className="flex-1 bg-white border border-[#E5E5E5] rounded-lg px-3.5 py-2 text-xs text-[#111827] placeholder:text-[#9CA3AF] focus:outline-none focus:border-[#111827]"
                  />
                  <Button type="submit" variant="primary" size="sm" isLoading={isSendingMentorship}>
                    <Send className="w-3.5 h-3.5 mr-1" /> Ask Mentor
                  </Button>
                </form>
              </>
            ) : (
              <div className="flex items-center justify-center h-full my-auto">
                <EmptyState
                  title="Select or Register a Project"
                  description="Choose a project on the left or register a new portfolio project."
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Register Project Modal */}
      {showProjectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-xs p-4">
          <div className="bg-white border border-[#E5E5E5] rounded-xl max-w-lg w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-[#111827]">Register Portfolio Project</h3>
              <button
                onClick={() => setShowProjectModal(false)}
                className="text-[#6B7280] hover:text-[#111827]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleRegisterProject} className="space-y-3.5">
              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">Project Title</label>
                <input
                  type="text"
                  required
                  value={newProjectTitle}
                  onChange={(e) => setNewProjectTitle(e.target.value)}
                  placeholder="e.g. Distributed Task Orchestrator"
                  className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">Target Role</label>
                <input
                  type="text"
                  required
                  value={newProjectRole}
                  onChange={(e) => setNewProjectRole(e.target.value)}
                  className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">Domain</label>
                <input
                  type="text"
                  value={newProjectDomain}
                  onChange={(e) => setNewProjectDomain(e.target.value)}
                  className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">Tech Stack (comma separated)</label>
                <input
                  type="text"
                  value={newProjectStack}
                  onChange={(e) => setNewProjectStack(e.target.value)}
                  className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-[#374151] block mb-1">Description & Problem Solved</label>
                <textarea
                  required
                  rows={3}
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  placeholder="Explain the real-world problem, user workload, or architectural challenge..."
                  className="w-full bg-white border border-[#E5E5E5] rounded-lg p-2.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <Button type="button" variant="outline" size="sm" onClick={() => setShowProjectModal(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" size="sm">
                  Register Project
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
