"use client";

import { useEffect, useState } from "react";
import type { JobOut } from "@retroweb/shared";
import { useFetchCovers, useIdentifyLibrary, useInvalidateLibrary, useJob } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

const COUNTER_LABELS: [string, string][] = [
  ["hash", "by digest"],
  ["serial", "by serial"],
  ["name", "by name"],
  ["fetched", "found"],
  ["not_found", "not found"],
  ["failed", "failed"],
];

function summary(job: JobOut): string {
  const parts = [`${job.done} / ${job.total}`];
  for (const [key, label] of COUNTER_LABELS) {
    if (job.counters[key]) parts.push(`${label} ${job.counters[key]}`);
  }
  if (job.status === "done") parts.push("done");
  if (job.status === "failed") parts.push("stopped");
  return parts.join(" · ");
}

/** Identify games against the public name lists and fetch box art, with live progress. */
export function CoverArtPanel() {
  const identify = useIdentifyLibrary();
  const covers = useFetchCovers();
  const [jobId, setJobId] = useState<string | null>(null);
  const { data: job } = useJob(jobId);
  const invalidate = useInvalidateLibrary();

  const running = job?.status === "queued" || job?.status === "running";
  const busy = running || identify.isPending || covers.isPending;

  // Names and covers appear in the library as the job finishes.
  useEffect(() => {
    if (job?.status === "done" || job?.status === "failed") void invalidate();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react to status changes only
  }, [job?.status]);

  const startError = identify.error ?? covers.error;

  return (
    <section className="space-y-3 rounded-xl border border-line bg-card p-5">
      <h2 className="font-semibold">Game identification and cover art</h2>
      <p className="text-sm text-muted">
        Each file is matched against the No-Intro / Redump release lists of{" "}
        <a
          href="https://github.com/libretro/libretro-database"
          target="_blank"
          rel="noreferrer"
          className="underline"
        >
          libretro-database
        </a>
        : first by its digest, then by the serial stored inside the image (this is what recognises
        translated or patched ROMs with a home-made file name), then by name. A match gives the
        game its English title, developer, publisher and release year, and the name its box art is
        filed under in the{" "}
        <a
          href="https://github.com/libretro-thumbnails/libretro-thumbnails"
          target="_blank"
          rel="noreferrer"
          className="underline"
        >
          libretro-thumbnails
        </a>{" "}
        collection. Only name lists and images are downloaded, never games. Fetching covers
        identifies games first, so one click does both.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          disabled={busy}
          onClick={() => covers.mutate(undefined, { onSuccess: (started) => setJobId(started.id) })}
        >
          {running && job?.kind === "covers.fetch" ? "Fetching…" : "Fetch missing covers"}
        </Button>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => identify.mutate(undefined, { onSuccess: (started) => setJobId(started.id) })}
        >
          {running && job?.kind === "library.identify" ? "Identifying…" : "Identify games"}
        </Button>
        {job && (
          <span className="text-sm text-muted" aria-live="polite">
            {summary(job)}
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
      {startError ? <ErrorBanner error={startError} /> : null}
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
