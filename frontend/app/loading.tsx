import React from "react";
import { LoadingSkeleton } from "../components/ui/LoadingSkeleton";

export default function Loading() {
  return (
    <div className="space-y-6">
      <LoadingSkeleton height="160px" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <LoadingSkeleton height="140px" />
        <LoadingSkeleton height="140px" />
        <LoadingSkeleton height="140px" />
      </div>
    </div>
  );
}
