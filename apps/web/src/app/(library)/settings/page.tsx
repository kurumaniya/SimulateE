"use client";

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ALL_SYSTEMS, GameSystem, type ScanResult } from "@retroweb/shared";
import { useScanLibrary, useSystems, useUploadRom } from "@/lib/api/hooks";
import { getEmulatorRegistry, EMULATORJS_ASSETS_URL } from "@/lib/emulator/registry";
import { useBrowserCapabilities } from "@/lib/emulator/useBrowserCapabilities";
import { BiosPanel } from "@/components/settings/BiosPanel";
import { CoverArtPanel } from "@/components/settings/CoverArtPanel";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { APP_NAME } from "@/lib/config";

export default function SettingsPage() {
  const scan = useScanLibrary();
  const upload = useUploadRom();
  const { data: systems } = useSystems();
  const [uploadSystem, setUploadSystem] = useState<GameSystem>(GameSystem.GBA);
  const [lastScan, setLastScan] = useState<ScanResult | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const capabilities = useBrowserCapabilities();
  const { data: assetsInstalled } = useQuery({
    queryKey: ["emulator-assets"],
    queryFn: () =>
      fetch(`${EMULATORJS_ASSETS_URL}retroweb-manifest.json`, { method: "HEAD" })
        .then((r) => r.ok)
        .catch(() => false),
  });

  const registry = getEmulatorRegistry();

  return (
    <div className="max-w-3xl space-y-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted">{APP_NAME} manages only the game files you provide.</p>
      </header>

      <section className="space-y-3 rounded-xl border border-line bg-card p-5">
        <h2 className="font-semibold">Library</h2>
        <p className="text-sm text-muted">
          Place your own ROM files under <code className="text-fg">data/roms/&lt;system&gt;/</code>{" "}
          (for example <code className="text-fg">data/roms/gba/</code>) and scan. Files are identified
          by hash, so re-scanning is safe.
        </p>
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            disabled={scan.isPending}
            onClick={() => scan.mutate(undefined, { onSuccess: setLastScan })}
          >
            {scan.isPending ? "Scanning…" : "Scan library"}
          </Button>
          {lastScan && (
            <span className="text-sm text-muted">
              Added {lastScan.added} · updated {lastScan.updated} · missing {lastScan.missing} ·
              skipped {lastScan.skipped}
            </span>
          )}
        </div>
        {scan.error ? <ErrorBanner error={scan.error} /> : null}
        {lastScan && lastScan.errors.length > 0 && (
          <ul className="list-disc pl-5 text-xs text-danger">
            {lastScan.errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3 rounded-xl border border-line bg-card p-5">
        <h2 className="font-semibold">Upload a ROM</h2>
        <p className="text-sm text-muted">
          Upload a game you own. It is stored in the library folder and scanned immediately.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={uploadSystem}
            onChange={(e) => setUploadSystem(e.target.value as GameSystem)}
            className="rounded-lg border border-line bg-bg px-3 py-2 text-sm"
            aria-label="System"
          >
            {ALL_SYSTEMS.map((info) => (
              <option key={info.id} value={info.id}>
                {info.name} ({info.extensions.join(", ")})
              </option>
            ))}
          </select>
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate({ file, system: uploadSystem });
              e.target.value = "";
            }}
          />
          <Button disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
            {upload.isPending ? "Uploading…" : "Choose file…"}
          </Button>
          {upload.data && (
            <span className="text-sm text-success">Added “{upload.data.title}”</span>
          )}
        </div>
        {upload.error ? <ErrorBanner error={upload.error} /> : null}
      </section>

      <CoverArtPanel />

      <BiosPanel />

      <section className="space-y-3 rounded-xl border border-line bg-card p-5">
        <h2 className="font-semibold">Emulators</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="py-1 pr-4 font-medium">System</th>
              <th className="py-1 pr-4 font-medium">Adapter</th>
              <th className="py-1 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {(systems ?? []).map((system) => {
              const adapter = registry.adapterIdFor(system.id);
              return (
                <tr key={system.id} className="border-t border-line">
                  <td className="py-1.5 pr-4">{system.name}</td>
                  <td className="py-1.5 pr-4 text-muted">{adapter ?? "—"}</td>
                  <td className="py-1.5">
                    {adapter ? (
                      <span className="text-success">Working</span>
                    ) : (
                      <span className="text-muted">Planned</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="text-sm">
          Emulator runtime assets:{" "}
          {assetsInstalled === undefined ? (
            <span className="text-muted">checking…</span>
          ) : assetsInstalled ? (
            <span className="text-success">installed</span>
          ) : (
            <span className="text-danger">
              missing — run <code>npm run fetch-emulator</code> on the server
            </span>
          )}
        </p>
      </section>

      <section className="space-y-3 rounded-xl border border-line bg-card p-5">
        <h2 className="font-semibold">Browser capabilities</h2>
        {capabilities ? (
          <ul className="grid grid-cols-2 gap-2 text-sm">
            {(
              [
                ["WebAssembly", capabilities.webAssembly],
                ["WebGL", capabilities.webgl],
                ["WebGL 2", capabilities.webgl2],
                ["SharedArrayBuffer (threads)", capabilities.sharedArrayBuffer],
                ["Cross-origin isolated", capabilities.crossOriginIsolated],
                ["Gamepad API", capabilities.gamepad],
                ["IndexedDB", capabilities.indexedDb],
                ["Fullscreen", capabilities.fullscreen],
                ["Web Audio", capabilities.audioContext],
              ] as [string, boolean][]
            ).map(([label, ok]) => (
              <li key={label} className="flex items-center gap-2">
                <span className={ok ? "text-success" : "text-danger"}>{ok ? "●" : "○"}</span>
                {label}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Detecting…</p>
        )}
      </section>

      <section className="space-y-2 rounded-xl border border-line bg-card p-5 text-sm text-muted">
        <h2 className="font-semibold text-fg">Legal</h2>
        <p>
          Emulator software is not the same as copyrighted game ROMs. {APP_NAME} never downloads
          games or BIOS files; it only catalogs and runs files you place in its data directory.
        </p>
      </section>
    </div>
  );
}
