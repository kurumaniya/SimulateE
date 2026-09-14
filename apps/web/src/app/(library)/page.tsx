"use client";

import Link from "next/link";
import { useHome } from "@/lib/api/hooks";
import { GameSection } from "@/components/games/GameSection";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import { APP_NAME } from "@/lib/config";

export default function HomePage() {
  const { data, error, isLoading, refetch } = useHome();

  if (isLoading) {
    return (
      <div className="space-y-8">
        <Skeleton className="h-8 w-48" />
        <div className="flex gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[3/4] w-40" />
          ))}
        </div>
      </div>
    );
  }
  if (error || !data) {
    return <ErrorBanner error={error} action={<Button onClick={() => refetch()}>Retry</Button>} />;
  }

  const empty =
    data.recently_added.length === 0 &&
    data.recently_played.length === 0 &&
    data.continue_playing.length === 0;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">{APP_NAME} Library</h1>
        <p className="text-sm text-muted">Your collection, playable in the browser.</p>
      </header>

      {empty ? (
        <div className="rounded-2xl border border-dashed border-line p-10 text-center">
          <h2 className="text-lg font-semibold">Your library is empty</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
            Copy your own game files into <code className="text-fg">data/roms/gba/</code> and scan the
            library, or upload a ROM from Settings.
          </p>
          <Link href="/settings" className="mt-6 inline-block">
            <Button variant="primary">Go to Settings</Button>
          </Link>
        </div>
      ) : (
        <>
          <GameSection title="Continue Playing" games={data.continue_playing} showPlayTime />
          <GameSection
            title="Recently Played"
            games={data.recently_played}
            href="/library?sort=recently_played"
            showPlayTime
          />
          <GameSection
            title="Recently Added"
            games={data.recently_added}
            href="/library?sort=recently_added"
          />
          <GameSection title="Favorites" games={data.favorites} href="/library?favorite=true" />
        </>
      )}
    </div>
  );
}
