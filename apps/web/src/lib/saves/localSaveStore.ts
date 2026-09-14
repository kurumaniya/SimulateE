import { openDB, type DBSchema, type IDBPDatabase } from "idb";

/**
 * Browser-side backup of save data. If the upload after a session fails, the
 * bytes survive here (flagged dirty) and are pushed on the next launch.
 */
export interface LocalSaveRecord {
  /** `${gameId}:${saveType}:${slot}` */
  key: string;
  gameId: string;
  saveType: "battery" | "state";
  slot: number;
  data: Uint8Array;
  sha256: string;
  modifiedAt: string;
  /** Not yet confirmed by the server. */
  dirty: boolean;
  emulatorId: string;
  coreId: string;
  coreVersion: string;
}

interface RetroWebDb extends DBSchema {
  saves: {
    key: string;
    value: LocalSaveRecord;
    indexes: { byGame: string };
  };
}

const DB_NAME = "retroweb";
const DB_VERSION = 1;

let dbPromise: Promise<IDBPDatabase<RetroWebDb>> | undefined;

function db(): Promise<IDBPDatabase<RetroWebDb>> {
  if (!dbPromise) {
    dbPromise = openDB<RetroWebDb>(DB_NAME, DB_VERSION, {
      upgrade(database) {
        const store = database.createObjectStore("saves", { keyPath: "key" });
        store.createIndex("byGame", "gameId");
      },
    });
  }
  return dbPromise;
}

export function localSaveKey(gameId: string, saveType: "battery" | "state", slot: number): string {
  return `${gameId}:${saveType}:${slot}`;
}

export const localSaveStore = {
  async get(key: string): Promise<LocalSaveRecord | undefined> {
    return (await db()).get("saves", key);
  },
  async put(record: LocalSaveRecord): Promise<void> {
    await (await db()).put("saves", record);
  },
  async markClean(key: string): Promise<void> {
    const database = await db();
    const record = await database.get("saves", key);
    if (record) await database.put("saves", { ...record, dirty: false });
  },
  async delete(key: string): Promise<void> {
    await (await db()).delete("saves", key);
  },
  async listForGame(gameId: string): Promise<LocalSaveRecord[]> {
    return (await db()).getAllFromIndex("saves", "byGame", gameId);
  },
};

export async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data as BufferSource);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}
