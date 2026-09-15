"use client";

import Link from "next/link";
import { use, useRef, useState } from "react";
import { systemName, AUTO_STATE_SLOT, type SaveOut } from "@retroweb/shared";
import {
  useDeleteSave,
  useGame,
  useSaves,
  useSystemBios,
  useToggleFavorite,
  useUploadCover,
} from "@/lib/api/hooks";
import { savesApi } from "@/lib/api/games";
import { formatBytes, formatDate, formatPlayTime, formatRelative } from "@/lib/format";
import { getEmulatorRegistry } from "@/lib/emulator/registry";
import { CoverImage } from "@/components/games/CoverImage";
import { PlatformBadge } from "@/components/games/PlatformBadge";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Skeleton } from "@/components/ui/Skeleton";

export default function GamePage(props: PageProps<"/games/[id]">) {
  const { id } = use(props.params);
  const { data: game, error, isLoading } = useGame(id);
  const { data: saves } = useSaves(id);
  const { data: bios } = useSystemBios(game?.system);
  const favorite = useToggleFavorite();
  const uploadCover = useUploadCover();
  const deleteSave = useDeleteSave();
  const coverInput = useRef<HTMLInputElement>(null);
  const [coverError, setCoverError] = useState<unknown>(null);

  if (isLoading) {
    return (
      <div className="flex gap-8">
        <Skeleton className="aspect-[3/4] w-64" />
        <div className="flex-1 space-y-4">
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-4 w-1/3" />
        </div>
      </div>
    );
  }
  if (error || !game) return <ErrorBanner error={error} />;

  const supported = getEmulatorRegistry().supports(game.system);
  const canPlay = supported && !game.rom_missing;
  const batterySave = saves?.find((s) => s.save_type === "battery");
  const autoState = saves?.find((s) => s.save_type === "state" && s.slot === AUTO_STATE_SLOT);
  const manualStates = (saves ?? []).filter((s) => s.save_type === "state" && s.slot !== AUTO_STATE_SLOT);

  return (
    <div className="space-y-10">
      <div className="flex flex-col gap-8 md:flex-row">
        <div className="w-full max-w-xs shrink-0 space-y-3">
          <div className="aspect-[3/4] overflow-hidden rounded-2xl bg-card ring-1 ring-line">
            <CoverImage game={game} sizes="320px" />
          </div>
          <input
            ref={coverInput}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setCoverError(null);
              uploadCover.mutate({ id: game.id, file }, { onError: setCoverError });
              e.target.value = "";
            }}
          />
          <Button
            variant="ghost"
            className="w-full"
            disabled={uploadCover.isPending}
            onClick={() => coverInput.current?.click()}
          >
            {uploadCover.isPending ? "Uploading…" : game.has_cover ? "Replace cover" : "Upload cover"}
          </Button>
          {coverError ? <ErrorBanner error={coverError} /> : null}
        </div>

        <div className="flex-1 space-y-6">
          <div>
            <div className="flex items-center gap-3">
              <PlatformBadge system={game.system} />
              {game.region && <span className="text-xs text-muted">{game.region}</span>}
            </div>
            <h1 className="mt-2 text-3xl font-bold tracking-tight">{game.title}</h1>
            <p className="text-sm text-muted">{systemName(game.system)}</p>
          </div>

          <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:grid-cols-3">
            <Meta label="Released" value={formatDate(game.release_date)} />
            <Meta label="Developer" value={game.developer ?? "Unknown"} />
            <Meta label="Publisher" value={game.publisher ?? "Unknown"} />
            <Meta label="Play time" value={formatPlayTime(game.play_time_seconds)} />
            <Meta label="Last played" value={formatRelative(game.last_played_at)} />
            <Meta label="File" value={game.rom_filename ?? "—"} mono />
          </dl>

          <div className="flex flex-wrap gap-3">
            {game.has_auto_state ? (
              <>
                <PlayLink id={game.id} resume disabled={!canPlay} label="Resume" primary />
                <PlayLink id={game.id} disabled={!canPlay} label="Play" />
              </>
            ) : (
              <PlayLink id={game.id} disabled={!canPlay} label="Play" primary />
            )}
            <Button
              variant="secondary"
              onClick={() => favorite.mutate({ id: game.id, favorite: !game.favorite })}
              disabled={favorite.isPending}
            >
              {game.favorite ? "★ Favorited" : "☆ Favorite"}
            </Button>
          </div>

          {!supported && (
            <p className="text-sm text-muted">
              No emulator is available for {systemName(game.system)} yet.
            </p>
          )}
          {game.rom_missing && (
            <ErrorBanner error={{ code: "rom_missing" }} />
          )}
          {bios && (
            <p className="text-sm text-muted">
              {bios.preferred_file ? (
                <>
                  BIOS: <span className="font-mono text-xs text-fg">{bios.preferred_file}</span>
                </>
              ) : bios.optional ? (
                <>
                  No BIOS installed; the emulator falls back to built-in emulation, which may not
                  work for every game.{" "}
                  <Link href="/settings" className="underline">
                    Upload one in Settings
                  </Link>
                  .
                </>
              ) : (
                <>
                  This system needs a BIOS file.{" "}
                  <Link href="/settings" className="underline">
                    Upload it in Settings
                  </Link>
                  .
                </>
              )}
            </p>
          )}
          {game.files.length > 1 && (
            <ul className="text-xs text-muted">
              {game.files.map((file) => (
                <li key={file.id} className="font-mono">
                  {file.filename}
                  <span className="ml-2 font-sans">
                    {file.role === "companion" ? "track" : "main"} · {formatBytes(file.size_bytes)}
                    {file.missing ? " · missing" : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {game.description && <p className="max-w-2xl text-sm text-fg/80">{game.description}</p>}
        </div>
      </div>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Saves</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <SaveCard
            title="Battery save"
            description="Created by the game itself (in-game save). Synced automatically."
            save={batterySave}
            onDelete={(save) => deleteSave.mutate({ saveId: save.id, gameId: game.id })}
          />
          <SaveCard
            title="Resume point"
            description="Automatic save state captured when you quit."
            save={autoState}
            onDelete={(save) => deleteSave.mutate({ saveId: save.id, gameId: game.id })}
          />
          {manualStates.map((save) => (
            <SaveCard
              key={save.id}
              title={`Save state · slot ${save.slot}`}
              description={`${save.core_id ?? save.emulator_id} ${save.core_version ?? ""}`}
              save={save}
              onDelete={(row) => deleteSave.mutate({ saveId: row.id, gameId: game.id })}
            />
          ))}
        </div>
      </section>
    </div>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
      <dd className={`mt-0.5 truncate ${mono ? "font-mono text-xs" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}

function PlayLink({
  id,
  resume,
  disabled,
  label,
  primary,
}: {
  id: string;
  resume?: boolean;
  disabled: boolean;
  label: string;
  primary?: boolean;
}) {
  const href = { pathname: `/play/${id}`, query: resume ? { resume: "1" } : undefined };
  if (disabled) {
    return (
      <Button variant={primary ? "primary" : "secondary"} disabled>
        ▶ {label}
      </Button>
    );
  }
  return (
    <Link href={href}>
      <Button variant={primary ? "primary" : "secondary"} className="min-w-28">
        ▶ {label}
      </Button>
    </Link>
  );
}

function SaveCard({
  title,
  description,
  save,
  onDelete,
}: {
  title: string;
  description: string;
  save?: SaveOut;
  onDelete: (save: SaveOut) => void;
}) {
  const screenshot = save ? savesApi.screenshotUrl(save) : null;
  return (
    <div className="flex gap-4 rounded-xl border border-line bg-card p-4">
      <div className="h-20 w-28 shrink-0 overflow-hidden rounded-md bg-bg">
        {screenshot ? (
          // eslint-disable-next-line @next/next/no-img-element -- served by the API
          <img src={screenshot} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted">
            {save ? "No image" : "—"}
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium">{title}</p>
        <p className="text-xs text-muted">{description}</p>
        {save ? (
          <p className="mt-2 text-xs text-muted">
            {formatBytes(save.size_bytes)} · updated {formatRelative(save.updated_at)}
          </p>
        ) : (
          <p className="mt-2 text-xs text-muted">None yet</p>
        )}
      </div>
      {save && (
        <button
          className="self-start text-xs text-muted hover:text-danger"
          onClick={() => {
            if (window.confirm(`Delete ${title.toLowerCase()}? This cannot be undone.`)) onDelete(save);
          }}
        >
          Delete
        </button>
      )}
    </div>
  );
}
