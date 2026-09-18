"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuthStatus } from "@/lib/api/hooks";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

/**
 * In multi-user mode, sends visitors without a login to /login before any
 * library page renders. In single-user mode it is transparent.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { data, error, isLoading } = useAuthStatus();
  const locked = !!data && data.mode === "multi" && !data.user;

  useEffect(() => {
    if (locked) router.replace("/login");
  }, [locked, router]);

  if (isLoading) {
    return <div className="flex h-dvh items-center justify-center text-sm text-muted">Loading…</div>;
  }
  if (error) {
    return (
      <div className="mx-auto max-w-lg p-8">
        <ErrorBanner error={error} />
      </div>
    );
  }
  if (locked) return null;
  return <>{children}</>;
}
