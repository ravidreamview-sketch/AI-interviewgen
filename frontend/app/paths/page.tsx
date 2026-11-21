"use client";

import React, { useState, useEffect } from "react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingSkeleton } from "@/components/ui/LoadingSkeleton";
import { apiClient } from "@/lib/api/client";
import {
  AdaptiveRoadmapData,
  LearningModule,
  LearningActivity,
  NextRecommendationResponse,
} from "@/lib/types";
import {
  Compass,
  RefreshCw,
  Clock,
  ExternalLink,
  Trophy,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  BookOpen,
  ArrowRight,
  Sparkles,
} from "lucide-react";

export default function AdaptivePathsPage() {
  const [roadmap, setRoadmap] = useState<AdaptiveRoadmapData | null>(null);
  const [recommendation, setRecommendation] = useState<NextRecommendationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAdapting, setIsAdapting] = useState(false);
  const [activeFilter, setActiveFilter] = useState<"all" | "in_progress" | "available" | "completed">("all");
  const [expandedModuleId, setExpandedModuleId] = useState<string | null>(null);

  useEffect(() => {
    fetchActiveRoadmapAndRecommendation();
  }, []);

  async function fetchActiveRoadmapAndRecommendation() {
    setIsLoading(true);
    try {
      const data = await apiClient<AdaptiveRoadmapData>("/api/v1/paths/active");
      setRoadmap(data);
      if (data && data.modules.length > 0) {
        setExpandedModuleId(data.modules[0].id);
      }

      const rec = await apiClient<NextRecommendationResponse>("/api/v1/paths/next-recommendation");
      setRecommendation(rec);
    } catch (err) {
      console.error("Failed to load active learning roadmap:", err);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAdaptRoadmap() {
    setIsAdapting(true);
    try {
      const updated = await apiClient<AdaptiveRoadmapData>("/api/v1/paths/adapt", {
        method: "POST",
        body: JSON.stringify({
          trigger_reason: "Learner Requested Calibration with Recent Performance Data",
        }),
      });
      setRoadmap(updated);
      const rec = await apiClient<NextRecommendationResponse>("/api/v1/paths/next-recommendation");
      setRecommendation(rec);
    } catch (err: any) {
      alert(err.message || "Failed to adapt roadmap.");
    } finally {
      setIsAdapting(false);
    }
  }

  async function handleToggleActivity(activityId: string, currentStatus: string) {
    if (!roadmap) return;
    const newStatus = currentStatus === "completed" ? "pending" : "completed";

    try {
      await apiClient(`/api/v1/paths/activities/${activityId}/progress`, {
        method: "POST",
        body: JSON.stringify({
          roadmap_id: roadmap.roadmap_id,
          status: newStatus,
        }),
      });
      // Refresh roadmap state
      const [updatedData, rec] = await Promise.all([
        apiClient<AdaptiveRoadmapData>("/api/v1/paths/active"),
        apiClient<NextRecommendationResponse>("/api/v1/paths/next-recommendation"),
      ]);
      setRoadmap(updatedData);
      setRecommendation(rec);
    } catch (err: any) {
      alert(err.message || "Failed to update activity progress.");
    }
  }

  const getPriorityBadgeVariant = (priority: string) => {
    switch (priority) {
      case "CRITICAL": return "danger";
      case "HIGH": return "warning";
      case "MODERATE": return "info";
      case "LOW": return "neutral";
      default: return "default";
    }
  };

  const getModuleStatusBadgeVariant = (status: string) => {
    switch (status) {
      case "completed": return "success";
      case "in_progress": return "info";
      case "available": return "default";
      case "locked": return "neutral";
      default: return "neutral";
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto py-8 px-4">
        <LoadingSkeleton className="h-8 w-64" />
        <LoadingSkeleton className="h-28 w-full" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <LoadingSkeleton className="h-24" />
          <LoadingSkeleton className="h-24" />
          <LoadingSkeleton className="h-24" />
          <LoadingSkeleton className="h-24" />
        </div>
      </div>
    );
  }

  const filteredModules = roadmap?.modules.filter((m) => {
    if (activeFilter === "all") return true;
    return m.status === activeFilter;
  }) || [];

  const completedActivitiesCount = roadmap?.modules.reduce(
    (acc, m) => acc + m.activities.filter((a) => a.status === "completed").length,
    0
  ) || 0;

  const totalActivitiesCount = roadmap?.modules.reduce(
    (acc, m) => acc + m.activities.length,
    0
  ) || 0;

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-[#111827]">
              {roadmap?.title || "Adaptive Learning Path"}
            </h1>
          </div>
          <p className="text-sm text-[#6B7280] mt-1 max-w-3xl">
            {roadmap?.rationale || "Personalized learning roadmap dynamically synthesized from your competency gaps."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            isLoading={isAdapting}
            onClick={handleAdaptRoadmap}
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Adapt Roadmap with New Evidence
          </Button>
        </div>
      </div>

      {/* Progress & Overview KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="p-4 bg-white border border-[#E5E5E5] rounded-xl shadow-xs">
          <div className="text-xs text-[#6B7280] uppercase tracking-wider font-semibold">Overall Progress</div>
          <div className="text-2xl font-bold text-[#111827] mt-1">{roadmap?.overall_progress || 0}%</div>
          <div className="w-full bg-[#F3F4F6] h-1.5 rounded-full mt-2 overflow-hidden">
            <div
              className="bg-[#111827] h-full rounded-full transition-all duration-300"
              style={{ width: `${roadmap?.overall_progress || 0}%` }}
            />
          </div>
        </Card>

        <Card className="p-4 bg-white border border-[#E5E5E5] rounded-xl shadow-xs">
          <div className="text-xs text-[#6B7280] uppercase tracking-wider font-semibold">Activities Completed</div>
          <div className="text-2xl font-bold text-[#111827] mt-1">
            {completedActivitiesCount} / {totalActivitiesCount}
          </div>
          <div className="text-xs text-[#6B7280] mt-1">
            {totalActivitiesCount - completedActivitiesCount} remaining
          </div>
        </Card>

        <Card className="p-4 bg-white border border-[#E5E5E5] rounded-xl shadow-xs">
          <div className="text-xs text-[#6B7280] uppercase tracking-wider font-semibold">Estimated Effort</div>
          <div className="text-2xl font-bold text-[#111827] mt-1">
            {roadmap?.total_estimated_hours || 0} hrs
          </div>
          <div className="text-xs text-[#6B7280] mt-1">Self-paced micro-modules</div>
        </Card>

        <Card className="p-4 bg-white border border-[#E5E5E5] rounded-xl shadow-xs">
          <div className="text-xs text-[#6B7280] uppercase tracking-wider font-semibold">Target Level</div>
          <div className="text-2xl font-bold text-[#111827] mt-1">
            {roadmap?.target_level || "Mid-Level"}
          </div>
          <div className="text-xs text-[#6B7280] mt-1 truncate">{roadmap?.target_role}</div>
        </Card>
      </div>

      {/* Next Recommended Activity Hero Card */}
      {recommendation?.current_activity && (
        <div className="bg-white border border-[#E5E5E5] rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between gap-2 pb-3 border-b border-[#F0F0F0]">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#111827]" />
              <span className="text-xs font-semibold uppercase tracking-wider text-[#111827]">
                Immediate Priority Activity
              </span>
              <span className="text-xs text-[#6B7280]">
                • From Module: {recommendation.current_module?.title}
              </span>
            </div>
            <Badge variant="info">
              {recommendation.current_activity.activity_type.replace(/_/g, " ")}
            </Badge>
          </div>

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mt-3">
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-[#111827]">
                {recommendation.current_activity.title}
              </h3>
              <p className="text-xs text-[#6B7280] max-w-2xl leading-relaxed">
                {recommendation.current_activity.description}
              </p>
              <div className="flex items-center gap-3 pt-1 text-xs text-[#6B7280]">
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {recommendation.current_activity.estimated_minutes} mins
                </span>
                <span>•</span>
                <span>Priority: {recommendation.current_module?.gap_priority}</span>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  handleToggleActivity(
                    recommendation.current_activity!.id,
                    recommendation.current_activity!.status
                  )
                }
              >
                Mark as Completed
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Module Filters */}
      <div className="flex border-b border-[#E5E5E5] space-x-6">
        <button
          onClick={() => setActiveFilter("all")}
          className={`pb-3 text-sm font-medium transition-colors border-b-2 ${
            activeFilter === "all"
              ? "border-[#111827] text-[#111827] font-semibold"
              : "border-transparent text-[#6B7280] hover:text-[#111827]"
          }`}
        >
          All Modules ({roadmap?.modules.length || 0})
        </button>
        <button
          onClick={() => setActiveFilter("in_progress")}
          className={`pb-3 text-sm font-medium transition-colors border-b-2 ${
            activeFilter === "in_progress"
              ? "border-[#111827] text-[#111827] font-semibold"
              : "border-transparent text-[#6B7280] hover:text-[#111827]"
          }`}
        >
          In Progress ({roadmap?.modules.filter((m) => m.status === "in_progress").length || 0})
        </button>
        <button
          onClick={() => setActiveFilter("available")}
          className={`pb-3 text-sm font-medium transition-colors border-b-2 ${
            activeFilter === "available"
              ? "border-[#111827] text-[#111827] font-semibold"
              : "border-transparent text-[#6B7280] hover:text-[#111827]"
          }`}
        >
          Available ({roadmap?.modules.filter((m) => m.status === "available").length || 0})
        </button>
        <button
          onClick={() => setActiveFilter("completed")}
          className={`pb-3 text-sm font-medium transition-colors border-b-2 ${
            activeFilter === "completed"
              ? "border-[#111827] text-[#111827] font-semibold"
              : "border-transparent text-[#6B7280] hover:text-[#111827]"
          }`}
        >
          Completed ({roadmap?.modules.filter((m) => m.status === "completed").length || 0})
        </button>
      </div>

      {/* Module List Accordion */}
      <div className="space-y-3">
        {filteredModules.length > 0 ? (
          filteredModules.map((module) => {
            const isExpanded = expandedModuleId === module.id;
            return (
              <div
                key={module.id}
                className="border border-[#E5E5E5] rounded-xl bg-white shadow-xs transition-all overflow-hidden"
              >
                {/* Module Header Bar */}
                <div
                  onClick={() => setExpandedModuleId(isExpanded ? null : module.id)}
                  className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 cursor-pointer hover:bg-[#F9FAFB] transition-colors"
                >
                  <div className="flex items-start sm:items-center gap-3">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-[#F3F4F6] text-[#111827] text-xs font-semibold shrink-0">
                      {module.sequence_index}
                    </span>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-[#111827] text-sm">{module.title}</h3>
                        <Badge variant={getPriorityBadgeVariant(module.gap_priority)} size="sm">
                          {module.gap_priority} GAP
                        </Badge>
                        <Badge variant={getModuleStatusBadgeVariant(module.status)} size="sm">
                          {module.status.toUpperCase()}
                        </Badge>
                      </div>
                      <p className="text-xs text-[#6B7280] mt-0.5">{module.description}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 shrink-0 sm:self-center self-end">
                    <div className="text-right">
                      <div className="text-xs font-semibold text-[#111827]">
                        {module.progress_percentage}% Done
                      </div>
                      <div className="text-[11px] text-[#6B7280]">{module.estimated_hours} hrs</div>
                    </div>
                    <span className="text-[#6B7280] text-sm">
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </span>
                  </div>
                </div>

                {/* Module Content */}
                {isExpanded && (
                  <div className="p-4 border-t border-[#E5E5E5] space-y-4 bg-[#FAFAFA]">
                    {/* Targeted Skills Tags */}
                    <div>
                      <span className="text-xs text-[#6B7280] uppercase tracking-wider font-semibold block mb-1.5">
                        Targeted Skills & Competencies:
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {module.targeted_skills.map((skill, sIdx) => (
                          <Badge key={sIdx} variant="neutral" size="sm">
                            {skill}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    {/* Activities List */}
                    <div className="space-y-2">
                      <span className="text-xs text-[#6B7280] uppercase tracking-wider font-semibold block">
                        Interactive Activities & Lessons ({module.activities.length}):
                      </span>
                      <div className="space-y-2">
                        {module.activities.map((act) => (
                          <div
                            key={act.id}
                            className={`p-3 rounded-lg border flex items-start justify-between gap-4 transition-colors ${
                              act.status === "completed"
                                ? "border-[#E5E5E5] bg-[#F9FAFB] text-[#6B7280]"
                                : "border-[#E5E5E5] bg-white text-[#111827]"
                            }`}
                          >
                            <div className="space-y-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className={`text-xs font-medium ${act.status === "completed" ? "line-through text-[#9CA3AF]" : "text-[#111827]"}`}>
                                  {act.title}
                                </span>
                                <Badge variant="neutral" size="sm">
                                  {act.activity_type.replace(/_/g, " ")}
                                </Badge>
                                <span className="text-[11px] text-[#6B7280] flex items-center gap-1">
                                  <Clock className="w-3 h-3" />
                                  {act.estimated_minutes} min
                                </span>
                              </div>
                              <p className="text-xs text-[#6B7280] leading-relaxed">{act.description}</p>
                              {act.external_resources.length > 0 && (
                                <div className="flex gap-2 pt-0.5">
                                  {act.external_resources.map((res, rIdx) => (
                                    <a
                                      key={rIdx}
                                      href={res.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-[11px] text-[#2563EB] hover:underline flex items-center gap-1"
                                    >
                                      <ExternalLink className="w-3 h-3" />
                                      {res.title}
                                    </a>
                                  ))}
                                </div>
                              )}
                            </div>
                            <Button
                              variant={act.status === "completed" ? "outline" : "primary"}
                              size="sm"
                              onClick={() => handleToggleActivity(act.id, act.status)}
                              className="shrink-0"
                            >
                              {act.status === "completed" ? "Completed" : "Complete"}
                            </Button>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Milestone Checkpoint Card */}
                    <div className="p-3.5 rounded-lg border border-[#E5E5E5] bg-white space-y-1.5 shadow-xs">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Trophy className="w-4 h-4 text-[#111827]" />
                          <h4 className="font-semibold text-xs text-[#111827]">
                            {module.milestone.title}
                          </h4>
                        </div>
                        <Badge
                          variant={module.milestone.status === "passed" ? "success" : "neutral"}
                          size="sm"
                        >
                          {module.milestone.status.toUpperCase()}
                        </Badge>
                      </div>
                      <p className="text-xs text-[#6B7280] leading-relaxed">
                        {module.milestone.criteria}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <EmptyState
            title="No Modules Found"
            description="No learning modules match the selected filter."
          />
        )}
      </div>
    </div>
  );
}
