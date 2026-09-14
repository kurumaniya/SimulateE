import { sessionsApi } from "../api/games";

/**
 * Drives the server-side play session: start, periodic heartbeat, end.
 * The server computes durations; this class only reports liveness.
 */
export class PlaySessionTracker {
  private sessionId: string | null = null;
  private timer: number | undefined;

  constructor(private readonly gameId: string, private readonly emulatorId: string) {}

  async start(): Promise<void> {
    const session = await sessionsApi.start(this.gameId, this.emulatorId, describeDevice());
    this.sessionId = session.id;
    const interval = Math.max(10, session.heartbeat_interval_seconds) * 1000;
    this.timer = window.setInterval(() => {
      if (this.sessionId) void sessionsApi.heartbeat(this.sessionId).catch(() => undefined);
    }, interval);
  }

  async end(): Promise<void> {
    if (this.timer !== undefined) window.clearInterval(this.timer);
    this.timer = undefined;
    const id = this.sessionId;
    this.sessionId = null;
    if (!id) return;
    try {
      await sessionsApi.end(id);
    } catch (error) {
      console.warn("failed to end play session", error);
    }
  }

  /** Best-effort end when the tab closes (fetch with keepalive). */
  endOnUnload(): void {
    const id = this.sessionId;
    if (!id) return;
    this.sessionId = null;
    void fetch(`/api/play-sessions/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "end" }),
      keepalive: true,
      credentials: "same-origin",
    }).catch(() => undefined);
  }
}

function describeDevice(): string {
  if (typeof navigator === "undefined") return "unknown";
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Safari\//.test(ua)
        ? "Safari"
        : /Firefox\//.test(ua)
          ? "Firefox"
          : "Browser";
  const platform = /iPad|Macintosh/.test(ua) && navigator.maxTouchPoints > 1
    ? "iPad"
    : /Android/.test(ua)
      ? "Android"
      : /iPhone/.test(ua)
        ? "iPhone"
        : /Windows/.test(ua)
          ? "Windows"
          : /Mac/.test(ua)
            ? "macOS"
            : /Linux/.test(ua)
              ? "Linux"
              : "Unknown";
  return `${browser} on ${platform}`.slice(0, 255);
}
