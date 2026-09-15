import { AUTO_STATE_SLOT, BATTERY_SLOT, type SaveOut } from "@retroweb/shared";
import type { CoreDescriptor, EmulatorAdapter } from "@retroweb/emulator-core";
import { savesApi } from "../api/games";
import { localSaveKey, localSaveStore, sha256Hex, type LocalSaveRecord } from "./localSaveStore";

export type SyncStatus = "idle" | "syncing" | "synced" | "offline" | "error";

export interface SaveSyncEvents {
  status: (status: SyncStatus, detail?: string) => void;
}

export interface Candidate {
  data: Uint8Array;
  modifiedAt: string;
  source: "server" | "local";
  serverSave?: SaveOut;
  /** Set when the local copy never reached the server. */
  dirty?: boolean;
}

/**
 * Resolve the newest battery save between the server and the local backup.
 * Runs before the emulator loads so adapters can put the save in place
 * before the game boots.
 */
export async function resolveBatterySave(
  gameId: string,
  onStatus?: SaveSyncEvents["status"],
): Promise<Candidate | undefined> {
  const key = localSaveKey(gameId, "battery", BATTERY_SLOT);
  const [local, serverList] = await Promise.all([
    localSaveStore.get(key).catch(() => undefined),
    savesApi
      .list(gameId, "battery")
      .then((rows) => rows.find((row) => row.slot === BATTERY_SLOT))
      .catch(() => undefined),
  ]);

  const candidates: Candidate[] = [];
  if (local) {
    candidates.push({
      data: local.data,
      modifiedAt: local.modifiedAt,
      source: "local",
      dirty: local.dirty,
    });
  }
  if (serverList) {
    try {
      const data = await savesApi.download(serverList.id);
      candidates.push({
        data,
        modifiedAt: serverList.client_modified_at ?? serverList.updated_at,
        source: "server",
        serverSave: serverList,
      });
    } catch (error) {
      onStatus?.("offline", "Could not download the save from the server.");
      console.warn("save download failed", error);
    }
  }
  return pickNewest(candidates);
}

/**
 * Keeps the emulator's battery save in step with the server.
 *
 * local (IndexedDB) ⇄ SaveSyncManager ⇄ server; the emulator only sees bytes.
 * Conflict policy lives in `pickNewest()` so it can be replaced later.
 */
export class SaveSyncManager {
  private lastUploadedHash: string | null = null;
  private timer: number | undefined;
  private inFlight: Promise<void> = Promise.resolve();
  private stopped = false;

  constructor(
    private readonly gameId: string,
    private readonly adapter: EmulatorAdapter,
    private readonly core: CoreDescriptor,
    private readonly onStatus: SaveSyncEvents["status"],
    private readonly intervalMs = 60_000,
  ) {}

  /**
   * Called once the emulator is running with the save chosen by
   * `resolveBatterySave()`: make sure the game has it, and push a dirty
   * local copy if the server never received it.
   */
  async applyBatterySave(chosen: Candidate | undefined): Promise<"server" | "local" | "none"> {
    if (!chosen) return "none";
    const key = localSaveKey(this.gameId, "battery", BATTERY_SLOT);

    if (!this.adapter.initialSaveApplied()) {
      // The core already booted once without this save (EmulatorJS only
      // exposes the save path after content is loaded). Reboot so the game
      // starts with it.
      await this.adapter.loadSaveData(chosen.data);
      await this.adapter.reset();
    }
    this.lastUploadedHash = await sha256Hex(chosen.data);

    if (chosen.source === "local" && chosen.dirty) {
      // The server missed this save (upload failed last time). Push it now.
      await this.upload(chosen.data, chosen.modifiedAt);
    } else if (chosen.source === "server") {
      await localSaveStore
        .put(this.record(key, chosen.data, this.lastUploadedHash, chosen.modifiedAt, false))
        .catch(() => undefined);
    }
    return chosen.source;
  }

  startPeriodicSync(): void {
    this.stopPeriodicSync();
    this.timer = window.setInterval(() => void this.syncBatterySave(), this.intervalMs);
  }

  stopPeriodicSync(): void {
    if (this.timer !== undefined) window.clearInterval(this.timer);
    this.timer = undefined;
  }

  /** Extract the current battery save and upload it if it changed. */
  syncBatterySave(): Promise<void> {
    this.inFlight = this.inFlight.then(() => this.doSync()).catch(() => undefined);
    return this.inFlight;
  }

  /** Final flush on quit: battery save plus the automatic "Resume" state. */
  async flushOnExit(): Promise<void> {
    this.stopPeriodicSync();
    await this.syncBatterySave();
    if (this.stopped) return;
    try {
      const [state, screenshot] = await Promise.all([
        this.adapter.saveState(),
        this.adapter.getScreenshot().catch(() => undefined),
      ]);
      await this.uploadState(AUTO_STATE_SLOT, state, screenshot);
    } catch (error) {
      console.warn("auto state on exit failed", error);
    }
  }

  async uploadState(slot: number, state: Uint8Array, screenshot?: Blob): Promise<SaveOut> {
    const modifiedAt = new Date().toISOString();
    this.onStatus("syncing");
    try {
      const saved = await savesApi.upload(
        this.gameId,
        {
          save_type: "state",
          slot,
          emulator_id: this.core.emulatorId,
          core_id: this.core.coreId,
          core_version: this.core.coreVersion,
          client_modified_at: modifiedAt,
        },
        state,
        screenshot,
      );
      this.onStatus("synced");
      return saved;
    } catch (error) {
      this.onStatus("error", "Save state upload failed.");
      throw error;
    }
  }

  dispose(): void {
    this.stopped = true;
    this.stopPeriodicSync();
  }

  private async doSync(): Promise<void> {
    if (this.stopped || !this.adapter.isRunning()) return;
    let data: Uint8Array | null;
    try {
      data = await this.adapter.getSaveData();
    } catch {
      return;
    }
    if (!data || data.length === 0) return;
    const hash = await sha256Hex(data);
    if (hash === this.lastUploadedHash) return;
    const modifiedAt = new Date().toISOString();
    const key = localSaveKey(this.gameId, "battery", BATTERY_SLOT);
    // Local first: even if the network is gone, the bytes are safe.
    await localSaveStore.put(this.record(key, data, hash, modifiedAt, true)).catch(() => undefined);
    await this.upload(data, modifiedAt, hash);
  }

  private async upload(data: Uint8Array, modifiedAt: string, hash?: string): Promise<void> {
    const key = localSaveKey(this.gameId, "battery", BATTERY_SLOT);
    this.onStatus("syncing");
    try {
      await savesApi.upload(
        this.gameId,
        {
          save_type: "battery",
          slot: BATTERY_SLOT,
          emulator_id: this.core.emulatorId,
          core_id: this.core.coreId,
          core_version: this.core.coreVersion,
          client_modified_at: modifiedAt,
        },
        data,
      );
      this.lastUploadedHash = hash ?? (await sha256Hex(data));
      await localSaveStore.markClean(key).catch(() => undefined);
      this.onStatus("synced");
    } catch (error) {
      this.onStatus("offline", "Save kept locally; upload will retry.");
      console.warn("save upload failed", error);
    }
  }

  private record(
    key: string,
    data: Uint8Array,
    sha256: string,
    modifiedAt: string,
    dirty: boolean,
  ): LocalSaveRecord {
    return {
      key,
      gameId: this.gameId,
      saveType: "battery",
      slot: BATTERY_SLOT,
      data,
      sha256,
      modifiedAt,
      dirty,
      emulatorId: this.core.emulatorId,
      coreId: this.core.coreId,
      coreVersion: this.core.coreVersion,
    };
  }
}

/** Phase 1 conflict policy: the copy modified most recently wins. */
export function pickNewest(candidates: Candidate[]): Candidate | undefined {
  if (candidates.length === 0) return undefined;
  return [...candidates].sort(
    (a, b) => Date.parse(normalizeIso(b.modifiedAt)) - Date.parse(normalizeIso(a.modifiedAt)),
  )[0];
}

function normalizeIso(value: string): string {
  return /Z|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
}
