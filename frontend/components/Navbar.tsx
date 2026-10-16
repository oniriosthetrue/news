"use client";

import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import UsageBadge from "./UsageBadge";

export default function Navbar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  return (
    <header className="border-b border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-6">
          <a href="/" className="text-lg font-bold tracking-tight">
            News<span className="text-sky-600">Minervia</span>
          </a>
          {user && (
            <nav className="flex gap-4 text-sm">
              <a
                href="/"
                className={
                  pathname === "/"
                    ? "font-semibold text-sky-600"
                    : "text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
                }
              >
                Fil
              </a>
              <a
                href="/themes"
                className={
                  pathname === "/themes"
                    ? "font-semibold text-sky-600"
                    : "text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
                }
              >
                Thèmes
              </a>
            </nav>
          )}
        </div>
        {user && (
          <div className="flex items-center gap-3 text-sm">
            <UsageBadge />
            <span className="text-neutral-500">{user.display_name}</span>
            <button
              onClick={() => {
                logout();
                router.push("/login");
              }}
              className="rounded-md border border-neutral-300 px-3 py-1 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
            >
              Déconnexion
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
