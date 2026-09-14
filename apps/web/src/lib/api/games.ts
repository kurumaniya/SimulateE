import type {
  GameDetail,
  GameListQuery,
  GameListResponse,
  GameSystem,
  GameUpdate,
  HomeResponse,
  PlaySessionOut,
  RecentSessionOut,
  SaveOut,
  SaveType,
  SaveUploadFields,
  ScanResult,
  SystemOut,
} from "@retroweb/shared";
import { buildUrl, rawRequest, request } from "./client";

export const gamesApi = {
  list: (query: GameListQuery = {}) =>
    request<GameListResponse>("/games", { query: { ...query } }),
  get: (id: string) => request<GameDetail>(`/games/${encodeURIComponent(id)}`),
  update: (id: string, changes: GameUpdate) =>
    request<GameDetail>(`/games/${encodeURIComponent(id)}`, { method: "PATCH", json: changes }),
  setFavorite: (id: string, favorite: boolean) =>
    request<GameDetail>(`/games/${encodeURIComponent(id)}/favorite`, {
      method: "POST",
      json: { favorite },
    }),
  scan: () => request<ScanResult>("/games/scan", { method: "POST" }),
  upload: (file: File, system: GameSystem) => {
    const body = new FormData();
    body.append("file", file, file.name);
    body.append("system", system);
    return request<GameDetail>("/games/upload", { method: "POST", body });
  },
  uploadCover: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file, file.name);
    return request<GameDetail>(`/games/${encodeURIComponent(id)}/cover`, { method: "PUT", body });
  },
  coverUrl: (game: { id: string; has_cover: boolean; updated_at?: string }) =>
    game.has_cover
      ? buildUrl(`/games/${encodeURIComponent(game.id)}/cover`, { v: game.updated_at })
      : null,
  /** ROM URL ends with the file name so browser caches key it per game. */
  romUrl: (game: GameDetail) =>
    game.rom_filename
      ? buildUrl(`/games/${encodeURIComponent(game.id)}/rom/${encodeURIComponent(game.rom_filename)}`)
      : buildUrl(`/games/${encodeURIComponent(game.id)}/rom`),
};

export const libraryApi = {
  home: () => request<HomeResponse>("/library/home"),
  systems: () => request<SystemOut[]>("/systems"),
};

export const savesApi = {
  list: (gameId: string, saveType?: SaveType) =>
    request<SaveOut[]>(`/games/${encodeURIComponent(gameId)}/saves`, {
      query: { save_type: saveType },
    }),
  upload: (gameId: string, fields: SaveUploadFields, data: Uint8Array, screenshot?: Blob) => {
    const body = new FormData();
    body.append("file", new Blob([data as BlobPart]), `${fields.save_type}-${fields.slot}.bin`);
    body.append("save_type", fields.save_type);
    body.append("slot", String(fields.slot));
    body.append("emulator_id", fields.emulator_id);
    if (fields.core_id) body.append("core_id", fields.core_id);
    if (fields.core_version) body.append("core_version", fields.core_version);
    if (fields.client_modified_at) body.append("client_modified_at", fields.client_modified_at);
    if (screenshot) body.append("screenshot", screenshot, "screenshot.png");
    return request<SaveOut>(`/games/${encodeURIComponent(gameId)}/saves`, { method: "POST", body });
  },
  download: async (saveId: string): Promise<Uint8Array> => {
    const response = await rawRequest(`/saves/${encodeURIComponent(saveId)}/download`);
    return new Uint8Array(await response.arrayBuffer());
  },
  remove: (saveId: string) => request<void>(`/saves/${encodeURIComponent(saveId)}`, { method: "DELETE" }),
  screenshotUrl: (save: SaveOut) =>
    save.has_screenshot
      ? buildUrl(`/saves/${encodeURIComponent(save.id)}/screenshot`, { v: save.updated_at })
      : null,
};

export const sessionsApi = {
  start: (gameId: string, emulatorId: string, device: string) =>
    request<PlaySessionOut>("/play-sessions", {
      method: "POST",
      json: { game_id: gameId, emulator_id: emulatorId, device },
    }),
  heartbeat: (sessionId: string) =>
    request<PlaySessionOut>(`/play-sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      json: { action: "heartbeat" },
    }),
  end: (sessionId: string) =>
    request<PlaySessionOut>(`/play-sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      json: { action: "end" },
    }),
  recent: (limit = 20) => request<RecentSessionOut[]>("/play-sessions/recent", { query: { limit } }),
};
