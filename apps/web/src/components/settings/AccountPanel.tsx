"use client";

import { useState, type FormEvent } from "react";
import { useChangePassword } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

/** Change the signed-in user's password (multi-user mode). */
export function AccountPanel({ username }: { username: string }) {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setMessage(null);
    if (next !== confirm) {
      setMessage("The new passwords do not match.");
      return;
    }
    change.mutate(
      { current, next },
      {
        onSuccess: () => {
          setCurrent("");
          setNext("");
          setConfirm("");
          setMessage("Password changed.");
        },
      },
    );
  };

  const field = "mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm focus:border-accent focus:outline-none";

  return (
    <section className="space-y-3 rounded-xl border border-line bg-card p-5">
      <h2 className="font-semibold">Account</h2>
      <p className="text-sm text-muted">
        Signed in as <span className="font-medium text-fg">{username}</span>. Saves, play time and
        favorites are yours alone.
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <label className="block text-sm">
          <span className="text-muted">Current password</span>
          <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} className={field} />
        </label>
        <label className="block text-sm">
          <span className="text-muted">New password</span>
          <input type="password" autoComplete="new-password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} className={field} />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Confirm</span>
          <input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className={field} />
        </label>
        <div className="flex items-center gap-3 sm:col-span-3">
          <Button type="submit" disabled={change.isPending}>
            {change.isPending ? "Saving…" : "Change password"}
          </Button>
          {message && <span className="text-sm text-muted">{message}</span>}
        </div>
      </form>
      {change.error ? <ErrorBanner error={change.error} /> : null}
    </section>
  );
}
