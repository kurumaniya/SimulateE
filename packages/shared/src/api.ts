/**
 * REST API data transfer types. Field names match the FastAPI schemas in
 * `apps/api/retroweb/schemas` (snake_case on purpose: no mapping layer).
 */
import type { GameSystem } from "./systems";

export type SaveType = "battery" | "state";

export const BATTERY_SLOT = 0;
export const AUTO_STATE_SLOT = -1;

export interface GameSummary {
  id: string;
  title: string;
  system: GameSystem;
  favorite: boolean;
  region: string | null;
  has_cover: boolean;
  rom_missing: boolean;
  play_time_seconds: number;
  last_played_at: string | null;
  has_auto_state: boolean;
  created_at: string;
}

export interface GameFile {
  id: string;
  filename: string;
  extension: string;
  size_bytes: number;
  sha256: string;
  region: string | null;
  label: string | null;
  is_primary: boolean;
  role: "primary" | "companion";
  missing: boolean;
}

export interface GameDetail extends GameSummary {
  title_en: string | null;
  title_ja: string | null;
  title_zh: string | null;
  developer: string | null;
  publisher: string | null;
  release_date: string | null;
  description: string | null;
  rom_filename: string | null;
  rom_hash: string | null;
  rom_size: number | null;
  files: GameFile[];
  updated_at: string;
}

export interface GameListResponse {
  items: GameSummary[];
  total: number;
  limit: number;
  offset: number;
}

export type GameSort = "title" | "recently_played" | "recently_added" | "play_time";

export interface GameListQuery {
  q?: string;
  system?: GameSystem;
  favorite?: boolean;
  sort?: GameSort;
  limit?: number;
  offset?: number;
}

export interface GameUpdate {
  title?: string;
  title_en?: string | null;
  title_ja?: string | null;
  title_zh?: string | null;
  developer?: string | null;
  publisher?: string | null;
  release_date?: string | null;
  region?: string | null;
  description?: string | null;
}

export interface ScanResult {
  added: number;
  updated: number;
  missing: number;
  skipped: number;
  errors: string[];
}

export interface PlatformSummary {
  system: GameSystem;
  name: string;
  short_name: string;
  count: number;
  supported: boolean;
}

export interface HomeResponse {
  continue_playing: GameSummary[];
  recently_played: GameSummary[];
  recently_added: GameSummary[];
  favorites: GameSummary[];
  platforms: PlatformSummary[];
}

export interface SystemOut {
  id: GameSystem;
  name: string;
  short_name: string;
  manufacturer: string;
  extensions: string[];
  supported: boolean;
}

export interface SaveOut {
  id: string;
  game_id: string;
  save_type: SaveType;
  slot: number;
  size_bytes: number;
  has_screenshot: boolean;
  emulator_id: string;
  core_id: string | null;
  core_version: string | null;
  client_modified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SaveUploadFields {
  save_type: SaveType;
  slot: number;
  emulator_id: string;
  core_id?: string;
  core_version?: string;
  client_modified_at?: string;
}

export interface PlaySessionOut {
  id: string;
  game_id: string;
  started_at: string;
  last_heartbeat_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  device: string | null;
  emulator_id: string | null;
  heartbeat_interval_seconds: number;
}

export interface RecentSessionOut {
  session: PlaySessionOut;
  game: GameSummary;
}

export interface UserOut {
  id: string;
  username: string;
  is_admin: boolean;
  created_at: string;
}

/** Answer of GET /auth/status: what the client needs before rendering. */
export interface AuthStatus {
  /** "single": one implicit account, no login. "multi": accounts and sessions. */
  mode: "single" | "multi";
  /** Multi-user mode before the first (admin) account exists. */
  setup_required: boolean;
  registration_open: boolean;
  user: UserOut | null;
}

export interface Credentials {
  username: string;
  password: string;
}

/** A server-side background job (e.g. fetching covers for the whole library). */
export interface JobOut {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  total: number;
  done: number;
  /** Outcome counts, e.g. { fetched, not_found, skipped, failed }. */
  counters: Record<string, number>;
  errors: string[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
}

export interface BiosFileOut {
  filename: string;
  description: string;
  known_md5: string | null;
  installed: boolean;
  size_bytes: number | null;
  sha256: string | null;
  md5: string | null;
  verified: boolean | null;
}

export interface SystemBiosOut {
  system: GameSystem;
  note: string;
  optional: boolean;
  ready: boolean;
  preferred_file: string | null;
  files: BiosFileOut[];
}
