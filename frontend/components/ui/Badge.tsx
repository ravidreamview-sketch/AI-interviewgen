import React from "react";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "danger" | "info" | "neutral";
  size?: "sm" | "md";
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = "default",
  size = "md",
  className = "",
}) => {
  const variantStyles = {
    default: "bg-[#F3F4F6] text-[#374151] border-[#E5E7EB]",
    success: "bg-[#ECFDF5] text-[#065F46] border-[#A7F3D0]",
    warning: "bg-[#FFFBEB] text-[#92400E] border-[#FDE68A]",
    danger: "bg-[#FEF2F2] text-[#991B1B] border-[#FECACA]",
    info: "bg-[#EFF6FF] text-[#1E40AF] border-[#BFDBFE]",
    neutral: "bg-[#F9FAFB] text-[#4B5563] border-[#E5E7EB]",
  };

  const sizeStyles = {
    sm: "px-2 py-0.5 text-[11px] leading-4 font-medium",
    md: "px-2.5 py-0.5 text-xs leading-4 font-medium",
  };

  return (
    <span
      className={`inline-flex items-center rounded-md border ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
    >
      {children}
    </span>
  );
};
