"use client";

import React from "react";
import Link from "next/link";
import { Compass, User as UserIcon } from "lucide-react";

interface HeaderProps {
  userEmail?: string;
  userRole?: string;
}

export const Header: React.FC<HeaderProps> = ({
  userEmail = "candidate@example.com",
  userRole = "candidate",
}) => {
  return (
    <header className="h-14 border-b border-[#E5E5E5] bg-white px-6 flex items-center justify-between sticky top-0 z-30">
      {/* Brand & Context */}
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-[#111827] text-white flex items-center justify-center transition-colors">
            <Compass size={18} strokeWidth={1.75} />
          </div>
          <div>
            <h1 className="font-semibold text-base leading-6 text-[#111827] tracking-tight">
              AI Interview Studio
            </h1>
            <p className="text-xs font-normal text-[#6B7280] leading-4">
              Adaptive Learning & Career Readiness
            </p>
          </div>
        </Link>
      </div>

      {/* User Info */}
      <div className="flex items-center gap-3">
        <div className="text-right hidden sm:block">
          <p className="text-[13px] font-medium leading-[18px] text-[#111827]">{userEmail}</p>
          <p className="text-xs font-normal leading-4 text-[#6B7280] capitalize">{userRole}</p>
        </div>
        <div className="w-8 h-8 rounded-full bg-[#F3F3F3] text-[#374151] flex items-center justify-center text-xs font-medium border border-[#E5E5E5]">
          {userEmail ? userEmail.charAt(0).toUpperCase() : <UserIcon size={14} strokeWidth={1.75} />}
        </div>
      </div>
    </header>
  );
};
