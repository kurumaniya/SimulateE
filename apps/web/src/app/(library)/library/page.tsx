"use client";

import { Suspense, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { ALL_SYSTEMS, GameSystem, systemName, type GameSort } from "@retroweb/shared";
import { useGames } from "@/lib/api/hooks";
import { GameGrid } from "@/components/games/GameGrid";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Skeleton } from "@/components/ui/Skeleton";

const SORTS: { value: GameSort; label: string }[] = [
  { value: "title", label: "Title" },
  { value: "recently_played", label: "Recently played" },
  { value: "recently_added", label: "Recently added" },
  { value: "play_time", label: "Play time" },
];

const PAGE_SIZE = 60;

function isSystem(value: string | null): value is GameSystem {
  return !!value && (Object.values(GameSystem) as string[]).includes(value);
}

function LibraryContent() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const q = params.get("q") ?? "";
  const system = isSystem(params.get("system")) ? (params.get("system") as GameSystem) : undefined;
  const favorite = params.get("favorite") === "true" ? true : undefined;
  const sort = (SORTS.find((s) => s.value === params.get("sort"))?.value ?? "title") as GameSort;
  const offset = Number(params.get("offset") ?? 0) || 0;

  const [searchText, setSearchText] = useState(q);
  // Keep the input in step with the URL (back/forward, sidebar links) without an effect.
  const [syncedQ, setSyncedQ] = useState(q);
  if (syncedQ !== q) {
    setSyncedQ(q);
    setSearchText(q);
  }

  const update = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === "") next.delete(key);
      else next.set(key, value);
    }
    if (!("offset" in changes)) next.delete("offset");
    const query = next.toString();
    router.replace((query ? `${pathname}?${query}` : pathname) as Route);
  };

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (searchText !== q) update({ q: searchText });
    }, 250);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounce only on text changes
  }, [searchText]);

  const { data, error, isLoading } = useGames({ q, system, favorite, sort, limit: PAGE_SIZE, offset });

  const title = favorite ? "Favorites" : system ? systemName(system) : "All Games";

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          {data && (
            <p className="text-sm text-muted">
              {data.total} {data.total === 1 ? "game" : "games"}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            type="search"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search games…"
            aria-label="Search games"
            className="w-56 rounded-lg border border-line bg-card px-3 py-2 text-sm placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <select
            value={system ?? ""}
            onChange={(e) => update({ system: e.target.value || undefined })}
            aria-label="Platform"
            className="rounded-lg border border-line bg-card px-3 py-2 text-sm"
          >
            <option value="">All platforms</option>
            {ALL_SYSTEMS.map((info) => (
              <option key={info.id} value={info.id}>
                {info.name}
              </option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(e) => update({ sort: e.target.value })}
            aria-label="Sort"
            className="rounded-lg border border-line bg-card px-3 py-2 text-sm"
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                Sort: {s.label}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 rounded-lg border border-line bg-card px-3 py-2 text-sm">
            <input
              type="checkbox"
              checked={!!favorite}
              onChange={(e) => update({ favorite: e.target.checked ? "true" : undefined })}
            />
            Favorites
          </label>
        </div>
      </header>

      {error && <ErrorBanner error={error} />}
      {isLoading && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[3/4]" />
          ))}
        </div>
      )}
      {data && data.items.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-muted">
          No games match these filters.
        </p>
      )}
      {data && data.items.length > 0 && (
        <GameGrid games={data.items} showPlayTime={sort === "play_time" || sort === "recently_played"} />
      )}
      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40"
            disabled={offset === 0}
            onClick={() => update({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}
          >
            Previous
          </button>
          <span className="text-muted">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}
          </span>
          <button
            className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40"
            disabled={offset + PAGE_SIZE >= data.total}
            onClick={() => update({ offset: String(offset + PAGE_SIZE) })}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

export default function LibraryPage() {
  return (
    <Suspense fallback={<Skeleton className="h-8 w-48" />}>
      <LibraryContent />
    </Suspense>
  );
}
