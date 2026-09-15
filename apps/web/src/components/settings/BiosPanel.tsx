"use client";

import { useRef, useState } from "react";
import { systemName, type SystemBiosOut } from "@retroweb/shared";
import { useBiosInventory, useDeleteBios, useUploadBios } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { formatBytes } from "@/lib/format";

/** Per-system BIOS status with upload and delete. Files are user-provided. */
export function BiosPanel() {
  const { data, error, isLoading } = useBiosInventory();
  return (
    <section className="space-y-4 rounded-xl border border-line bg-card p-5">
      <div>
        <h2 className="font-semibold">BIOS files</h2>
        <p className="text-sm text-muted">
          Some systems need a BIOS image from the console you own. Upload it here; nothing is ever
          downloaded for you. Files are checked against known digests where available.
        </p>
      </div>
      {error ? <ErrorBanner error={error} /> : null}
      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {data?.map((entry) => <SystemBiosCard key={entry.system} entry={entry} />)}
    </section>
  );
}

function SystemBiosCard({ entry }: { entry: SystemBiosOut }) {
  const upload = useUploadBios();
  const remove = useDeleteBios();
  const input = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<unknown>(null);
  const installed = entry.files.filter((f) => f.installed);

  return (
    <div className="rounded-lg border border-line bg-bg p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-medium">{systemName(entry.system)}</p>
          <p className="text-xs text-muted">{entry.note}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill entry={entry} />
          <input
            ref={input}
            type="file"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setUploadError(null);
              upload.mutate({ system: entry.system, file }, { onError: setUploadError });
              e.target.value = "";
            }}
          />
          <Button disabled={upload.isPending} onClick={() => input.current?.click()}>
            {upload.isPending ? "Uploading…" : "Upload BIOS"}
          </Button>
        </div>
      </div>
      {uploadError ? (
        <div className="mt-3">
          <ErrorBanner error={uploadError} />
        </div>
      ) : null}
      <ul className="mt-3 divide-y divide-line text-sm">
        {entry.files.map((file) => (
          <li key={file.filename} className="flex items-center justify-between gap-3 py-1.5">
            <div className="min-w-0">
              <span className="font-mono text-xs">{file.filename}</span>
              <span className="ml-2 text-muted">{file.description}</span>
            </div>
            <div className="flex items-center gap-3 text-xs">
              {file.installed ? (
                <>
                  <span className="text-muted">{formatBytes(file.size_bytes ?? 0)}</span>
                  <span
                    className={
                      file.verified === false
                        ? "text-amber-300"
                        : file.verified
                          ? "text-success"
                          : "text-muted"
                    }
                    title={file.md5 ? `MD5 ${file.md5}` : undefined}
                  >
                    {file.verified === false
                      ? "unverified digest"
                      : file.verified
                        ? "verified"
                        : "installed"}
                  </span>
                  <button
                    className="text-muted hover:text-danger"
                    onClick={() => {
                      if (window.confirm(`Remove ${file.filename}?`)) {
                        remove.mutate({ system: entry.system, filename: file.filename });
                      }
                    }}
                  >
                    Remove
                  </button>
                </>
              ) : (
                <span className="text-muted">not installed</span>
              )}
            </div>
          </li>
        ))}
      </ul>
      {installed.length === 0 && !entry.optional && (
        <p className="mt-2 text-xs text-danger">Required: games for this system will not start.</p>
      )}
    </div>
  );
}

function StatusPill({ entry }: { entry: SystemBiosOut }) {
  const installed = entry.files.some((f) => f.installed);
  const label = installed ? "Installed" : entry.optional ? "Optional" : "Missing";
  const color = installed ? "text-success" : entry.optional ? "text-muted" : "text-danger";
  return <span className={`text-xs font-medium ${color}`}>{label}</span>;
}
