"use client";

import Link from "next/link";
import type { GameSummary } from "@retroweb/shared";
import { formatPlayTime } from "@/lib/format";
import { CoverImage } from "./CoverImage";
import { PlatformBadge } from "./PlatformBadge";

export function GameCard({ game, showPlayTime = false }: { game: GameSummary; showPlayTime?: boolean }) {
  return (
    <Link
      href={`/games/${game.id}`}
      className="group block w-full shrink-0 focus:outline-none"
      aria-label={game.title}
    >
      <div className="relative aspect-[3/4] overflow-hidden rounded-xl bg-card ring-1 ring-line transition-all duration-200 group-hover:scale-[1.03] group-hover:ring-accent group-focus-visible:ring-accent">
        <CoverImage game={game} />
        <div className="absolute left-2 top-2 flex gap-1">
          <PlatformBadge system={game.system} className="backdrop-blur" />
        </div>
        {game.favorite && (
          <span className="absolute right-2 top-2 text-sm text-amber-300" aria-label="Favorite">
            ★
          </span>
        )}
        {game.rom_missing && (
          <span className="absolute inset-x-0 bottom-0 bg-danger/80 px-2 py-1 text-center text-[11px] font-semibold">
            ROM missing
          </span>
        )}
      </div>
      <div className="mt-2 px-0.5">
        <p className="truncate text-sm font-medium text-fg">{game.title}</p>
        {showPlayTime && (
          <p className="text-xs text-muted">{formatPlayTime(game.play_time_seconds)}</p>
        )}
      </div>
    </Link>
  );
}
