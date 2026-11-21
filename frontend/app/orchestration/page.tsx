"use client";

import React, { useState, useEffect } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/LoadingSkeleton";
import { apiClient } from "@/lib/api/client";
import {
  Cpu,
  Layers,
  Activity,
  ShieldCheck,
  Zap,
  Clock,
  Coins,
  CheckCircle2,
  AlertTriangle,
  Play,
  RotateCcw,
  Sliders,
  ExternalLink,
} from "lucide-react";

interface AgentRegistryItem {
  agent_id: string;
  name: string;
  phase: number;
  responsibility: string;
  timeout_seconds: number;
  max_retries: number;
  rate_limit_per_min: number;
  max_tokens_budget: number;
  required_context_fields: string[];
}

interface OrchestrationMetrics {
  summary: {
    total_executions: number;
    success_rate_pct: number;
    failed_executions: number;
    average_latency_ms: number;
    total_tokens_estimated: number;
    total_cost_estimated_usd: number;
  };
  agent_breakdown: Array<{
    agent_id: string;
    calls_count: number;
    avg_latency_ms: number;
    failure_rate_pct: number;
  }>;
  recent_logs: Array<{
    execution_id: string;
    agent_id: string;
    status: string;
    latency_ms: number;
    tokens: number;
    cost_usd: number;
    timestamp?: string;
  }>;
}

export default function OrchestrationDashboardPage() {
  const [registry, setRegistry] = useState<AgentRegistryItem[]>([]);
  const [metrics, setMetrics] = useState<OrchestrationMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"registry" | "workflows" | "metrics" | "security">("registry");

  // Workflow trigger state
  const [workflowRunning, setWorkflowRunning] = useState(false);
  const [workflowResult, setWorkflowResult] = useState<any | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [regData, metData] = await Promise.all([
        apiClient<AgentRegistryItem[]>("/api/v1/orchestrator/registry"),
        apiClient<OrchestrationMetrics>("/api/v1/orchestrator/metrics"),
      ]);
      setRegistry(regData);
      setMetrics(metData);
    } catch (err: any) {
      setError(err.message || "Failed to load orchestration data.");
    } finally {
      setIsLoading(false);
    }
  };

  const runOnboardingWorkflow = async () => {
    setWorkflowRunning(true);
    setWorkflowResult(null);
    try {
      const res = await apiClient<any>("/api/v1/orchestrator/workflows/diagnostic-onboarding", {
        method: "POST",
        body: JSON.stringify({
          target_role: "Backend Engineer (Python / Cloud)",
          target_level: "Senior",
          skills: ["Python Architecture", "PostgreSQL & Concurrency", "API Design & Idempotency"],
        }),
      });
      setWorkflowResult({ type: "Diagnostic Onboarding", data: res });
      await fetchData();
    } catch (err: any) {
      setWorkflowResult({ error: err.message });
    } finally {
      setWorkflowRunning(false);
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

  if (error) {
    return (
      <div className="max-w-7xl mx-auto py-8 px-4">
        <EmptyState
          title="Orchestration Service Unavailable"
          description={error}
          actionLabel="Retry Connection"
          onAction={fetchData}
        />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 space-y-6 pb-12">
      {/* Header Banner */}
      <div className="bg-white border border-[#E5E5E5] rounded-xl p-6 shadow-xs relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 mb-2.5">
              <Badge variant="success" size="sm" className="font-medium tracking-normal text-[11px] leading-4 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 inline-block" />
                Operational
              </Badge>
              <Badge variant="neutral" size="sm" className="font-medium tracking-normal text-[11px] leading-4">
                6 Agents Registered • 4 Multi-Step Workflows
              </Badge>
            </div>
            <h1 className="text-[30px] font-bold leading-[38px] tracking-[-0.025em] text-[#111827]">
              Agent Orchestration, Monitoring & Reliability
            </h1>
            <p className="mt-1.5 text-sm font-normal leading-[22px] text-[#4B5563]">
              Coordinates all 6 specialized platform agents under strict governance: data minimisation,
              sliding-window rate limiting, prompt injection sanitization, idempotency keys, and real-time cost tracking.
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <Button variant="outline" size="sm" onClick={fetchData}>
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Refresh Telemetry
            </Button>
          </div>
        </div>

        {/* Telemetry KPI Grid */}
        {metrics && (
          <div className="mt-6 pt-5 border-t border-[#F0F0F0] grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl p-3.5">
              <div className="flex items-center justify-between text-[13px] font-medium leading-[18px] text-[#4B5563]">
                <span className="flex items-center gap-1.5"><Zap className="w-3.5 h-3.5 text-[#111827]" /> Executions</span>
                <span className="text-xs font-medium leading-4 text-emerald-700">{metrics.summary.success_rate_pct}% Success</span>
              </div>
              <p className="text-[30px] font-bold leading-[36px] tracking-tight tabular-nums text-[#111827] mt-1.5">
                {metrics.summary.total_executions}
              </p>
              <p className="text-xs font-normal leading-4 text-[#6B7280] mt-1">
                {metrics.summary.failed_executions} failures recorded
              </p>
            </div>

            <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl p-3.5">
              <div className="flex items-center justify-between text-[13px] font-medium leading-[18px] text-[#4B5563]">
                <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-[#111827]" /> Avg Latency</span>
                <span className="text-xs font-medium leading-4 text-[#6B7280]">Mean</span>
              </div>
              <p className="text-[30px] font-bold leading-[36px] tracking-tight tabular-nums text-[#111827] mt-1.5">
                {metrics.summary.average_latency_ms} <span className="text-sm font-normal text-[#6B7280] ml-0.5">ms</span>
              </p>
              <p className="text-xs font-normal leading-4 text-[#6B7280] mt-1">
                Optimized local execution
              </p>
            </div>

            <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl p-3.5">
              <div className="flex items-center justify-between text-[13px] font-medium leading-[18px] text-[#4B5563]">
                <span className="flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-[#111827]" /> Tokens Used</span>
                <span className="text-xs font-medium leading-4 text-[#6B7280]">Prompt + Output</span>
              </div>
              <p className="text-[30px] font-bold leading-[36px] tracking-tight tabular-nums text-[#111827] mt-1.5">
                {metrics.summary.total_tokens_estimated.toLocaleString()}
              </p>
              <p className="text-xs font-normal leading-4 text-[#6B7280] mt-1">
                Sliding budget tracked
              </p>
            </div>

            <div className="bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl p-3.5">
              <div className="flex items-center justify-between text-[13px] font-medium leading-[18px] text-[#4B5563]">
                <span className="flex items-center gap-1.5"><Coins className="w-3.5 h-3.5 text-[#111827]" /> Cost Estimate</span>
                <span className="text-xs font-medium leading-4 text-[#6B7280]">USD</span>
              </div>
              <p className="text-[30px] font-bold leading-[36px] tracking-tight tabular-nums text-[#111827] mt-1.5">
                <span className="text-lg font-normal text-[#6B7280] mr-0.5">$</span>{metrics.summary.total_cost_estimated_usd}
              </p>
              <p className="text-xs font-normal leading-4 text-[#6B7280] mt-1">
                Blended token pricing
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-[#E5E5E5] pb-3 overflow-x-auto">
        <button
          type="button"
          onClick={() => setActiveTab("registry")}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm leading-5 transition-colors duration-100 ${
            activeTab === "registry"
              ? "bg-[#111827] text-white font-semibold shadow-xs"
              : "bg-white text-[#4B5563] border border-[#E5E5E5] hover:bg-[#F9F9F9] hover:text-[#111827] font-medium"
          }`}
        >
          <Cpu className="w-3.5 h-3.5 mr-1" /> Agent Registry ({registry.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("workflows")}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm leading-5 transition-colors duration-100 ${
            activeTab === "workflows"
              ? "bg-[#111827] text-white font-semibold shadow-xs"
              : "bg-white text-[#4B5563] border border-[#E5E5E5] hover:bg-[#F9F9F9] hover:text-[#111827] font-medium"
          }`}
        >
          <Layers className="w-3.5 h-3.5 mr-1" /> Multi-Agent Workflows
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("metrics")}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm leading-5 transition-colors duration-100 ${
            activeTab === "metrics"
              ? "bg-[#111827] text-white font-semibold shadow-xs"
              : "bg-white text-[#4B5563] border border-[#E5E5E5] hover:bg-[#F9F9F9] hover:text-[#111827] font-medium"
          }`}
        >
          <Activity className="w-3.5 h-3.5 mr-1" /> Telemetry & Audit Logs
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("security")}
          className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm leading-5 transition-colors duration-100 ${
            activeTab === "security"
              ? "bg-[#111827] text-white font-semibold shadow-xs"
              : "bg-white text-[#4B5563] border border-[#E5E5E5] hover:bg-[#F9F9F9] hover:text-[#111827] font-medium"
          }`}
        >
          <ShieldCheck className="w-3.5 h-3.5 mr-1" /> Security & Governance
        </button>
      </div>

      {/* Tab: Registry */}
      {activeTab === "registry" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {registry.map((agent) => (
            <Card key={agent.agent_id} className="border-[#E5E5E5] bg-white shadow-xs hover:border-[#D1D5DB] transition-colors">
              <div className="flex items-center justify-between pb-3 border-b border-[#F0F0F0]">
                <div>
                  <h3 className="font-semibold text-base leading-6 text-[#111827]">{agent.name}</h3>
                  <p className="text-xs font-mono leading-4 text-[#4B5563] mt-0.5">
                    {agent.agent_id}
                  </p>
                </div>
                <Badge variant="info" size="sm" className="font-medium text-xs leading-4">
                  {agent.rate_limit_per_min} rpm
                </Badge>
              </div>

              <div className="mt-3.5 space-y-3">
                <p className="text-sm font-normal leading-[22px] text-[#4B5563]">{agent.responsibility}</p>

                <div className="pt-2.5 border-t border-[#F0F0F0] space-y-1.5">
                  <div className="flex justify-between items-center text-xs leading-4">
                    <span className="text-[#6B7280] font-normal">Execution Timeout:</span>
                    <span className="font-mono font-medium text-[#111827] tabular-nums">{agent.timeout_seconds}s</span>
                  </div>
                  <div className="flex justify-between items-center text-xs leading-4">
                    <span className="text-[#6B7280] font-normal">Retry Budget:</span>
                    <span className="font-mono font-medium text-[#111827] tabular-nums">Max {agent.max_retries} with exp. backoff</span>
                  </div>
                  <div className="flex justify-between items-center text-xs leading-4">
                    <span className="text-[#6B7280] font-normal">Max Token Budget:</span>
                    <span className="font-mono font-medium text-[#111827] tabular-nums">{agent.max_tokens_budget} tokens</span>
                  </div>
                </div>

                <div className="pt-2.5 border-t border-[#F0F0F0]">
                  <p className="text-xs font-medium leading-4 text-[#6B7280] mb-1.5">Scoped Context Contract:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {agent.required_context_fields.map((f) => (
                      <span key={f} className="px-2 py-0.5 rounded bg-[#F3F4F6] border border-[#E5E5E5] text-[11px] font-medium leading-4 text-[#374151] font-mono">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Tab: Workflows */}
      {activeTab === "workflows" && (
        <div className="space-y-6">
          <Card title="Controlled Multi-Agent Workflows" subtitle="Explicit, deterministic multi-agent pipelines with idempotency keys and state tracking.">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* Workflow 1 */}
              <div className="p-4 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-sm leading-5 text-[#111827]">Workflow A: Interview Feedback Loop</h4>
                  <Badge variant="success" size="sm" className="font-medium text-xs leading-4">4 Steps</Badge>
                </div>
                <p className="text-[13px] font-normal leading-5 text-[#4B5563]">
                  Evaluates candidate interview turn (Interview Simulation) → extracts competency evidence & updates CandidateSkillAnalytics → adaptively prunes Adaptive Roadmap → refreshes Competency Intelligence.
                </p>
                <div className="text-xs font-mono text-[#374151] bg-white p-2.5 rounded border border-[#E5E5E5] leading-5">
                  Interview Simulation → Skills / Mistakes → Adaptive Path → Competency Intelligence
                </div>
              </div>

              {/* Workflow 2 */}
              <div className="p-4 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-sm leading-5 text-[#111827]">Workflow B: Scenario Evaluation Loop</h4>
                  <Badge variant="success" size="sm" className="font-medium text-xs leading-4">3 Steps</Badge>
                </div>
                <p className="text-[13px] font-normal leading-5 text-[#4B5563]">
                  Evaluates real-world code challenge against rubric (Scenario Engine) → updates CandidateSkillAnalytics for scenario skills → updates roadmap progress & refreshes Competency Intelligence.
                </p>
                <div className="text-xs font-mono text-[#374151] bg-white p-2.5 rounded border border-[#E5E5E5] leading-5">
                  Scenario Engine → Rubric Evaluation → Skills → Competency Intelligence
                </div>
              </div>

              {/* Workflow 3 */}
              <div className="p-4 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-sm leading-5 text-[#111827]">Workflow C: Diagnostic Onboarding</h4>
                  <Badge variant="success" size="sm" className="font-medium text-xs leading-4">2 Steps</Badge>
                </div>
                <p className="text-[13px] font-normal leading-5 text-[#4B5563]">
                  Discovers career objectives and experience (Learner Profiling) → initializes baseline competency framework → synthesizes personalized adaptive learning roadmap.
                </p>
                <div className="text-xs font-mono text-[#374151] bg-white p-2.5 rounded border border-[#E5E5E5] leading-5">
                  Learner Profiling → Adaptive Roadmap
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  className="w-full mt-2"
                  disabled={workflowRunning}
                  onClick={runOnboardingWorkflow}
                >
                  <Play className="w-3.5 h-3.5 mr-1.5" /> {workflowRunning ? "Running Pipeline..." : "Execute Onboarding Workflow"}
                </Button>
              </div>

              {/* Workflow 4 */}
              <div className="p-4 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-sm leading-5 text-[#111827]">Workflow D: Project Mentorship Loop</h4>
                  <Badge variant="success" size="sm" className="font-medium text-xs leading-4">2 Steps</Badge>
                </div>
                <p className="text-[13px] font-normal leading-5 text-[#4B5563]">
                  Validates project ownership → conducts Socratic guidance across the 6 technical stages (Project Mentor) → updates portfolio project skills in Competency Intelligence.
                </p>
                <div className="text-xs font-mono text-[#374151] bg-white p-2.5 rounded border border-[#E5E5E5] leading-5">
                  Project Mentor → Competency Intelligence
                </div>
              </div>
            </div>

            {/* Workflow Execution Result Modal / Card */}
            {workflowResult && (
              <div className="mt-5 p-4 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm leading-5 text-[#111827]">Execution Result: {workflowResult.type}</span>
                  <Badge variant={workflowResult.error ? "danger" : "success"} size="sm" className="font-medium text-xs leading-4">
                    {workflowResult.error ? "Failed" : "Success"}
                  </Badge>
                </div>
                <pre className="p-3 bg-white border border-[#E5E5E5] rounded-lg font-mono text-xs leading-5 text-[#374151] overflow-x-auto max-h-48">
                  {JSON.stringify(workflowResult.data || workflowResult.error, null, 2)}
                </pre>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Tab: Telemetry & Audit Logs */}
      {activeTab === "metrics" && metrics && (
        <div className="space-y-6">
          <Card title="Agent Execution Breakdown" subtitle="Detailed latency, invocation volume, and failure rates per specialized agent.">
            <div className="space-y-2.5">
              {metrics.agent_breakdown.map((agent) => (
                <div key={agent.agent_id} className="p-3 bg-[#FAFAFA] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-sm leading-5 font-mono text-[#111827]">{agent.agent_id}</p>
                    <p className="text-xs font-normal leading-4 text-[#6B7280] mt-0.5">
                      Invocations: <span className="font-semibold text-[#111827] tabular-nums">{agent.calls_count}</span> • Avg Latency: <span className="font-medium text-[#111827] tabular-nums">{agent.avg_latency_ms} ms</span>
                    </p>
                  </div>
                  <Badge variant={agent.failure_rate_pct === 0 ? "success" : "warning"} size="sm" className="font-medium text-xs leading-4 tabular-nums">
                    {agent.failure_rate_pct}% Failure Rate
                  </Badge>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Recent Execution Audit Trail" subtitle="Sanitized execution trail with latency profiling and cost estimation (PII scrubbed).">
            {metrics.recent_logs.length === 0 ? (
              <p className="text-sm font-normal text-[#6B7280] italic p-4 text-center">No agent executions recorded yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13px] leading-5 text-[#374151]">
                  <thead className="bg-[#FAFAFA] border-b border-[#E5E5E5] text-xs font-medium text-[#6B7280] uppercase tracking-wider">
                    <tr>
                      <th className="p-3">Execution ID</th>
                      <th className="p-3">Agent</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Latency</th>
                      <th className="p-3">Tokens</th>
                      <th className="p-3">Est. Cost</th>
                      <th className="p-3">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#F0F0F0]">
                    {metrics.recent_logs.map((log) => (
                      <tr key={log.execution_id} className="hover:bg-[#F9FAFB] transition-colors">
                        <td className="p-3 font-mono text-xs text-[#6B7280]">{log.execution_id}</td>
                        <td className="p-3 font-medium text-[#111827]">{log.agent_id}</td>
                        <td className="p-3">
                          <Badge variant={log.status === "completed" ? "success" : "danger"} size="sm" className="font-medium text-xs leading-4">
                            {log.status}
                          </Badge>
                        </td>
                        <td className="p-3 font-mono text-xs tabular-nums">{log.latency_ms} ms</td>
                        <td className="p-3 font-mono text-xs tabular-nums">{log.tokens.toLocaleString()}</td>
                        <td className="p-3 font-mono text-xs tabular-nums">${log.cost_usd}</td>
                        <td className="p-3 text-xs text-[#6B7280] tabular-nums">{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Tab: Security & Governance Controls */}
      {activeTab === "security" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card title="Security & Boundary Enforcement" subtitle="Strict isolation and input validation protecting core resources.">
            <ul className="space-y-3">
              <li className="flex items-start gap-2.5 p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg">
                <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-sm leading-5 text-[#111827]">Data Minimisation Contracts</p>
                  <p className="text-[13px] font-normal leading-5 text-[#4B5563] mt-0.5">Agents only receive the exact fields required for their domain. Tutor never receives resumes; Scenarios never receive personal logs.</p>
                </div>
              </li>

              <li className="flex items-start gap-2.5 p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg">
                <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-sm leading-5 text-[#111827]">Adversarial Injection Defense</p>
                  <p className="text-[13px] font-normal leading-5 text-[#4B5563] mt-0.5">Sanitization filters strip DAN mode, system prompt overrides, and control tokens before context is presented to any LLM prompt.</p>
                </div>
              </li>

              <li className="flex items-start gap-2.5 p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg">
                <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-sm leading-5 text-[#111827]">Tenant Isolation & User Ownership</p>
                  <p className="text-[13px] font-normal leading-5 text-[#4B5563] mt-0.5">All database queries, roadmaps, project mentorship turns, and scenario submissions enforce strict ownership checks tied to authenticated session tokens.</p>
                </div>
              </li>
            </ul>
          </Card>

          <Card title="Reliability & Failure Handling" subtitle="Policies preventing cascading failures and infinite AI execution loops.">
            <ul className="space-y-3">
              <li className="flex items-start gap-2.5 p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg">
                <Sliders className="w-4 h-4 text-[#111827] shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-sm leading-5 text-[#111827]">Sliding-Window Rate Limiting</p>
                  <p className="text-[13px] font-normal leading-5 text-[#4B5563] mt-0.5">Each agent enforces strict turns per minute (15–40 rpm) per candidate, completely eliminating autonomous recursive loops.</p>
                </div>
              </li>

              <li className="flex items-start gap-2.5 p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg">
                <Sliders className="w-4 h-4 text-[#111827] shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-sm leading-5 text-[#111827]">Exponential Backoff & Fallbacks</p>
                  <p className="text-[13px] font-normal leading-5 text-[#4B5563] mt-0.5">Transient failures retry up to 2 times with exponential delay. Offline AI providers trigger deterministic fallback generation.</p>
                </div>
              </li>

              <li className="flex items-start gap-2.5 p-3.5 bg-[#FAFAFA] border border-[#E5E5E5] rounded-lg">
                <Sliders className="w-4 h-4 text-[#111827] shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-sm leading-5 text-[#111827]">Idempotency Protection</p>
                  <p className="text-[13px] font-normal leading-5 text-[#4B5563] mt-0.5">X-Idempotency-Key headers prevent double-grading scenarios, duplicate interview turns, or redundant roadmap generations.</p>
                </div>
              </li>
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}
