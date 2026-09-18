"use client";

import { useEffect, useState } from "react";
import { useFetchCovers, useInvalidateLibrary, useJob } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

/** Fetch box art for every game without a cover, with live progress. */
export function CoverArtPanel() {
  const start = useFetchCovers();
  const [jobId, setJobId] = useState<string | null>(null);
  const { data: job } = useJob(jobId);
  const invalidate = useInvalidateLibrary();

  const running = job?.status === "queued" || job?.status === "running";

  // Covers appear in the library as the job finishes.
  useEffect(() => {
    if (job?.status === "done" || job?.status === "failed") void invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react to status changes only
  }, [job?.status]);

  const counters = job?.counters ?? {};

  return (
    <section className="space-y-3 rounded-xl border border-line bg-card p-5">
      <h2 className="font-semibold">Cover art</h2>
      <p className="text-sm text-muted">
        Box art is looked up by file name in the{" "}
        <a
          href="https://github.com/libretro-thumbnails/libretro-thumbnails"
          target="_blank"
          rel="noreferrer"
          className="underline"
        >
          libretro-thumbnails
        </a>{" "}
        collection. Files named in No-Intro / Redump style (
        <code className="text-fg">Title (Region).ext</code>) match best. Only images are
        downloaded, never games. Each game page also has a “Fetch cover online” button.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          disabled={start.isPending || running}
          onClick={() => start.mutate(undefined, { onSuccess: (job) => setJobId(job.id) })}
        >
          {running ? "Fetching…" : "Fetch missing covers"}
        </Button>
        {job && (
          <span className="text-sm text-muted" aria-live="polite">
            {job.done} / {job.total}
            {counters.fetched ? ` · found ${counters.fetched}` : ""}
            {counters.not_found ? ` · not found ${counters.not_found}` : ""}
            {counters.failed ? ` · failed ${counters.failed}` : ""}
            {job.status === "done" && " · done"}
            {job.status === "failed" && " · stopped"}
          </span>
        )}
      </div>
      {job && job.total > 0 && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg">
          <div
            className="h-full bg-accent transition-[width]"
            style={{ width: `${Math.round((job.done / job.total) * 100)}%` }}
          />
        </div>
      )}
      {start.error ? <ErrorBanner error={start.error} /> : null}
      {job && job.errors.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-danger">
          {job.errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
