"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AssistantDock } from "@/components/assistant/assistant-dock";
import { ActivityIcon, HomeIcon, LogoutIcon, MarketsIcon, SwapIcon } from "@/components/icons";
import { Logo } from "@/components/logo";
import { useAuth } from "@/lib/auth";

const NAV_ITEMS: { href: string; label: string; icon: () => ReactNode }[] = [
  { href: "/dashboard", label: "Home", icon: HomeIcon },
  { href: "/markets", label: "Markets", icon: MarketsIcon },
  { href: "/trade", label: "Trade", icon: SwapIcon },
  { href: "/activity", label: "Activity", icon: ActivityIcon },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, checking, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!checking && !user) router.replace("/login");
  }, [user, checking, router]);

  if (!user) return null;

  return (
    <div className="md:grid md:min-h-dvh md:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-line p-4 md:flex">
        <div className="px-2 py-1">
          <Logo />
        </div>
        <nav aria-label="Main" className="mt-8 flex flex-col gap-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 font-medium ${
                  active ? "bg-surface-raised text-ink" : "text-ink-2 hover:bg-surface"
                }`}
              >
                <Icon />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto border-t border-line pt-4">
          <p className="truncate px-3 text-sm font-medium">{user.full_name}</p>
          <p className="truncate px-3 text-sm text-ink-3">@{user.username}</p>
          <button
            type="button"
            onClick={logout}
            className="mt-2 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-ink-2 hover:bg-surface"
          >
            <LogoutIcon />
            Log out
          </button>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="flex items-center justify-between px-4 pt-4 md:hidden">
          <Logo />
          <button type="button" onClick={logout} aria-label="Log out" className="rounded-lg p-2 text-ink-2">
            <LogoutIcon />
          </button>
        </header>
        <main className="mx-auto w-full max-w-5xl px-4 pt-5 pb-44 md:px-8 md:pt-8 md:pb-24">{children}</main>
      </div>

      <AssistantDock />

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-10 grid grid-cols-4 border-t border-line bg-canvas/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
      >
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex flex-col items-center gap-1 py-2.5 text-xs font-medium ${
                active ? "text-accent" : "text-ink-3"
              }`}
            >
              <Icon />
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
