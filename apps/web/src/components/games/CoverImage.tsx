"use client";

import { useState } from "react";
import { systemInfo, type GameSummary } from "@retroweb/shared";
import { gamesApi } from "@/lib/api/games";

/** Cover art with a generated placeholder when the game has none. */
export function CoverImage({
  game,
  className = "",
  sizes = "200px",
}: {
  game: GameSummary & { updated_at?: string };
  className?: string;
  sizes?: string;
}) {
  const [failed, setFailed] = useState(false);
  const url = gamesApi.coverUrl(game);
  const info = systemInfo(game.system);
  if (!url || failed) {
    return (
      <div
        className={`flex h-full w-full flex-col justify-end overflow-hidden p-3 ${className}`}
        style={{
          background: `linear-gradient(160deg, ${info?.accent ?? "#444"}66 0%, #0c0e14 70%)`,
        }}
        aria-label={game.title}
      >
        <span className="line-clamp-3 text-sm font-semibold leading-tight text-fg/90">{game.title}</span>
        <span className="mt-1 text-[11px] uppercase tracking-wide text-fg/50">{info?.shortName}</span>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- covers are user uploads served by the API
    <img
      src={url}
      alt={game.title}
      sizes={sizes}
      loading="lazy"
      onError={() => setFailed(true)}
      className={`h-full w-full object-cover ${className}`}
    />
  );
}
