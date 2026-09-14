"use client";

import { useSyncExternalStore } from "react";
import { detectBrowserCapabilities, type BrowserCapabilities } from "@retroweb/emulator-core";

let snapshot: BrowserCapabilities | null = null;

function getSnapshot(): BrowserCapabilities {
  if (!snapshot) snapshot = detectBrowserCapabilities();
  return snapshot;
}

function getServerSnapshot(): null {
  return null;
}

function subscribe(): () => void {
  return () => undefined;
}

/** Browser feature probe; `null` during server rendering. */
export function useBrowserCapabilities(): BrowserCapabilities | null {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
