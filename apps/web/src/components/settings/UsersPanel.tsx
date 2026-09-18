"use client";

import { useState, type FormEvent } from "react";
import { useCreateUser, useDeleteUser, useUpdateUser, useUsers } from "@/lib/api/hooks";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

/** Administrators create, reset and remove accounts (multi-user mode). */
export function UsersPanel({ selfId }: { selfId: string }) {
  const { data: users, error } = useUsers();
  const create = useCreateUser();
  const update = useUpdateUser();
  const remove = useDeleteUser();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      { username: username.trim(), password, is_admin: isAdmin },
      {
        onSuccess: () => {
          setUsername("");
          setPassword("");
          setIsAdmin(false);
        },
      },
    );
  };

  const resetPassword = (id: string, name: string) => {
    const next = window.prompt(`New password for ${name} (at least 8 characters):`);
    if (next) update.mutate({ id, changes: { password: next } });
  };

  const field = "mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm focus:border-accent focus:outline-none";

  return (
    <section className="space-y-4 rounded-xl border border-line bg-card p-5">
      <div>
        <h2 className="font-semibold">Users</h2>
        <p className="text-sm text-muted">
          Everyone shares the game library; saves, play time and favorites are per account.
          Administrators manage the library and accounts.
        </p>
      </div>
      {error ? <ErrorBanner error={error} /> : null}
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-muted">
          <tr>
            <th className="py-1 pr-4 font-medium">Username</th>
            <th className="py-1 pr-4 font-medium">Role</th>
            <th className="py-1 pr-4 font-medium">Created</th>
            <th className="py-1 font-medium" />
          </tr>
        </thead>
        <tbody>
          {(users ?? []).map((user) => {
            const self = user.id === selfId;
            return (
              <tr key={user.id} className="border-t border-line">
                <td className="py-1.5 pr-4">
                  {user.username}
                  {self && <span className="ml-1 text-xs text-muted">(you)</span>}
                </td>
                <td className="py-1.5 pr-4 text-muted">{user.is_admin ? "Administrator" : "Player"}</td>
                <td className="py-1.5 pr-4 text-muted">{formatDate(user.created_at)}</td>
                <td className="py-1.5 text-right text-xs">
                  {!self && (
                    <span className="flex justify-end gap-3">
                      <button className="text-muted hover:text-fg" onClick={() => resetPassword(user.id, user.username)}>
                        Reset password
                      </button>
                      <button
                        className="text-muted hover:text-fg"
                        onClick={() => update.mutate({ id: user.id, changes: { is_admin: !user.is_admin } })}
                      >
                        {user.is_admin ? "Make player" : "Make admin"}
                      </button>
                      <button
                        className="text-muted hover:text-danger"
                        onClick={() => {
                          if (window.confirm(`Delete ${user.username} and all of their saves? This cannot be undone.`)) {
                            remove.mutate({ id: user.id });
                          }
                        }}
                      >
                        Delete
                      </button>
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {update.error ? <ErrorBanner error={update.error} /> : null}
      {remove.error ? <ErrorBanner error={remove.error} /> : null}

      <form onSubmit={submit} className="grid gap-3 rounded-lg border border-line bg-bg p-4 sm:grid-cols-3">
        <label className="block text-sm">
          <span className="text-muted">New username</span>
          <input required value={username} onChange={(e) => setUsername(e.target.value)} className={field} autoComplete="off" />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Password</span>
          <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className={field} autoComplete="new-password" />
        </label>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
          Administrator
        </label>
        <div className="sm:col-span-3">
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Add account"}
          </Button>
        </div>
        {create.error ? (
          <div className="sm:col-span-3">
            <ErrorBanner error={create.error} />
          </div>
        ) : null}
      </form>
    </section>
  );
}
