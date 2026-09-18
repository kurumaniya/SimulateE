"use client";

import { useState } from "react";
import type { GameDetail } from "@retroweb/shared";
import type { PlayerState } from "./usePlayerSession";

const STATE_SLOTS = [1, 2, 3];

interface Props {
  game: GameDetail;
  state: PlayerState;
  running: boolean;
  onTogglePause: () => void;
  onReset: () => void;
  onSaveState: (slot: number) => void;
  onLoadState: (slot: number) => void;
  onScreenshot: () => void;
  onToggleMuted: () => void;
  onVolume: (volume: number) => void;
  onScreenLayout: (id: string) => void;
  onControls: () => void;
  onFullscreen: () => void;
  onQuit: () => void;
}

export function PlayerToolbar(props: Props) {
  const { game, state, running } = props;
  const [menu, setMenu] = useState<"save" | "load" | null>(null);
  const paused = state.phase === "paused";

  const iconButton = (label: string, onClick: () => void, content: string, disabled = false) => (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={() => {
        setMenu(null);
        onClick();
      }}
      className="shrink-0 rounded-md px-2.5 py-1.5 text-sm text-fg/90 hover:bg-white/10 disabled:opacity-40"
    >
      {content}
    </button>
  );

  return (
    // Scrolls sideways on phones instead of wrapping over the game.
    <div className="hide-scrollbar flex items-center gap-2 overflow-x-auto bg-gradient-to-b from-black/90 to-black/0 px-3 py-2">
      <button
        type="button"
        onClick={props.onQuit}
        disabled={state.phase === "exiting"}
        className="shrink-0 rounded-md px-3 py-1.5 text-sm font-medium hover:bg-white/10 disabled:opacity-40"
        aria-label="Quit game"
      >
        ✕ Quit
      </button>
      <div className="min-w-16 flex-1 truncate px-2 text-sm font-medium">{game.title}</div>
      <SyncIndicator status={state.syncStatus} detail={state.syncDetail} />

      {iconButton(paused ? "Resume" : "Pause", props.onTogglePause, paused ? "▶ Resume" : "⏸ Pause", !running)}
      {iconButton("Reset", props.onReset, "↺", !running)}

      <div className="relative">
        {iconButton("Save state", () => setMenu(menu === "save" ? null : "save"), "Save ▾", !running)}
        {menu === "save" && (
          <SlotMenu label="Save to" onPick={(slot) => { setMenu(null); props.onSaveState(slot); }} />
        )}
      </div>
      <div className="relative">
        {iconButton("Load state", () => setMenu(menu === "load" ? null : "load"), "Load ▾", !running)}
        {menu === "load" && (
          <SlotMenu label="Load from" onPick={(slot) => { setMenu(null); props.onLoadState(slot); }} />
        )}
      </div>

      {state.screenLayouts.length > 0 && (
        <select
          aria-label="Screen layout"
          title="Screen layout"
          value={state.screenLayout ?? ""}
          disabled={!running}
          onChange={(event) => {
            setMenu(null);
            props.onScreenLayout(event.target.value);
          }}
          className="rounded-md border border-white/10 bg-black/40 px-2 py-1.5 text-sm text-fg/90 disabled:opacity-40"
        >
          {state.screenLayouts.map((layout) => (
            <option key={layout.id} value={layout.id}>
              {layout.label}
            </option>
          ))}
        </select>
      )}
      {iconButton("Controls (remap keyboard and gamepad)", props.onControls, "🎮", !running)}
      {iconButton("Screenshot", props.onScreenshot, "📷", !running)}
      {iconButton(state.muted ? "Unmute" : "Mute", props.onToggleMuted, state.muted ? "🔇" : "🔊")}
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={state.volume}
        onChange={(e) => props.onVolume(Number(e.target.value))}
        aria-label="Volume"
        className="w-20 accent-[var(--accent)]"
      />
      {iconButton("Fullscreen", props.onFullscreen, "⛶")}
    </div>
  );
}

function SlotMenu({ label, onPick }: { label: string; onPick: (slot: number) => void }) {
  return (
    <div className="absolute right-0 top-full z-30 mt-1 w-36 rounded-lg border border-line bg-elevated p-1 shadow-xl">
      <p className="px-2 py-1 text-[11px] uppercase tracking-wide text-muted">{label}</p>
      {STATE_SLOTS.map((slot) => (
        <button
          key={slot}
          type="button"
          onClick={() => onPick(slot)}
          className="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-hover"
        >
          Slot {slot}
        </button>
      ))}
    </div>
  );
}

function SyncIndicator({ status, detail }: { status: PlayerState["syncStatus"]; detail?: string }) {
  const map: Record<PlayerState["syncStatus"], { text: string; color: string }> = {
    idle: { text: "", color: "text-muted" },
    syncing: { text: "Saving…", color: "text-muted" },
    synced: { text: "Saved", color: "text-success" },
    offline: { text: "Offline · saved locally", color: "text-amber-300" },
    error: { text: "Save failed", color: "text-danger" },
  };
  const entry = map[status];
  if (!entry.text) return null;
  return (
    <span className={`px-2 text-xs ${entry.color}`} title={detail}>
      {entry.text}
    </span>
  );
}
