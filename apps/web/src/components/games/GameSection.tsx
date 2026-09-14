import Link from "next/link";
import type { Route } from "next";
import type { GameSummary } from "@retroweb/shared";
import { GameCard } from "./GameCard";

export function GameSection({
  title,
  games,
  href,
  showPlayTime,
  emptyText,
}: {
  title: string;
  games: GameSummary[];
  href?: Route;
  showPlayTime?: boolean;
  emptyText?: string;
}) {
  if (games.length === 0 && !emptyText) return null;
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
        {href && (
          <Link href={href} className="text-sm text-muted hover:text-fg">
            See all
          </Link>
        )}
      </div>
      {games.length === 0 ? (
        <p className="text-sm text-muted">{emptyText}</p>
      ) : (
        <div className="hide-scrollbar -mx-1 flex gap-4 overflow-x-auto px-1 pb-2">
          {games.map((game) => (
            <div key={game.id} className="w-36 shrink-0 sm:w-40 lg:w-44">
              <GameCard game={game} showPlayTime={showPlayTime} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
