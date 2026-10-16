"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Navbar from "@/components/Navbar";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Theme } from "@/lib/types";

export default function ThemesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [themes, setThemes] = useState<Theme[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [interval, setIntervalH] = useState(6);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const refresh = useCallback(() => {
    if (!user) return;
    api.listThemes().then(setThemes).catch(() => {});
  }, [user]);

  useEffect(refresh, [refresh]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.createTheme(name, description, interval);
      setName("");
      setDescription("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(false);
    }
  }

  async function scan(id: number) {
    await api.scanTheme(id);
    setTimeout(refresh, 1500);
  }

  async function remove(id: number) {
    await api.deleteTheme(id);
    refresh();
  }

  async function toggle(t: Theme) {
    await api.updateTheme(t.id, { is_active: !t.is_active });
    refresh();
  }

  if (loading) return null;

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-3xl px-4 py-6">
        <h1 className="mb-4 text-xl font-bold">Mes thèmes</h1>

        <form
          onSubmit={create}
          className="mb-6 space-y-3 rounded-xl border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
        >
          <input
            required
            className="w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-sky-500 dark:border-neutral-700"
            placeholder="Nom du thème (ex : IA, spatial, climat…)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <textarea
            className="w-full rounded-md border border-neutral-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-sky-500 dark:border-neutral-700"
            placeholder="Description (aide le LLM à élargir — optionnel)"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div className="flex items-center gap-3">
            <label className="text-sm text-neutral-500">Intervalle (h)</label>
            <input
              type="number"
              min={1}
              max={168}
              className="w-20 rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
              value={interval}
              onChange={(e) => setIntervalH(Number(e.target.value))}
            />
            <button
              type="submit"
              disabled={busy}
              className="ml-auto rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
            >
              {busy ? "…" : "Créer"}
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>

        <div className="space-y-3">
          {themes.length === 0 && (
            <p className="text-sm text-neutral-500">Aucun thème. Créez-en un ci-dessus.</p>
          )}
          {themes.map((t) => (
            <div
              key={t.id}
              className="flex items-center justify-between rounded-xl border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="font-semibold">{t.name}</h2>
                  <span
                    className={
                      "rounded px-1.5 py-0.5 text-xs " +
                      (t.is_active
                        ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
                        : "bg-neutral-200 text-neutral-500 dark:bg-neutral-800")
                    }
                  >
                    {t.is_active ? "actif" : "inactif"}
                  </span>
                </div>
                {t.description && (
                  <p className="truncate text-sm text-neutral-500">{t.description}</p>
                )}
                <p className="mt-1 text-xs text-neutral-400">
                  Toutes les {t.scan_interval_hours}h ·{" "}
                  {t.last_scanned_at
                    ? `scan ${new Date(t.last_scanned_at).toLocaleString("fr-FR")}`
                    : "jamais scanné"}
                </p>
              </div>
              <div className="flex flex-shrink-0 gap-2 text-sm">
                <button
                  onClick={() => scan(t.id)}
                  className="rounded-md bg-sky-600 px-3 py-1 text-white hover:bg-sky-700"
                >
                  Scanner
                </button>
                <button
                  onClick={() => toggle(t)}
                  className="rounded-md border border-neutral-300 px-3 py-1 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                >
                  {t.is_active ? "Pause" : "Activer"}
                </button>
                <button
                  onClick={() => remove(t.id)}
                  className="rounded-md border border-red-300 px-3 py-1 text-red-600 hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950"
                >
                  Suppr.
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
