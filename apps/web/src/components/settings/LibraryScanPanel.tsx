"use client";

import { useEffect, useState } from "react";
import { useInvalidateLibrary, useJob, useStartScan } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

/** Scan data/roms in the background with live progress. */
export function LibraryScanPanel() {
  const start = useStartScan();
  const [jobId, setJobId] = useState<string | null>(null);
  const { data: job } = useJob(jobId);
  const invalidate = useInvalidateLibrary();

  const running = job?.status === "queued" || job?.status === "running";
  const counters = job?.counters ?? {};

  useEffect(() => {
    if (job?.status === "done" || job?.status === "failed") void invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react to status changes only
  }, [job?.status]);

  return (
    <section className="space-y-3 rounded-xl border border-line bg-card p-5">
      <h2 className="font-semibold">Library</h2>
      <p className="text-sm text-muted">
        Place your own ROM files under <code className="text-fg">data/roms/&lt;system&gt;/</code>{" "}
        (for example <code className="text-fg">data/roms/gba/</code>) and scan. Files are identified
        by hash, so re-scanning is safe. A <code className="text-fg">.m3u</code> listing the cue sheets
        of a multi-disc game makes them one entry.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          disabled={start.isPending || running}
          onClick={() => start.mutate(undefined, { onSuccess: (job) => setJobId(job.id) })}
        >
          {running ? "Scanning…" : "Scan library"}
        </Button>
        {job && (
          <span className="text-sm text-muted" aria-live="polite">
            {running
              ? `${job.done} / ${job.total} files`
              : job.status === "done"
                ? `Added ${counters.added ?? 0} · updated ${counters.updated ?? 0} · missing ${counters.missing ?? 0} · skipped ${counters.skipped ?? 0}`
                : "Scan stopped"}
          </span>
        )}
      </div>
      {running && job.total > 0 && (
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
