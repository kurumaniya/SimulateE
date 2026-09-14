import { systemInfo, type GameSystem } from "@retroweb/shared";

export function PlatformBadge({ system, className = "" }: { system: GameSystem; className?: string }) {
  const info = systemInfo(system);
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${className}`}
      style={{ background: `${info?.accent ?? "#444"}33`, color: info?.accent ?? "#ccc" }}
    >
      {info?.shortName ?? system}
    </span>
  );
}
