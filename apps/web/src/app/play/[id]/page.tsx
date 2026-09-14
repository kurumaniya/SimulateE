"use client";

import { use } from "react";
import Link from "next/link";
import { useGame } from "@/lib/api/hooks";
import { EmulatorPlayer } from "@/components/player/EmulatorPlayer";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Button } from "@/components/ui/Button";

export default function PlayPage(props: PageProps<"/play/[id]">) {
  const { id } = use(props.params);
  const search = use(props.searchParams);
  const resume = search.resume === "1" || search.resume === "true";
  const { data: game, error, isLoading } = useGame(id);

  if (isLoading) {
    return <div className="fixed inset-0 flex items-center justify-center bg-black text-muted">Loading…</div>;
  }
  if (error || !game) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-bg p-8">
        <div className="w-full max-w-lg space-y-4">
          <ErrorBanner error={error} />
          <Link href="/">
            <Button>Back to library</Button>
          </Link>
        </div>
      </div>
    );
  }
  return <EmulatorPlayer game={game} resume={resume} />;
}
