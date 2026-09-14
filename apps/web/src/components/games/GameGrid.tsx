import type { GameSummary } from "@retroweb/shared";
import { GameCard } from "./GameCard";

export function GameGrid({ games, showPlayTime }: { games: GameSummary[]; showPlayTime?: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8">
      {games.map((game) => (
        <GameCard key={game.id} game={game} showPlayTime={showPlayTime} />
      ))}
    </div>
  );
}
