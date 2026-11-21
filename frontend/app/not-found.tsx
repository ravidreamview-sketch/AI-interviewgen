import React from "react";
import Link from "next/link";
import { EmptyState } from "../components/ui/EmptyState";
import { Button } from "../components/ui/Button";

export default function NotFound() {
  return (
    <div className="py-12 flex justify-center">
      <div className="max-w-md w-full">
        <EmptyState
          title="Module or Resource Not Found"
          description="The requested route does not exist or is currently unavailable."
        />
        <div className="mt-4 text-center">
          <Link href="/">
            <Button variant="primary" size="sm">
              Return to Platform Overview
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
