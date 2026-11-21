import React from "react";

interface CardProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
  className?: string;
}

export const Card: React.FC<CardProps> = ({
  children,
  title,
  subtitle,
  action,
  className = "",
}) => {
  return (
    <div className={`bg-white border border-[#E5E5E5] rounded-xl p-5 shadow-xs ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between pb-3.5 mb-3.5 border-b border-[#F0F0F0]">
          <div>
            {title && <h3 className="text-base font-semibold text-[#111827] leading-6 tracking-tight">{title}</h3>}
            {subtitle && <p className="text-sm font-normal text-[#6B7280] leading-[22px] mt-0.5">{subtitle}</p>}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
};

export const CardHeader: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = "",
}) => <div className={`pb-3 mb-3 border-b border-[#F0F0F0] ${className}`}>{children}</div>;

export const CardContent: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className = "",
}) => <div className={className}>{children}</div>;
