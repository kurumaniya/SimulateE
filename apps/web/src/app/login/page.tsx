"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuthStatus, useLogin, useRegister, useSetup } from "@/lib/api/hooks";
import { APP_NAME } from "@/lib/config";
import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

type Mode = "login" | "setup" | "register";

export default function LoginPage() {
  const router = useRouter();
  const { data: status, isLoading } = useAuthStatus();
  const login = useLogin();
  const setup = useSetup();
  const register = useRegister();
  const [chosenMode, setMode] = useState<Mode | null>(null);
  // Before the first account exists the only sensible form is the setup one.
  const mode: Mode = chosenMode ?? (status?.setup_required ? "setup" : "login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  // Nothing to sign in to: single-user mode, or already signed in.
  useEffect(() => {
    if (status && (status.mode === "single" || status.user)) router.replace("/");
  }, [status, router]);

  const pending = login.isPending || setup.isPending || register.isPending;
  const error = localError ?? login.error ?? setup.error ?? register.error;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLocalError(null);
    if (mode !== "login" && password !== confirm) {
      setLocalError("The passwords do not match.");
      return;
    }
    const credentials = { username: username.trim(), password };
    try {
      if (mode === "setup") await setup.mutateAsync(credentials);
      else if (mode === "register") await register.mutateAsync(credentials);
      else await login.mutateAsync(credentials);
      router.replace("/");
    } catch {
      /* shown through the mutation error */
    }
  };

  if (isLoading || !status || status.mode === "single" || status.user) {
    return <div className="flex h-dvh items-center justify-center text-sm text-muted">Loading…</div>;
  }

  const title =
    mode === "setup" ? "Create the administrator account" : mode === "register" ? "Create your account" : "Sign in";

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg p-6">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-2xl border border-line bg-card p-6">
        <div>
          <p className="flex items-center gap-2 text-lg font-bold tracking-tight">
            <span className="inline-block h-6 w-6 rounded-md bg-accent" aria-hidden />
            {APP_NAME}
          </p>
          <h1 className="mt-3 text-xl font-semibold">{title}</h1>
          {mode === "setup" && (
            <p className="mt-1 text-sm text-muted">
              This is the first account. It manages the library and other accounts, and inherits
              the saves made so far.
            </p>
          )}
        </div>

        <label className="block text-sm">
          <span className="text-muted">Username</span>
          <input
            autoFocus
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 focus:border-accent focus:outline-none"
          />
        </label>
        <label className="block text-sm">
          <span className="text-muted">Password</span>
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={mode === "login" ? 1 : 8}
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 focus:border-accent focus:outline-none"
          />
        </label>
        {mode !== "login" && (
          <label className="block text-sm">
            <span className="text-muted">Confirm password</span>
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 focus:border-accent focus:outline-none"
            />
          </label>
        )}

        {error ? <ErrorBanner error={error} /> : null}

        <Button type="submit" variant="primary" className="w-full" disabled={pending}>
          {pending ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </Button>

        {mode === "login" && status.registration_open && (
          <p className="text-center text-sm text-muted">
            No account yet?{" "}
            <button type="button" className="underline" onClick={() => setMode("register")}>
              Create one
            </button>
          </p>
        )}
        {mode === "register" && (
          <p className="text-center text-sm text-muted">
            <button type="button" className="underline" onClick={() => setMode("login")}>
              Back to sign in
            </button>
          </p>
        )}
      </form>
    </div>
  );
}
