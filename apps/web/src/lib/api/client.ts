import type { ApiErrorBody } from "@retroweb/shared";

/** Same-origin API base; Next.js rewrites forward it to the FastAPI server. */
export const API_BASE = "/api";

export type ApiErrorCode =
  | "not_found"
  | "validation_error"
  | "rom_missing"
  | "unsupported_rom"
  | "invalid_filename"
  | "file_too_large"
  | "duplicate_rom"
  | "save_not_found"
  | "session_not_found"
  | "session_already_ended"
  | "storage_error"
  | "invalid_storage_key"
  | "bios_missing"
  | "cover_not_found"
  | "game_not_identified"
  | "feature_disabled"
  | "metadata_unavailable"
  | "job_running"
  | "unauthorized"
  | "invalid_credentials"
  | "forbidden"
  | "username_taken"
  | "setup_complete"
  | "registration_closed"
  | "network_error"
  | "unknown";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly details?: unknown;

  constructor(code: ApiErrorCode, message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> | undefined;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = undefined;
  }
  const code = (body?.error?.code as ApiErrorCode | undefined) ?? "unknown";
  const message = body?.error?.message ?? `Request failed with HTTP ${response.status}`;
  return new ApiError(code, message, response.status, body?.error?.details);
}

export interface RequestOptions {
  method?: string;
  query?: Record<string, string | number | boolean | undefined>;
  json?: unknown;
  body?: BodyInit;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === "") continue;
    params.set(key, String(value));
  }
  const suffix = params.toString();
  return suffix ? `${url}?${suffix}` : url;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await rawRequest(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function rawRequest(path: string, options: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = { ...options.headers };
  let body = options.body;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body,
      signal: options.signal,
      credentials: "same-origin",
    });
  } catch (error) {
    throw new ApiError("network_error", "The server could not be reached.", 0, error);
  }
  if (!response.ok) {
    const error = await toApiError(response);
    if (error.code === "unauthorized" && typeof window !== "undefined") {
      // The login expired (or never existed): go to the sign-in page. A full
      // navigation on purpose: it also drops every cached query of the old user.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      if (!window.location.pathname.startsWith("/login")) window.location.assign("/login");
    }
    throw error;
  }
  return response;
}

export function describeError(error: unknown): { title: string; detail: string; code: string } {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "rom_missing":
        return { title: "ROM missing", detail: "The game file is no longer on the server. Re-scan the library or restore the file.", code: error.code };
      case "unsupported_rom":
        return { title: "Unsupported ROM", detail: error.message, code: error.code };
      case "file_too_large":
        return { title: "File too large", detail: error.message, code: error.code };
      case "duplicate_rom":
        return { title: "Already in library", detail: error.message, code: error.code };
      case "bios_missing":
        return { title: "BIOS required", detail: "Upload the BIOS file for this system in Settings.", code: error.code };
      case "cover_not_found":
        return { title: "No cover found", detail: "The libretro-thumbnails collection has no box art matching this file name. Rename the file in No-Intro style or upload a cover.", code: error.code };
      case "game_not_identified":
        return { title: "Game not recognised", detail: "Neither the file's digest, its serial nor its name is in the No-Intro / Redump lists. Homebrew and heavily modified files are expected to end up here.", code: error.code };
      case "feature_disabled":
        return { title: "Feature disabled", detail: error.message, code: error.code };
      case "metadata_unavailable":
        return { title: "Online source unreachable", detail: "The cover or game database server could not be reached. Try again later.", code: error.code };
      case "job_running":
        return { title: "Already running", detail: error.message, code: error.code };
      case "unauthorized":
        return { title: "Sign in required", detail: "Your session has ended. Sign in again to continue.", code: error.code };
      case "invalid_credentials":
        return { title: "Sign-in failed", detail: error.message, code: error.code };
      case "forbidden":
        return { title: "Administrators only", detail: "Ask an administrator to do this for you.", code: error.code };
      case "username_taken":
        return { title: "Username taken", detail: "Pick another username.", code: error.code };
      case "setup_complete":
        return { title: "Already set up", detail: "The first account exists. Sign in instead.", code: error.code };
      case "registration_closed":
        return { title: "Registration closed", detail: "Ask an administrator for an account.", code: error.code };
      case "network_error":
        return { title: "Network disconnected", detail: "Check that the server is running and reachable.", code: error.code };
      case "not_found":
        return { title: "Not found", detail: error.message, code: error.code };
      default:
        return { title: "Request failed", detail: error.message, code: error.code };
    }
  }
  if (error instanceof Error) return { title: "Unexpected error", detail: error.message, code: "unknown" };
  return { title: "Unexpected error", detail: String(error), code: "unknown" };
}
