"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import type { GameDetail } from "@retroweb/shared";
import { systemName } from "@retroweb/shared";
import { usePlayerSession } from "./usePlayerSession";
import { PlayerToolbar } from "./PlayerToolbar";
import { Button } from "@/components/ui/Button";

const OVERLAY_HIDE_MS = 3000;

export function EmulatorPlayer({ game, resume }: { game: GameDetail; resume: boolean }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { state, containerRef, rootRef, actions } = usePlayerSession(game, resume);
  const [overlayVisible, setOverlayVisible] = useState(true);
  const hideTimer = useRef<number | undefined>(undefined);

  const running = state.phase === "running" || state.phase === "paused";

  // Hide the toolbar while playing; any pointer movement or Escape brings it back.
  useEffect(() => {
    const show = () => {
      setOverlayVisible(true);
      window.clearTimeout(hideTimer.current);
      if (state.phase === "running") {
        hideTimer.current = window.setTimeout(() => setOverlayVisible(false), OVERLAY_HIDE_MS);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") show();
    };
    show();
    window.addEventListener("pointermove", show);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointermove", show);
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(hideTimer.current);
    };
  }, [state.phase]);

  const handleQuit = async () => {
    await actions.quit();
    // Play time, saves and the resume point changed on the server.
    await queryClient.invalidateQueries();
    router.push(`/games/${game.id}`);
  };

  return (
    <div ref={rootRef} className="fixed inset-0 flex flex-col bg-black text-fg">
      <div className="relative flex-1 overflow-hidden">
        <div ref={containerRef} className="retroweb-emulator-host absolute inset-0" />

        {(state.phase === "booting" || state.phase === "loading") && (
          <StatusScreen
            title={state.phase === "booting" ? "Preparing emulator…" : `Loading ${game.title}…`}
            subtitle={systemName(game.system)}
          />
        )}
        {state.phase === "exiting" && (
          <StatusScreen title="Saving your progress…" subtitle="Uploading save data" />
        )}
        {state.phase === "error" && state.error && (
          <StatusScreen title={state.error.title} subtitle={state.error.detail} error>
            <div className="mt-6 flex gap-3">
              <Link href={`/games/${game.id}`}>
                <Button variant="secondary">Back to game</Button>
              </Link>
              {state.error.code === "rom_missing" && (
                <Link href="/settings">
                  <Button variant="primary">Open Settings</Button>
                </Link>
              )}
              {state.error.code === "assets_missing" && (
                <Link href="/settings">
                  <Button variant="primary">Check emulator status</Button>
                </Link>
              )}
            </div>
          </StatusScreen>
        )}

        {state.message && (
          <div className="pointer-events-none absolute bottom-16 left-1/2 -translate-x-1/2 rounded-full bg-black/70 px-4 py-1.5 text-sm backdrop-blur">
            {state.message}
          </div>
        )}

        <div
          className={`absolute inset-x-0 top-0 transition-opacity duration-300 ${
            overlayVisible || !running ? "opacity-100" : "pointer-events-none opacity-0"
          }`}
        >
          <PlayerToolbar
            game={game}
            state={state}
            running={running}
            onTogglePause={actions.togglePause}
            onReset={() => {
              if (window.confirm("Reset the game? Unsaved progress since the last in-game save is lost.")) {
                void actions.reset();
              }
            }}
            onSaveState={actions.saveState}
            onLoadState={actions.loadState}
            onScreenshot={actions.screenshot}
            onToggleMuted={actions.toggleMuted}
            onVolume={actions.setVolume}
            onScreenLayout={actions.setScreenLayout}
            onFullscreen={actions.toggleFullscreen}
            onQuit={handleQuit}
          />
        </div>
      </div>
    </div>
  );
}

function StatusScreen({
  title,
  subtitle,
  error,
  children,
}: {
  title: string;
  subtitle?: string;
  error?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-bg/95 p-8 text-center">
      {!error && <div className="mb-6 h-10 w-10 animate-spin rounded-full border-2 border-line border-t-accent" />}
      <h2 className={`text-xl font-semibold ${error ? "text-danger" : ""}`}>{title}</h2>
      {subtitle && <p className="mt-2 max-w-md text-sm text-muted">{subtitle}</p>}
      {children}
    </div>
  );
}
