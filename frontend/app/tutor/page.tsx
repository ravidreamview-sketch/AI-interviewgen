"use client";

import React, { useState, useEffect, useRef } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/LoadingSkeleton";
import { apiClient } from "@/lib/api/client";
import {
  TutorSessionItem,
  TutorMessageItem,
  TutorResponse,
} from "@/lib/types";
import {
  BookOpen,
  Plus,
  Send,
  Code2,
  X,
  MessageSquare,
  Sparkles,
} from "lucide-react";

export default function AiTutorPage() {
  const [sessions, setSessions] = useState<TutorSessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<TutorMessageItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);

  // Form states
  const [conceptInput, setConceptInput] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [showCodeDrawer, setShowCodeDrawer] = useState(false);
  const [teachingMode, setTeachingMode] = useState<"explain" | "demonstrate" | "hint" | "challenge" | "solution">("explain");
  const [complexityLevel, setComplexityLevel] = useState<"simple" | "standard" | "deep_dive">("standard");

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchSessions();
  }, []);

  useEffect(() => {
    if (activeSessionId) {
      fetchMessages(activeSessionId);
    } else {
      setMessages([]);
    }
  }, [activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function fetchSessions() {
    setIsLoading(true);
    try {
      const data = await apiClient<TutorSessionItem[]>("/api/v1/tutor/sessions");
      setSessions(data);
      if (data.length > 0 && !activeSessionId) {
        setActiveSessionId(data[0].session_id);
        setConceptInput(data[0].concept);
        setTeachingMode(data[0].teaching_mode);
        setComplexityLevel(data[0].complexity_level);
      }
    } catch (err) {
      console.error("Failed to load tutor sessions:", err);
    } finally {
      setIsLoading(false);
    }
  }

  async function fetchMessages(sessionId: string) {
    try {
      const data = await apiClient<TutorMessageItem[]>(`/api/v1/tutor/sessions/${sessionId}/messages`);
      setMessages(data);
    } catch (err) {
      console.error("Failed to load messages:", err);
    }
  }

  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!queryInput.trim()) return;

    const concept = conceptInput.trim() || "Technical Concept";
    const currentQuery = queryInput.trim();
    const currentCode = codeInput.trim() || undefined;

    setIsSending(true);
    setQueryInput("");

    // Optimistic user message
    const tempUserMsg: TutorMessageItem = {
      id: Date.now(),
      role: "user",
      content: currentQuery,
      code_snippet: currentCode,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const res = await apiClient<TutorResponse>("/api/v1/tutor/query", {
        method: "POST",
        body: JSON.stringify({
          concept,
          query: currentQuery,
          code_context: currentCode,
          session_id: activeSessionId || undefined,
          teaching_mode: teachingMode,
          complexity_level: complexityLevel,
        }),
      });

      // Update active session ID if this was a new session
      if (!activeSessionId) {
        setActiveSessionId(res.session_id);
        await fetchSessions();
      } else {
        await fetchMessages(res.session_id);
      }
    } catch (err: any) {
      alert(err.message || "Tutor query failed.");
    } finally {
      setIsSending(false);
    }
  }

  function handleStartNewSession() {
    setActiveSessionId(null);
    setMessages([]);
    setConceptInput("");
    setQueryInput("");
    setCodeInput("");
    setShowCodeDrawer(false);
    setTeachingMode("explain");
    setComplexityLevel("standard");
  }

  const getModeBadgeVariant = (mode: string) => {
    switch (mode) {
      case "hint": return "warning";
      case "demonstrate": return "info";
      case "challenge": return "danger";
      case "solution": return "success";
      default: return "default";
    }
  };

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-[#111827]">
              AI Socratic Tutor
            </h1>
          </div>
          <p className="text-sm text-[#6B7280] mt-1">
            Context-aware Socratic mentoring, guided problem solving, and static code debugging assistance.
          </p>
        </div>
        <div>
          <Button variant="primary" size="sm" onClick={handleStartNewSession}>
            <Plus className="w-3.5 h-3.5 mr-1.5" /> New Dialogue
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 min-h-[650px]">
        {/* Sessions Sidebar */}
        <div className="lg:col-span-1 border border-[#E5E5E5] rounded-xl bg-white p-4 space-y-4 flex flex-col h-[650px] shadow-xs">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[#6B7280]">
              Recent Sessions ({sessions.length})
            </h2>
          </div>

          <div className="space-y-2 overflow-y-auto flex-1 pr-1">
            {isLoading ? (
              <div className="space-y-2">
                <LoadingSkeleton className="h-14" />
                <LoadingSkeleton className="h-14" />
                <LoadingSkeleton className="h-14" />
              </div>
            ) : sessions.length > 0 ? (
              sessions.map((sess) => (
                <div
                  key={sess.session_id}
                  onClick={() => {
                    setActiveSessionId(sess.session_id);
                    setConceptInput(sess.concept);
                    setTeachingMode(sess.teaching_mode);
                    setComplexityLevel(sess.complexity_level);
                  }}
                  className={`p-3 rounded-lg cursor-pointer transition-all border ${activeSessionId === sess.session_id
                    ? "border-[#111827] bg-[#F7F7F7] text-[#111827]"
                    : "border-[#E5E5E5] bg-white text-[#374151] hover:bg-[#F9FAFB]"
                    }`}
                >
                  <div className="flex items-center justify-between text-xs mb-1">
                    <Badge variant={getModeBadgeVariant(sess.teaching_mode)} size="sm">
                      {sess.teaching_mode.toUpperCase()}
                    </Badge>
                    <span className="text-[11px] text-[#9CA3AF]">
                      {sess.message_count} turns
                    </span>
                  </div>
                  <h4 className="font-medium text-xs truncate">{sess.concept}</h4>
                </div>
              ))
            ) : (
              <div className="text-xs text-[#9CA3AF] text-center py-8">
                No previous sessions. Start a new question!
              </div>
            )}
          </div>
        </div>

        {/* Chat Thread Area */}
        <div className="lg:col-span-3 border border-[#E5E5E5] rounded-xl bg-white flex flex-col h-[650px] shadow-xs overflow-hidden">
          {/* Controls Bar */}
          <div className="p-3.5 border-b border-[#E5E5E5] bg-[#FAFAFA] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex-1">
              <input
                type="text"
                value={conceptInput}
                onChange={(e) => setConceptInput(e.target.value)}
                placeholder="Target Concept (e.g. Asyncio Event Loops, SQL Indexing, JWT Defenses)"
                className="w-full bg-white border border-[#E5E5E5] rounded-lg px-3 py-1.5 text-xs text-[#111827] placeholder:text-[#9CA3AF] focus:outline-none focus:border-[#111827]"
              />
            </div>

            {/* Mode & Depth Selectors */}
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={teachingMode}
                onChange={(e: any) => setTeachingMode(e.target.value)}
                className="bg-white border border-[#E5E5E5] rounded-lg px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
              >
                <option value="explain">Explain Concept</option>
                <option value="hint">Give Socratic Hint</option>
                <option value="demonstrate">Demonstrate Code</option>
                <option value="challenge">Challenge Me</option>
                <option value="solution">Reveal Solution</option>
              </select>

              <select
                value={complexityLevel}
                onChange={(e: any) => setComplexityLevel(e.target.value)}
                className="bg-white border border-[#E5E5E5] rounded-lg px-2.5 py-1.5 text-xs text-[#111827] focus:outline-none focus:border-[#111827]"
              >
                <option value="simple">Simple (Beginner)</option>
                <option value="standard">Standard (Mid-Level)</option>
                <option value="deep_dive">Deep Dive (Senior)</option>
              </select>
            </div>
          </div>

          {/* Messages Stream */}
          <div className="flex-1 p-5 overflow-y-auto space-y-4 bg-white">
            {messages.length > 0 ? (
              messages.map((m, idx) => (
                <div
                  key={idx}
                  className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"
                    }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[11px] font-semibold text-[#6B7280]">
                      {m.role === "user" ? "You" : "AI Socratic Tutor"}
                    </span>
                    {m.pedagogical_intent && (
                      <Badge variant={getModeBadgeVariant(m.pedagogical_intent)} size="sm">
                        {m.pedagogical_intent.replace(/_/g, " ")}
                      </Badge>
                    )}
                  </div>

                  <div
                    className={`p-3.5 rounded-xl max-w-2xl text-xs leading-relaxed ${m.role === "user"
                      ? "bg-[#111827] text-white rounded-br-none shadow-xs"
                      : "bg-[#F9FAFB] text-[#111827] rounded-bl-none border border-[#E5E5E5] shadow-xs"
                      }`}
                  >
                    <div className="whitespace-pre-wrap">{m.content}</div>

                    {m.code_snippet && (
                      <div className="mt-3 p-3 bg-[#111827] border border-[#374151] rounded-lg font-mono text-xs overflow-x-auto text-[#E5E7EB]">
                        <div className="text-[10px] text-[#9CA3AF] uppercase tracking-wider mb-1 font-sans">
                          Attached Code Context
                        </div>
                        {m.code_snippet}
                      </div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <EmptyState
                title="Socratic Tutoring Ready"
                description="Ask a technical question, paste code for static debugging analysis, or request a progressive hint."
              />
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Box & Code Drawer */}
          <div className="p-3.5 border-t border-[#E5E5E5] bg-[#FAFAFA] space-y-2">
            {showCodeDrawer && (
              <div className="space-y-1">
                <div className="flex justify-between items-center text-xs text-[#6B7280]">
                  <span>Code Context (Static Review Only - No Execution):</span>
                  <button
                    onClick={() => setShowCodeDrawer(false)}
                    className="text-[#6B7280] hover:text-[#111827] text-xs flex items-center gap-1"
                  >
                    <X className="w-3.5 h-3.5" /> Close
                  </button>
                </div>
                <textarea
                  value={codeInput}
                  onChange={(e) => setCodeInput(e.target.value)}
                  placeholder="Paste Python, TypeScript, or SQL snippet for review or optimization..."
                  rows={4}
                  className="w-full bg-white border border-[#E5E5E5] rounded-lg p-2.5 font-mono text-xs text-[#111827] placeholder:text-[#9CA3AF] focus:outline-none focus:border-[#111827]"
                />
              </div>
            )}

            <form onSubmit={handleSendMessage} className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowCodeDrawer(!showCodeDrawer)}
                className="px-3 py-2 bg-white hover:bg-[#F3F4F6] border border-[#E5E5E5] rounded-lg text-xs font-medium text-[#374151] shrink-0 transition-colors flex items-center gap-1.5"
              >
                <Code2 className="w-3.5 h-3.5" />
                {showCodeDrawer ? "Hide Code" : "Add Code"}
              </button>

              <input
                type="text"
                required
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                placeholder="Ask the AI Tutor a question, request a hint, or verify an architecture idea..."
                className="flex-1 bg-white border border-[#E5E5E5] rounded-lg px-3.5 py-2 text-xs text-[#111827] placeholder:text-[#9CA3AF] focus:outline-none focus:border-[#111827]"
              />

              <Button
                type="submit"
                variant="primary"
                size="sm"
                isLoading={isSending}
                className="shrink-0"
              >
                <Send className="w-3.5 h-3.5 mr-1" /> Send
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
