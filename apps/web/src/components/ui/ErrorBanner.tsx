import type { ReactNode } from "react";
import { describeError } from "@/lib/api/client";

export function ErrorBanner({
  error,
  action,
}: {
  error: unknown;
  action?: ReactNode;
}) {
  const { title, detail } = describeError(error);
  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-lg border border-danger/40 bg-danger/10 p-4 text-sm md:flex-row md:items-center md:justify-between"
    >
      <div>
        <p className="font-semibold text-danger">{title}</p>
        <p className="text-muted">{detail}</p>
      </div>
      {action}
    </div>
  );
}
