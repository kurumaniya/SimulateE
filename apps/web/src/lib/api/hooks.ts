"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Credentials, GameListQuery, GameSystem, GameUpdate } from "@retroweb/shared";
import { authApi, biosApi, gamesApi, libraryApi, savesApi, sessionsApi, usersApi } from "./games";

export const queryKeys = {
  auth: ["auth"] as const,
  users: ["users"] as const,
  home: ["home"] as const,
  games: (query: GameListQuery) => ["games", query] as const,
  game: (id: string) => ["game", id] as const,
  saves: (gameId: string) => ["saves", gameId] as const,
  systems: ["systems"] as const,
  bios: ["bios"] as const,
  biosFor: (system: GameSystem) => ["bios", system] as const,
  recent: ["recent-sessions"] as const,
  job: (id: string) => ["job", id] as const,
};

// -- accounts ---------------------------------------------------------------

export function useAuthStatus() {
  return useQuery({ queryKey: queryKeys.auth, queryFn: authApi.status, staleTime: 60_000 });
}

/** True when the signed-in user may manage the library (always in single-user mode). */
export function useIsAdmin(): boolean {
  const { data } = useAuthStatus();
  return !data || data.mode === "single" || !!data.user?.is_admin;
}

function useAfterSignIn() {
  const client = useQueryClient();
  return async () => {
    // Everything cached belongs to whoever was signed in before.
    client.clear();
    await client.invalidateQueries({ queryKey: queryKeys.auth });
  };
}

export function useLogin() {
  const after = useAfterSignIn();
  return useMutation({ mutationFn: (c: Credentials) => authApi.login(c), onSuccess: after });
}

export function useSetup() {
  const after = useAfterSignIn();
  return useMutation({ mutationFn: (c: Credentials) => authApi.setup(c), onSuccess: after });
}

export function useRegister() {
  const after = useAfterSignIn();
  return useMutation({ mutationFn: (c: Credentials) => authApi.register(c), onSuccess: after });
}

export function useLogout() {
  const after = useAfterSignIn();
  return useMutation({ mutationFn: authApi.logout, onSuccess: after });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: ({ current, next }: { current: string; next: string }) =>
      authApi.changePassword(current, next),
  });
}

export function useUsers(enabled = true) {
  return useQuery({ queryKey: queryKeys.users, queryFn: usersApi.list, enabled });
}

export function useCreateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: usersApi.create,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.users }),
  });
}

export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: { password?: string; is_admin?: boolean } }) =>
      usersApi.update(id, changes),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.users }),
  });
}

export function useDeleteUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => usersApi.remove(id),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.users }),
  });
}

// -- library ----------------------------------------------------------------

export function useHome() {
  return useQuery({ queryKey: queryKeys.home, queryFn: libraryApi.home });
}

export function useGames(query: GameListQuery) {
  return useQuery({ queryKey: queryKeys.games(query), queryFn: () => gamesApi.list(query) });
}

export function useGame(id: string) {
  return useQuery({ queryKey: queryKeys.game(id), queryFn: () => gamesApi.get(id), enabled: !!id });
}

export function useSaves(gameId: string) {
  return useQuery({
    queryKey: queryKeys.saves(gameId),
    queryFn: () => savesApi.list(gameId),
    enabled: !!gameId,
  });
}

export function useSystems() {
  return useQuery({ queryKey: queryKeys.systems, queryFn: libraryApi.systems, staleTime: Infinity });
}

export function useRecentSessions() {
  return useQuery({ queryKey: queryKeys.recent, queryFn: () => sessionsApi.recent() });
}

/** Invalidate everything that shows library state after a mutation. */
export function useInvalidateLibrary() {
  const client = useQueryClient();
  return async (gameId?: string) => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["games"] }),
      client.invalidateQueries({ queryKey: queryKeys.home }),
      client.invalidateQueries({ queryKey: queryKeys.recent }),
      gameId ? client.invalidateQueries({ queryKey: queryKeys.game(gameId) }) : Promise.resolve(),
    ]);
  };
}

export function useToggleFavorite() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ id, favorite }: { id: string; favorite: boolean }) =>
      gamesApi.setFavorite(id, favorite),
    onSuccess: (game) => invalidate(game.id),
  });
}

export function useUpdateGame() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: GameUpdate }) => gamesApi.update(id, changes),
    onSuccess: (game) => invalidate(game.id),
  });
}

/** Starts the background scan; follow it with `useJob` and invalidate when it finishes. */
export function useStartScan() {
  return useMutation({ mutationFn: libraryApi.scan });
}

export function useUploadRom() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ file, system }: { file: File; system: GameSystem }) =>
      gamesApi.upload(file, system),
    onSuccess: () => invalidate(),
  });
}

export function useUploadCover() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => gamesApi.uploadCover(id, file),
    onSuccess: (game) => invalidate(game.id),
  });
}

export function useFetchCover() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => gamesApi.fetchCover(id),
    onSuccess: (game) => invalidate(game.id),
  });
}

export function useFetchCovers() {
  return useMutation({ mutationFn: libraryApi.fetchCovers });
}

export function useIdentifyGame() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ id }: { id: string }) => gamesApi.identify(id),
    onSuccess: (game) => invalidate(game.id),
  });
}

export function useIdentifyLibrary() {
  return useMutation({ mutationFn: libraryApi.identify });
}

/** Polls a background job every second until it finishes. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.job(jobId ?? ""),
    queryFn: () => libraryApi.job(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1000 : false;
    },
  });
}

export function useDeleteSave() {
  const client = useQueryClient();
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ saveId }: { saveId: string; gameId: string }) => savesApi.remove(saveId),
    onSuccess: async (_result, { gameId }) => {
      await client.invalidateQueries({ queryKey: queryKeys.saves(gameId) });
      await invalidate(gameId);
    },
  });
}

export function useBiosInventory() {
  return useQuery({ queryKey: queryKeys.bios, queryFn: biosApi.list });
}

export function useSystemBios(system: GameSystem | undefined) {
  return useQuery({
    queryKey: queryKeys.biosFor(system ?? ("" as GameSystem)),
    queryFn: () => biosApi.forSystem(system as GameSystem),
    enabled: !!system,
  });
}

export function useUploadBios() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ system, file }: { system: GameSystem; file: File }) => biosApi.upload(system, file),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.bios }),
  });
}

export function useDeleteBios() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ system, filename }: { system: GameSystem; filename: string }) =>
      biosApi.remove(system, filename),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.bios }),
  });
}
