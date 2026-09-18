"use client";

import Link from "next/link";
import type { Route } from "next";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { systemInfo } from "@retroweb/shared";
import { useAuthStatus, useHome, useLogout } from "@/lib/api/hooks";
import { APP_NAME } from "@/lib/config";

interface NavItem {
  href: Route;
  label: string;
  icon: string;
  match: (pathname: string, search: URLSearchParams) => boolean;
}

const primaryNav: NavItem[] = [
  { href: "/", label: "Home", icon: "⌂", match: (p) => p === "/" },
  {
    href: "/library",
    label: "Library",
    icon: "▦",
    match: (p, s) => p === "/library" && !s.get("favorite") && !s.get("system"),
  },
  {
    href: "/library?favorite=true",
    label: "Favorites",
    icon: "★",
    match: (p, s) => p === "/library" && s.get("favorite") === "true",
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const search = useSearchParams();
  const { data: home } = useHome();
  const { data: auth } = useAuthStatus();
  const logout = useLogout();

  const linkClass = (active: boolean) =>
    `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
      active ? "bg-hover text-fg" : "text-muted hover:bg-hover/60 hover:text-fg"
    }`;

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-line bg-elevated">
      <Link href="/" className="flex items-center gap-2 px-5 py-5 text-lg font-bold tracking-tight">
        <span className="inline-block h-6 w-6 rounded-md bg-accent" aria-hidden />
        {APP_NAME}
      </Link>
      <nav className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 pb-4">
        <div className="space-y-1">
          {primaryNav.map((item) => (
            <Link key={item.label} href={item.href} className={linkClass(item.match(pathname, search))}>
              <span className="w-4 text-center" aria-hidden>
                {item.icon}
              </span>
              {item.label}
            </Link>
          ))}
        </div>
        <div>
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
            Platforms
          </p>
          <div className="space-y-1">
            {(home?.platforms ?? []).map((platform) => {
              const info = systemInfo(platform.system);
              const active = pathname === "/library" && search.get("system") === platform.system;
              return (
                <Link
                  key={platform.system}
                  href={`/library?system=${platform.system}`}
                  className={linkClass(active)}
                >
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ background: info?.accent ?? "#666" }}
                    aria-hidden
                  />
                  <span className="flex-1 truncate">{info?.name ?? platform.name}</span>
                  <span className="text-xs text-muted">{platform.count}</span>
                </Link>
              );
            })}
            {home && home.platforms.length === 0 && (
              <p className="px-3 text-xs text-muted">No games yet</p>
            )}
          </div>
        </div>
        <div className="mt-auto space-y-1">
          <Link href="/settings" className={linkClass(pathname === "/settings")}>
            <span className="w-4 text-center" aria-hidden>
              ⚙
            </span>
            Settings
          </Link>
          {auth?.mode === "multi" && auth.user && (
            <div className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="w-4 text-center" aria-hidden>
                👤
              </span>
              <span className="flex-1 truncate" title={auth.user.username}>
                {auth.user.username}
                {auth.user.is_admin && <span className="ml-1 text-[10px] uppercase text-muted">admin</span>}
              </span>
              <button
                type="button"
                className="text-xs text-muted hover:text-fg"
                disabled={logout.isPending}
                onClick={() => logout.mutate(undefined, { onSuccess: () => router.replace("/login") })}
              >
                Log out
              </button>
            </div>
          )}
        </div>
      </nav>
    </aside>
  );
}
