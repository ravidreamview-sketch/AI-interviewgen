import React from "react";

interface SkeletonProps {
  className?: string;
  lines?: number;
  height?: string;
}

export const LoadingSkeleton: React.FC<SkeletonProps> = ({ className = "h-4 w-full", lines = 1, height }) => {
  const style = height ? { height } : undefined;
  return (
    <div className="space-y-2 animate-pulse">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} style={style} className={`bg-[#F3F4F6] rounded-md ${className}`} />
      ))}
    </div>
  );
};
