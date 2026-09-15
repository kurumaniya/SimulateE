"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AUTO_STATE_SLOT, type GameDetail } from "@retroweb/shared";
import {
  EmulatorError,
  detectBrowserCapabilities,
  missingCapabilities,
  type EmulatorAdapter,
  type ScreenLayout,
} from "@retroweb/emulator-core";
import { biosApi, gamesApi, savesApi } from "@/lib/api/games";
import { getEmulatorRegistry, EMULATORJS_ASSETS_URL } from "@/lib/emulator/registry";
import { SaveSyncManager, resolveBatterySave, type SyncStatus } from "@/lib/saves/SaveSyncManager";
import { PlaySessionTracker } from "@/lib/play/PlaySessionTracker";

export type PlayerPhase = "booting" | "loading" | "running" | "paused" | "exiting" | "error";

export interface PlayerError {
  code: string;
  title: string;
  detail: string;
}

export interface PlayerState {
  phase: PlayerPhase;
  error: PlayerError | null;
  syncStatus: SyncStatus;
  syncDetail?: string;
  message: string | null;
  muted: boolean;
  volume: number;
  /** Layouts the running system offers; empty for single-screen consoles. */
  screenLayouts: ScreenLayout[];
  screenLayout: string | null;
}

const VOLUME_KEY = "retroweb.volume";
const MUTED_KEY = "retroweb.muted";
/** Preferred screen layout is remembered per system, not per game. */
const layoutKey = (system: string) => `retroweb.layout.${system}`;

function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function toPlayerError(error: unknown): PlayerError {
  if (error instanceof EmulatorError) {
    switch (error.code) {
      case "rom_missing":
        return { code: error.code, title: "ROM missing", detail: error.message };
      case "rom_download_failed":
        return { code: error.code, title: "Download failed", detail: error.message };
      case "assets_missing":
        return { code: error.code, title: "Emulator not installed", detail: error.message };
      case "bios_missing":
        return { code: error.code, title: "BIOS required", detail: error.message };
      case "unsupported_system":
        return { code: error.code, title: "Unsupported system", detail: error.message };
      case "unsupported_browser":
        return { code: error.code, title: "Unsupported browser", detail: error.message };
      default:
        return { code: error.code, title: "Emulator failed to load", detail: error.message };
    }
  }
  const message = error instanceof Error ? error.message : String(error);
  return { code: "unknown", title: "Something failed", detail: message };
}

/**
 * Owns the emulator lifecycle for one play: boot → load → run → quit.
 * Components only render `state` and call the returned actions.
 */
export function usePlayerSession(game: GameDetail | undefined, resume: boolean) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const adapterRef = useRef<EmulatorAdapter | null>(null);
  const syncRef = useRef<SaveSyncManager | null>(null);
  const trackerRef = useRef<PlaySessionTracker | null>(null);
  const quittingRef = useRef(false);
  const messageTimer = useRef<number | undefined>(undefined);

  const [state, setState] = useState<PlayerState>(() => ({
    phase: "booting",
    error: null,
    syncStatus: "idle",
    message: null,
    muted: false,
    volume: 0.7,
    screenLayouts: [],
    screenLayout: null,
  }));

  const patch = useCallback((changes: Partial<PlayerState>) => {
    setState((prev) => ({ ...prev, ...changes }));
  }, []);

  const flash = useCallback(
    (message: string) => {
      patch({ message });
      window.clearTimeout(messageTimer.current);
      messageTimer.current = window.setTimeout(() => patch({ message: null }), 2500);
    },
    [patch],
  );

  const focusEmulator = useCallback(() => {
    const host = containerRef.current?.firstElementChild as HTMLElement | null;
    host?.focus?.();
  }, []);

  // Boot once the game is known and the container exists.
  useEffect(() => {
    if (!game || !containerRef.current) return;
    let cancelled = false;
    const container = containerRef.current;
    const volume = readStored(VOLUME_KEY, 0.7);
    const muted = readStored(MUTED_KEY, false);
    patch({ volume, muted });

    const run = async () => {
      if (game.rom_missing) {
        throw new EmulatorError("rom_missing", "The ROM file for this game is missing on the server.");
      }
      const adapter = getEmulatorRegistry().getEmulator(game.system);
      adapterRef.current = adapter;
      const capabilities = detectBrowserCapabilities();
      const missing = missingCapabilities(capabilities, adapter.capabilityRequirements(game.system));
      if (missing.length > 0) {
        throw new EmulatorError(
          "unsupported_browser",
          `This browser lacks: ${missing.map((m) => m.label).join(", ")}. Use a recent Chrome, Edge or Safari.`,
        );
      }
      const preferredLayout = readStored<string | null>(layoutKey(game.system), null);
      await adapter.initialize({
        container,
        fullscreenTarget: rootRef.current ?? container,
        assetsBaseUrl: EMULATORJS_ASSETS_URL,
        volume,
        muted,
        threads: false,
        adapterOptions: preferredLayout ? { screenLayout: preferredLayout } : undefined,
      });
      if (cancelled) return;
      patch({ phase: "loading" });
      const onSyncStatus = (status: SyncStatus, detail?: string) =>
        patch({ syncStatus: status, syncDetail: detail });
      const [bios, batterySave] = await Promise.all([
        biosApi.forSystem(game.system).catch(() => null),
        resolveBatterySave(game.id, onSyncStatus),
      ]);
      await adapter.loadGame({
        gameId: game.id,
        title: game.title,
        system: game.system,
        romUrl: gamesApi.romUrl(game),
        romFilename: game.rom_filename ?? "game",
        biosUrl: bios?.preferred_file
          ? biosApi.fileUrl(game.system, bios.preferred_file)
          : undefined,
        biosFiles: (bios?.files ?? [])
          .filter((file) => file.installed)
          .map((file) => ({
            filename: file.filename,
            url: biosApi.fileUrl(game.system, file.filename),
          })),
        companionFiles: game.files
          .filter((file) => file.role === "companion")
          .map((file) => ({ filename: file.filename, url: gamesApi.fileUrl(game, file) })),
        batterySave: batterySave?.data,
      });
      if (cancelled) return;

      const tracker = new PlaySessionTracker(game.id, adapter.id);
      trackerRef.current = tracker;
      await tracker.start().catch((error) => console.warn("play session start failed", error));

      await adapter.start();
      if (cancelled) return;
      patch({ screenLayouts: adapter.getScreenLayouts(), screenLayout: adapter.getScreenLayout() });

      const sync = new SaveSyncManager(game.id, adapter, adapter.core, onSyncStatus);
      syncRef.current = sync;
      const source = await sync.applyBatterySave(batterySave);
      if (source !== "none") flash(`Save restored (${source === "server" ? "cloud" : "local backup"})`);

      if (resume) {
        try {
          const states = await savesApi.list(game.id, "state");
          const auto = states.find((s) => s.slot === AUTO_STATE_SLOT);
          if (auto) {
            await adapter.loadState(await savesApi.download(auto.id));
            flash("Resumed where you left off");
          }
        } catch (error) {
          console.warn("resume failed", error);
          flash("Could not load the resume point");
        }
      }
      sync.startPeriodicSync();
      patch({ phase: "running" });
      focusEmulator();
    };

    run().catch((error) => {
      if (cancelled) return;
      console.error(error);
      patch({ phase: "error", error: toPlayerError(error) });
    });

    return () => {
      cancelled = true;
      syncRef.current?.dispose();
      void adapterRef.current?.destroy();
      void trackerRef.current?.end();
      adapterRef.current = null;
      syncRef.current = null;
      trackerRef.current = null;
    };
    // `game` identity changes on refetch; boot only once per game id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game?.id, resume]);

  // Flush progress when the tab hides or unloads.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") void syncRef.current?.syncBatterySave();
    };
    const onPageHide = () => {
      void syncRef.current?.syncBatterySave();
      trackerRef.current?.endOnUnload();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, []);

  const withAdapter = useCallback(
    async (action: (adapter: EmulatorAdapter) => Promise<void>) => {
      const adapter = adapterRef.current;
      if (!adapter || !adapter.isRunning()) return;
      try {
        await action(adapter);
      } catch (error) {
        console.error(error);
        flash(toPlayerError(error).title);
      }
    },
    [flash],
  );

  const togglePause = useCallback(
    () =>
      withAdapter(async (adapter) => {
        if (adapter.isPaused()) {
          await adapter.resume();
          patch({ phase: "running" });
        } else {
          await adapter.pause();
          patch({ phase: "paused" });
        }
      }),
    [withAdapter, patch],
  );

  const reset = useCallback(
    () =>
      withAdapter(async (adapter) => {
        await adapter.reset();
        patch({ phase: "running" });
        flash("Game reset");
        focusEmulator();
      }),
    [withAdapter, patch, flash, focusEmulator],
  );

  const saveState = useCallback(
    (slot: number) =>
      withAdapter(async (adapter) => {
        const [bytes, screenshot] = await Promise.all([
          adapter.saveState(),
          adapter.getScreenshot().catch(() => undefined),
        ]);
        await syncRef.current?.uploadState(slot, bytes, screenshot);
        flash(`State saved to slot ${slot}`);
        focusEmulator();
      }),
    [withAdapter, flash, focusEmulator],
  );

  const loadState = useCallback(
    (slot: number) =>
      withAdapter(async (adapter) => {
        const states = await savesApi.list(game?.id ?? "", "state");
        const target = states.find((s) => s.slot === slot);
        if (!target) {
          flash(`Slot ${slot} is empty`);
          return;
        }
        if (target.core_id && target.core_id !== adapter.core.coreId) {
          flash(`Slot ${slot} was made with ${target.core_id}; cannot load in ${adapter.core.coreId}`);
          return;
        }
        await adapter.loadState(await savesApi.download(target.id));
        flash(`State loaded from slot ${slot}`);
        focusEmulator();
      }),
    [withAdapter, flash, focusEmulator, game?.id],
  );

  const screenshot = useCallback(
    () =>
      withAdapter(async (adapter) => {
        const blob = await adapter.getScreenshot();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${(game?.title ?? "screenshot").replace(/[^\w\- ]+/g, "")}.png`;
        anchor.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 5000);
        flash("Screenshot saved");
        focusEmulator();
      }),
    [withAdapter, flash, focusEmulator, game?.title],
  );

  const setVolume = useCallback(
    (volume: number) => {
      adapterRef.current?.setVolume(volume);
      patch({ volume });
      try {
        window.localStorage.setItem(VOLUME_KEY, JSON.stringify(volume));
      } catch {
        /* private mode */
      }
    },
    [patch],
  );

  const toggleMuted = useCallback(() => {
    setState((prev) => {
      const muted = !prev.muted;
      adapterRef.current?.setMuted(muted);
      try {
        window.localStorage.setItem(MUTED_KEY, JSON.stringify(muted));
      } catch {
        /* private mode */
      }
      return { ...prev, muted };
    });
  }, []);

  const setScreenLayout = useCallback(
    (id: string) =>
      withAdapter(async (adapter) => {
        await adapter.setScreenLayout(id);
        patch({ screenLayout: id });
        if (game) {
          try {
            window.localStorage.setItem(layoutKey(game.system), JSON.stringify(id));
          } catch {
            /* private mode */
          }
        }
        focusEmulator();
      }),
    [withAdapter, patch, focusEmulator, game],
  );

  const toggleFullscreen = useCallback(
    () =>
      withAdapter(async (adapter) => {
        if (document.fullscreenElement) await adapter.exitFullscreen();
        else await adapter.enterFullscreen();
        focusEmulator();
      }),
    [withAdapter, focusEmulator],
  );

  /** Quit: flush saves, capture the resume point, end the session. */
  const quit = useCallback(async (): Promise<void> => {
    if (quittingRef.current) return;
    quittingRef.current = true;
    patch({ phase: "exiting" });
    try {
      if (adapterRef.current?.isRunning()) {
        if (adapterRef.current.isPaused()) await adapterRef.current.resume();
        await syncRef.current?.flushOnExit();
      }
    } catch (error) {
      console.warn("flush on exit failed", error);
    }
    syncRef.current?.dispose();
    await adapterRef.current?.destroy().catch(() => undefined);
    adapterRef.current = null;
    await trackerRef.current?.end();
    trackerRef.current = null;
  }, [patch]);

  return {
    state,
    containerRef,
    rootRef,
    actions: {
      togglePause,
      reset,
      saveState,
      loadState,
      screenshot,
      setVolume,
      toggleMuted,
      setScreenLayout,
      toggleFullscreen,
      quit,
      focusEmulator,
    },
  };
}
