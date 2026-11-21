"use client";

import React from "react";
import Link from "next/link";
import { Card, CardHeader, CardContent } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import {
  UserCheck,
  Route,
  BookOpen,
  Briefcase,
  Mic,
  BarChart3,
  ArrowRight,
  ExternalLink,
  Activity,
} from "lucide-react";

export default function HomePage() {
  const agents = [
    {
      id: 1,
      title: "Learner profiling agent",
      href: "/learners",
      desc: "Discovers candidate skills, career goals, target role, and calculates evidence-aware competency vectors.",
      icon: UserCheck,
      status: "Active",
    },
    {
      id: 2,
      title: "Adaptive learning path agent",
      href: "/paths",
      desc: "Synthesizes personalized modular learning roadmaps with real-time pruning based on demonstrated mastery.",
      icon: Route,
      status: "Active",
    },
    {
      id: 3,
      title: "AI tutor agent",
      href: "/tutor",
      desc: "Provides context-aware tutoring, step-by-step guidance, and code debugging assistance without giving away direct answers.",
      icon: BookOpen,
      status: "Active",
    },
    {
      id: 4,
      title: "Real-world scenario agent",
      href: "/scenarios",
      desc: "Generates production incident challenges, architecture dilemmas, and evaluates submitted code against rubrics.",
      icon: Briefcase,
      status: "Active",
    },
    {
      id: 5,
      title: "AI interview & project mentor",
      href: "/interviews",
      desc: "Multi-turn adaptive interview simulations and continuous architectural milestone reviews.",
      icon: Mic,
      status: "Active",
    },
    {
      id: 6,
      title: "Competency intelligence agent",
      href: "/competency",
      desc: "Multi-dimensional evidence consolidation, skill gap analytics, and objective career readiness scoring.",
      icon: BarChart3,
      status: "Active",
    },
  ];

  return (
    <div className="space-y-8 pb-12">
      {/* Platform Overview Banner */}
      <div className="border border-[#E5E5E5] rounded-xl p-6 bg-white shadow-xs">
        <div className="max-w-3xl space-y-3">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-[#F3F4F6] text-[#374151] border border-[#E5E7EB] text-xs font-medium leading-4">
            <Activity size={13} strokeWidth={2} className="text-emerald-600" />
            <span>Platform operational</span>
          </div>

          <h1 className="text-[30px] font-bold leading-[38px] tracking-[-0.025em] text-[#111827]">
            AI Interview Studio
          </h1>
          <p className="text-sm font-normal leading-[22px] text-[#4B5563]">
            A modular multi-agent platform designed for candidate skill evaluation, adaptive learning roadmaps, context-aware tutoring, and real-world mock interview simulations. Built with strict provenance tracking and zero hallucinated competencies.
          </p>

          <div className="pt-2 flex flex-wrap gap-3">
            <Link href="/onboarding">
              <Button variant="primary" size="sm">
                <span>Start candidate onboarding</span>
                <ArrowRight size={14} strokeWidth={1.75} />
              </Button>
            </Link>
            <a href="/docs" target="_blank" rel="noreferrer">
              <Button variant="secondary" size="sm">
                <span>API documentation</span>
                <ExternalLink size={13} strokeWidth={1.75} />
              </Button>
            </a>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 border border-[#E5E5E5] rounded-xl bg-white shadow-xs">
          <span className="text-[13px] font-medium leading-[18px] text-[#4B5563] block">Active agents</span>
          <span className="text-[30px] font-bold leading-[36px] tracking-tight tabular-nums text-[#111827] mt-1.5 block">6</span>
          <span className="text-xs font-medium leading-4 text-[#065F46] mt-1 block">Platform orchestrated</span>
        </div>

        <div className="p-4 border border-[#E5E5E5] rounded-xl bg-white shadow-xs">
          <span className="text-[13px] font-medium leading-[18px] text-[#4B5563] block">Standard roles</span>
          <span className="text-[30px] font-bold leading-[36px] tracking-tight tabular-nums text-[#111827] mt-1.5 block">14</span>
          <span className="text-xs font-normal leading-4 text-[#6B7280] mt-1 block">+ Custom role generator</span>
        </div>

        <div className="p-4 border border-[#E5E5E5] rounded-xl bg-white shadow-xs">
          <span className="text-[13px] font-medium leading-[18px] text-[#4B5563] block">Competency tiers</span>
          <span className="text-[30px] font-bold leading-[36px] tracking-tight tabular-nums text-[#111827] mt-1.5 block">5</span>
          <span className="text-xs font-normal leading-4 text-[#6B7280] mt-1 block">Foundational to Expert</span>
        </div>

        <div className="p-4 border border-[#E5E5E5] rounded-xl bg-white shadow-xs">
          <span className="text-[13px] font-medium leading-[18px] text-[#4B5563] block">Readiness index</span>
          <span className="text-[30px] font-bold leading-[36px] tracking-tight text-[#111827] mt-1.5 block">Objective</span>
          <span className="text-xs font-medium leading-4 text-[#065F46] mt-1 block">Evidence-based verification</span>
        </div>
      </div>

      {/* Agent Capability Matrix */}
      <div className="space-y-4">
        <div className="border-b border-[#E5E5E5] pb-3.5 flex items-center justify-between">
          <div>
            <h2 className="text-[20px] font-semibold leading-7 tracking-[-0.01em] text-[#111827]">
              Agent capability matrix
            </h2>
            <p className="text-sm font-normal leading-[22px] text-[#6B7280] mt-0.5">
              Autonomous micro-agents executing specialized workflow phases.
            </p>
          </div>
          <Link href="/orchestration" className="text-[13px] text-[#111827] hover:underline font-medium inline-flex items-center gap-1 leading-5">
            <span>View orchestration</span>
            <ArrowRight size={13} strokeWidth={1.75} />
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => {
            const Icon = agent.icon;
            return (
              <Link key={agent.id} href={agent.href} className="group">
                <Card className="h-full hover:border-slate-400 transition-colors flex flex-col justify-between">
                  <div>
                    <CardHeader className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-[#F3F4F6] text-[#374151] flex items-center justify-center group-hover:bg-[#111827] group-hover:text-white transition-colors">
                          <Icon size={16} strokeWidth={1.75} />
                        </div>
                        <div>
                          <h3 className="font-semibold text-base leading-6 text-[#111827] group-hover:text-black">
                            {agent.title}
                          </h3>
                        </div>
                      </div>
                      <Badge variant="success" size="sm" className="font-medium text-xs leading-4">
                        {agent.status}
                      </Badge>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm font-normal leading-[22px] text-[#4B5563]">{agent.desc}</p>
                    </CardContent>
                  </div>
                  <div className="pt-3 border-t border-[#F0F0F0] mt-4 flex items-center justify-between text-xs font-medium leading-4 text-[#111827]">
                    <span>Open agent workspace</span>
                    <ArrowRight size={13} strokeWidth={1.75} className="group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
