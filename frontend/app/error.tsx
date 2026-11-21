"use client";

import React from "react";
import { Button } from "../components/ui/Button";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center border border-red-800/40 bg-red-950/20 rounded-2xl my-8">
      <div className="w-12 h-12 rounded-full bg-red-900/50 flex items-center justify-center text-red-400 text-xl font-bold mb-4">
        !
      </div>
      <h2 className="text-lg font-semibold text-white">Application Exception Encountered</h2>
      <p className="mt-1 text-xs text-red-300 max-w-md font-mono bg-red-950/40 p-2 rounded-lg mt-3">
        {error.message || "An unexpected error occurred during rendering."}
      </p>
      <div className="mt-6 flex gap-3">
        <Button variant="danger" size="sm" onClick={() => reset()}>
          Try Again
        </Button>
        <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
          Reload Page
        </Button>
      </div>
    </div>
  );
}
