"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Navbar from "@/components/Navbar";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Theme, Usage } from "@/lib/types";

// Heure du dernier scan, en heure de Paris (ex. « 17 oct. à 14:23 »).
function lastScanParis(iso: string): string {
  const d = new Date(iso);
  const sameYear =
    d.toLocaleDateString("fr-FR", { timeZone: "Europe/Paris" }) ===
    new Date().toLocaleDateString("fr-FR", { timeZone: "Europe/Paris" });
  return d.toLocaleString("fr-FR", {
    timeZone: "Europe/Paris",
    day: "numeric",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ThemesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [themes, setThemes] = useState<Theme[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [interval, setIntervalH] = useState(6);
  const [lookback, setLookbackH] = useState(24);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Brouillon d'intervalle par thème (id -> valeur en cours d'édition).
  const [drafts, setDrafts] = useState<Record<number, number>>({});
  // Brouillon de fenêtre de recherche par thème (id -> heures en arrière).
  const [lookbackDrafts, setLookbackDrafts] = useState<Record<number, number>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  // Thème dont le scan est en cours (null = aucun). Le scan tourne en
  // arrière-plan côté serveur ; on affiche l'état jusqu'à ce qu'il ait fini.
  const [scanningId, setScanningId] = useState<number | null>(null);
  // État du moteur (LLM on/off) : sert à avertir que les thèmes en attente ne
  // se rempliront qu'au retour du LLM.
  const [usage, setUsage] = useState<Usage | null>(null);
  // Message d'information non bloquant (ex. après création LLM off).
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  const refresh = useCallback(() => {
    if (!user) return;
    api.listThemes().then(setThemes).catch(() => {});
  }, [user]);

  useEffect(refresh, [refresh]);

  // Un thème « en attente » = jamais scanné (aucun article). Il se remplira
  // dès que le LLM sera joignable (l'ordonnanceur le retente à chaque tick).
  const hasPending = themes.some((t) => t.last_scanned_at == null);

  // État du moteur au montage + périodiquement (le LLM peut revenir).
  useEffect(() => {
    if (!user) return;
    let alive = true;
    const poll = () => api.usage().then((u) => alive && setUsage(u)).catch(() => {});
    poll();
    const id = setInterval(poll, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [user]);

  // Rafraîchissement continu tant qu'un thème est en attente : il se dégrise
  // de lui-même dès que le scan réussit (LLM revenu), sans rechargement manuel.
  useEffect(() => {
    if (!hasPending) return;
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [hasPending, refresh]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.createTheme(name, description, interval, lookback);
      setName("");
      setDescription("");
      refresh();
      setNotice(
        usage && !usage.llm_online
          ? "Thème créé. Le LLM est indisponible : le fil se remplira automatiquement dès son retour."
          : "Thème créé. Le fil se remplit, ça peut prendre une minute.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(false);
    }
  }

  async function scan(id: number) {
    if (scanningId != null) return;
    setError(null);
    setScanningId(id);
    const startedAt =
      themes.find((t) => t.id === id)?.last_scanned_at ?? null;
    try {
      await api.scanTheme(id);
      // Le scan s'exécute en arrière-plan : on attend que last_scanned_at
      // change (ou un délai max) pour rendre la main à l'utilisateur.
      const deadline = Date.now() + 60000;
      // eslint-disable-next-line no-constant-condition
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2000));
        let list: Theme[];
        try {
          list = await api.listThemes();
        } catch {
          continue;
        }
        setThemes(list);
        const done = list.find((t) => t.id === id)?.last_scanned_at ?? null;
        if (done && done !== startedAt) break;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur pendant le scan");
    } finally {
      setScanningId(null);
      refresh();
    }
  }

  async function remove(id: number) {
    await api.deleteTheme(id);
    refresh();
  }

  async function toggle(t: Theme) {
    await api.updateTheme(t.id, { is_active: !t.is_active });
    refresh();
  }

  async function saveInterval(t: Theme) {
    const value = drafts[t.id];
    if (value == null || value === t.scan_interval_hours || value < 1 || value > 168)
      return;
    setSavingId(t.id);
    try {
      await api.updateTheme(t.id, { scan_interval_hours: value });
      setDrafts((d) => {
        const next = { ...d };
        delete next[t.id];
        return next;
      });
      refresh();
    } finally {
      setSavingId(null);
    }
  }

  async function saveLookback(t: Theme) {
    const value = lookbackDrafts[t.id];
    if (value == null || value === t.lookback_hours || value < 1 || value > 8760)
      return;
    setSavingId(t.id);
    try {
      await api.updateTheme(t.id, { lookback_hours: value });
      setLookbackDrafts((d) => {
        const next = { ...d };
        delete next[t.id];
        return next;
      });
      refresh();
    } finally {
      setSavingId(null);
    }
  }

  if (loading) return null;

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-3xl px-4 py-6">
        <h1 className="mb-4 text-xl font-bold">Mes thèmes</h1>

        {usage && !usage.llm_online && (
          <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
            LLM indisponible : les thèmes en attente (grisés) seront alimentés
            automatiquement dès son retour. Aucune action requise.
          </div>
        )}
        {notice && (
          <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-800 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-200">
            <span>{notice}</span>
            <button
              onClick={() => setNotice(null)}
              className="text-sky-500 hover:text-sky-700"
              aria-label="Fermer"
            >
              ✕
            </button>
          </div>
        )}

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
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm text-neutral-500">Intervalle (h)</label>
            <input
              type="number"
              min={1}
              max={168}
              className="w-20 rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
              value={interval}
              onChange={(e) => setIntervalH(Number(e.target.value))}
            />
            <label className="text-sm text-neutral-500">Fenêtre (h)</label>
            <input
              type="number"
              min={1}
              max={8760}
              className="w-20 rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
              value={lookback}
              onChange={(e) => setLookbackH(Number(e.target.value))}
              title="Ne retenir que les articles publiés dans les N dernières heures"
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
          {themes.map((t) => {
            const pending = t.last_scanned_at == null;
            return (
            <div
              key={t.id}
              className={
                "flex items-center justify-between rounded-xl border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900" +
                (pending ? " opacity-60 grayscale" : "")
              }
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
                  {pending && (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                      en attente du LLM
                    </span>
                  )}
                  {t.last_scanned_at && (
                    <span
                      className="rounded bg-sky-100 px-1.5 py-0.5 text-xs text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
                      title={`Dernier scan : ${lastScanParis(t.last_scanned_at)} (heure de Paris)`}
                    >
                      🕒 {lastScanParis(t.last_scanned_at)}
                    </span>
                  )}
                </div>
                {t.description && (
                  <p className="truncate text-sm text-neutral-500">{t.description}</p>
                )}
                <div className="mt-2 flex items-center gap-2 text-xs text-neutral-500">
                  <label>Actualisation toutes</label>
                  <input
                    type="number"
                    min={1}
                    max={168}
                    className="w-16 rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
                    value={drafts[t.id] ?? t.scan_interval_hours}
                    onChange={(e) =>
                      setDrafts((d) => ({
                        ...d,
                        [t.id]: Math.max(1, Math.min(168, Number(e.target.value) || 1)),
                      }))
                    }
                  />
                  <span>h</span>
                  {(drafts[t.id] ?? t.scan_interval_hours) !== t.scan_interval_hours && (
                    <button
                      onClick={() => saveInterval(t)}
                      disabled={savingId === t.id}
                      className="rounded-md bg-sky-600 px-2 py-1 text-xs font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
                    >
                      {savingId === t.id ? "…" : "Enregistrer"}
                    </button>
                  )}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-neutral-500">
                  <label>Articles des</label>
                  <input
                    type="number"
                    min={1}
                    max={8760}
                    className="w-20 rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
                    value={lookbackDrafts[t.id] ?? t.lookback_hours}
                    onChange={(e) =>
                      setLookbackDrafts((d) => ({
                        ...d,
                        [t.id]: Math.max(
                          1,
                          Math.min(8760, Number(e.target.value) || 1),
                        ),
                      }))
                    }
                  />
                  <span>dernières h</span>
                  {(lookbackDrafts[t.id] ?? t.lookback_hours) !== t.lookback_hours && (
                    <button
                      onClick={() => saveLookback(t)}
                      disabled={savingId === t.id}
                      className="rounded-md bg-sky-600 px-2 py-1 text-xs font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
                    >
                      {savingId === t.id ? "…" : "Enregistrer"}
                    </button>
                  )}
                </div>
              </div>
              <div className="flex flex-shrink-0 gap-2 text-sm">
                <button
                  onClick={() => scan(t.id)}
                  disabled={scanningId != null}
                  className="inline-flex items-center gap-2 rounded-md bg-sky-600 px-3 py-1 text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {scanningId === t.id && (
                    <span
                      className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                      aria-hidden
                    />
                  )}
                  {scanningId === t.id ? "Scan en cours…" : "Scanner"}
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
            );
          })}
        </div>
      </main>
    </>
  );
}
