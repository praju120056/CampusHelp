"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { api } from "@/lib/api";
import { clearSession, getToken, getUser, HOME, ROLE_LABEL, type Role, type User } from "@/lib/auth";
import { useInterval } from "@/lib/live";
import { Icon } from "./ui";

const NAV: Record<Role, { href: string; label: string }[]> = {
  faculty: [
    { href: "/log", label: "Work log" },
    { href: "/adjust", label: "Class cover" },
    { href: "/timetable", label: "Timetable" },
  ],
  hod: [
    { href: "/hod", label: "Dashboard" },
    { href: "/hod/adjustments", label: "Adjustments" },
    { href: "/map", label: "Live map" },
    { href: "/timetable", label: "Timetable" },
    { href: "/report", label: "Report" },
    { href: "/settings", label: "Settings" },
    { href: "/import", label: "Import" },
    { href: "/outbox", label: "Outbox" },
  ],
  incharge: [
    { href: "/tickets", label: "My tickets" },
    { href: "/map", label: "Live map" },
  ],
  estate: [
    { href: "/map", label: "Live map" },
    { href: "/tickets", label: "All tickets" },
    { href: "/qr", label: "QR codes" },
    { href: "/outbox", label: "Outbox" },
  ],
};

// Which roles may open which pages (the API enforces the same rules).
const ACCESS: [string, Role[]][] = [
  ["/hod", ["hod"]],
  ["/report", ["hod"]],
  ["/settings", ["hod"]],
  ["/import", ["hod"]],
  ["/log", ["faculty"]],
  ["/adjust", ["faculty"]],
  ["/map", ["hod", "incharge", "estate"]],
  ["/tickets", ["hod", "incharge", "estate"]],
  ["/qr", ["hod", "estate"]],
  ["/outbox", ["hod", "estate"]],
  ["/timetable", ["faculty", "hod"]],
  ["/inbox", ["faculty", "hod", "incharge", "estate"]],
];

const UserContext = createContext<User | null>(null);

export function useCurrentUser(): User {
  const user = useContext(UserContext);
  if (!user) throw new Error("useCurrentUser outside the staff shell");
  return user;
}

function subscribeStorage(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

/** The logged-in user from localStorage; undefined while rendering on the server. */
function useStoredUser(): User | null | undefined {
  const raw = useSyncExternalStore(
    subscribeStorage,
    () => (getToken() ? JSON.stringify(getUser()) : "null"),
    () => undefined,
  );
  return useMemo(() => (raw === undefined ? undefined : (JSON.parse(raw) as User | null)), [raw]);
}

function allowed(user: User, pathname: string): boolean {
  const rule = ACCESS.find(([prefix]) => pathname === prefix || pathname.startsWith(prefix + "/"));
  return !rule || rule[1].includes(user.role);
}

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const stored = useStoredUser();
  const [unread, setUnread] = useState(0);
  const user = stored && allowed(stored, pathname) ? stored : null;

  useEffect(() => {
    if (stored === null) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else if (stored && !allowed(stored, pathname)) router.replace(HOME[stored.role]);
  }, [stored, pathname, router]);

  const refreshUnread = () => {
    if (!getToken()) return;
    api<{ unread: number }>("/notifications")
      .then((r) => setUnread(r.unread))
      .catch(() => {});
  };
  useEffect(() => {
    if (!getToken()) return;
    api<{ unread: number }>("/notifications")
      .then((r) => setUnread(r.unread))
      .catch(() => {});
  }, [pathname]);
  useInterval(refreshUnread, 20000);

  if (!user) return <div className="p-6 text-sm text-muted">Loading…</div>;

  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  return (
    <UserContext.Provider value={user}>
      <div className="min-h-screen">
        <header className="no-print border-b border-rule bg-surface">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
            <Link href={HOME[user.role]} className="flex items-baseline gap-2 py-1">
              <span className="text-lg font-bold tracking-tight text-accent">EduCrew</span>
              <span className="hidden text-xs text-muted sm:inline">CSE (AI &amp; ML)</span>
            </Link>
            <nav className="order-3 -mx-1 flex w-full flex-wrap gap-1 sm:order-none sm:w-auto" aria-label="Main">
              {NAV[user.role].map((item) => {
                const active = pathname === item.href || (item.href !== "/hod" && pathname.startsWith(item.href + "/"));
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`rounded-md px-2.5 py-2 text-sm ${
                      active ? "bg-accent-soft font-semibold text-accent" : "text-ink-2 hover:bg-paper hover:text-ink"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <div className="ml-auto flex items-center gap-1">
              <Link href="/inbox" className="btn btn-ghost btn-sm relative" aria-label={`Inbox, ${unread} unread`}>
                <Icon name="bell" />
                {unread > 0 && (
                  <span className="absolute -right-0.5 -top-0.5 min-w-5 rounded-full bg-bad px-1 text-center text-[11px] font-semibold leading-5 text-white">
                    {unread}
                  </span>
                )}
              </Link>
              <div className="hidden text-right leading-tight md:block">
                <div className="text-sm font-medium">{user.name}</div>
                <div className="text-xs text-muted">{ROLE_LABEL[user.role]}</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={logout} aria-label="Log out">
                <Icon name="logout" />
              </button>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </div>
    </UserContext.Provider>
  );
}
