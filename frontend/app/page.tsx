"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import ClusterCard from "@/components/ClusterCard";
import Navbar from "@/components/Navbar";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Cluster, Theme } from "@/lib/types";

export default function FeedPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [themes, setThemes] = useState<Theme[]>([]);
  const [activeTheme, setActiveTheme] = useState<number | undefined>(undefined);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    api.listThemes().then(setThemes).catch(() => {});
  }, [user]);

  useEffect(() => {
    if (!user) return;
    setBusy(true);
    api
      .feed(activeTheme)
      .then(setClusters)
      .catch((e) => setError(e instanceof Error ? e.message : "Erreur"))
      .finally(() => setBusy(false));
  }, [user, activeTheme]);

  if (loading) return null;

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-3xl px-4 py-6">
        <div className="mb-4 flex flex-wrap gap-2">
          <button
            onClick={() => setActiveTheme(undefined)}
            className={
              "rounded-full px-3 py-1 text-sm " +
              (activeTheme === undefined
                ? "bg-sky-600 text-white"
                : "border border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800")
            }
          >
            Tous
          </button>
          {themes.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTheme(t.id)}
              className={
                "rounded-full px-3 py-1 text-sm " +
                (activeTheme === t.id
                  ? "bg-sky-600 text-white"
                  : "border border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800")
              }
            >
              {t.name}
            </button>
          ))}
        </div>

        {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

        {busy ? (
          <p className="text-sm text-neutral-500">Chargement…</p>
        ) : clusters.length === 0 ? (
          <div className="rounded-xl border border-dashed border-neutral-300 p-10 text-center text-neutral-500 dark:border-neutral-700">
            Aucune actualité pour le moment.{" "}
            <a href="/themes" className="text-sky-600 hover:underline">
              Créez un thème
            </a>{" "}
            et lancez un scan.
          </div>
        ) : (
          <div className="space-y-4">
            {clusters.map((c) => (
              <ClusterCard key={c.id} cluster={c} />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
