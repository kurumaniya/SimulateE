"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { GameListQuery, GameSystem, GameUpdate } from "@retroweb/shared";
import { biosApi, gamesApi, libraryApi, savesApi, sessionsApi } from "./games";

export const queryKeys = {
  home: ["home"] as const,
  games: (query: GameListQuery) => ["games", query] as const,
  game: (id: string) => ["game", id] as const,
  saves: (gameId: string) => ["saves", gameId] as const,
  systems: ["systems"] as const,
  bios: ["bios"] as const,
  biosFor: (system: GameSystem) => ["bios", system] as const,
  recent: ["recent-sessions"] as const,
};

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
function useInvalidateLibrary() {
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

export function useScanLibrary() {
  const invalidate = useInvalidateLibrary();
  return useMutation({ mutationFn: gamesApi.scan, onSuccess: () => invalidate() });
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
