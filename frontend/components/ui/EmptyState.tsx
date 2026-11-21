import React from "react";
import { Button } from "./Button";

interface EmptyStateProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  actionLabel,
  onAction,
  icon,
}) => {
  return (
    <div className="text-center py-12 px-4 border border-dashed border-[#E5E5E5] rounded-xl bg-[#FAFAFA]">
      {icon && <div className="flex justify-center mb-3 text-[#6B7280]">{icon}</div>}
      <h3 className="text-sm font-semibold text-[#111827]">{title}</h3>
      <p className="mt-1 text-xs text-[#6B7280] max-w-sm mx-auto leading-relaxed">{description}</p>
      {actionLabel && onAction && (
        <div className="mt-4">
          <Button variant="secondary" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      )}
    </div>
  );
};
