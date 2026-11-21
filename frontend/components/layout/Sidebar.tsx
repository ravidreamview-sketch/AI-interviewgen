"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  UserCheck,
  User,
  Route,
  BookOpen,
  Briefcase,
  Mic,
  BarChart3,
  Sliders,
  FileText,
  Settings,
  CheckCircle2,
} from "lucide-react";

interface NavItem {
  name: string;
  href: string;
  tag?: string;
  icon: React.ElementType;
}

const NAV_ITEMS: NavItem[] = [
  { name: "Platform overview", href: "/", icon: LayoutDashboard },
  { name: "Candidate onboarding", href: "/onboarding", tag: "Start here", icon: UserCheck },
  { name: "Learner profiling", href: "/learners", icon: User },
  { name: "Adaptive paths", href: "/paths", icon: Route },
  { name: "AI tutor", href: "/tutor", icon: BookOpen },
  { name: "Real scenarios", href: "/scenarios", icon: Briefcase },
  { name: "Mock interviews", href: "/interviews", icon: Mic },
  { name: "Competency intelligence", href: "/competency", icon: BarChart3 },
  { name: "Agent Orchestration & Operations", href: "/orchestration", icon: Sliders },
  { name: "Resume & ATS match", href: "/resumes", icon: FileText },
  { name: "Admin portal", href: "/admin", icon: Settings },
];

export const Sidebar: React.FC = () => {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-[#E5E5E5] bg-[#F7F7F7] flex flex-col shrink-0 min-h-[calc(100vh-3.5rem)]">
      <div className="p-3 space-y-1 flex-1">
        <p className="px-3 pt-2 text-xs font-medium text-[#6B7280] leading-4 tracking-normal mb-1.5">
          Navigation
        </p>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm leading-5 transition-colors duration-100 ${isActive
                ? "bg-[#EEEEEE] text-[#111827] font-semibold shadow-2xs"
                : "text-[#4B5563] hover:bg-[#F3F3F3] hover:text-[#111827] font-medium"
                }`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <Icon
                  size={16}
                  strokeWidth={isActive ? 2 : 1.75}
                  className={isActive ? "text-[#111827]" : "text-[#6B7280]"}
                />
                <span className="truncate">{item.name}</span>
              </div>
              {item.tag && (
                <span className="text-[11px] font-medium leading-4 px-2 py-0.5 rounded-full bg-white text-[#4B5563] border border-[#E5E5E5] shrink-0">
                  {item.tag}
                </span>
              )}
            </Link>
          );
        })}
      </div>

      {/* Subtle Workspace Status Indicator */}
      <div className="p-3 border-t border-[#E5E5E5] mt-auto">
        <div className="p-3 bg-white border border-[#E5E5E5] rounded-lg space-y-1.5">
          <div className="flex items-center justify-between text-xs font-medium leading-4 text-[#111827]">
            <span>System status</span>
            <span className="inline-flex items-center gap-1 text-[11px] font-medium leading-4 text-emerald-700">
              <CheckCircle2 size={12} strokeWidth={2} className="text-emerald-600" />
              Online
            </span>
          </div>
          <p className="text-xs font-normal leading-[18px] text-[#6B7280]">
            Autonomous agents operational with cloud run foundation.
          </p>
        </div>
      </div>
    </aside>
  );
};
