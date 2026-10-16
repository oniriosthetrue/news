"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Usage } from "@/lib/types";

// Pastille d'état du moteur. Affiche en permanence « LLM on » / « LLM off »
// (passerelle LiteLLM joignable ou non). Sur le boîtier, un détail au clic
// montre aussi les sources de recherche et le solde de credits Serper.
export default function UsageBadge() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .usage()
      .then((u) => {
        if (alive) setUsage(u);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  // Avant le 1er chargement : pastille neutre (évite le badge qui « disparaît »).
  if (!loaded) {
    return (
      <span className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs font-medium text-neutral-400 dark:bg-neutral-800">
        LLM …
      </span>
    );
  }

  const llmOn = usage?.llm_online ?? false;
  const balance = usage?.serper?.balance;

  const pill = llmOn
    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
    : "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300";

  const hasDetail = !!usage && (balance != null || usage.fallback_order?.length > 0);

  return (
    <div className="relative">
      <button
        onClick={() => hasDetail && setOpen((o) => !o)}
        title={llmOn ? "LLM joignable" : "LLM injoignable (recherches en pause)"}
        className={`rounded-full px-2.5 py-1 text-xs font-medium ${pill}`}
      >
        <span
          className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle ${
            llmOn ? "bg-emerald-500" : "bg-red-500"
          }`}
        />
        LLM {llmOn ? "on" : "off"}
      </button>
      {open && usage && (
        <div className="absolute right-0 z-20 mt-2 w-64 rounded-lg border border-neutral-200 bg-white p-3 text-xs shadow-lg dark:border-neutral-700 dark:bg-neutral-900">
          <p className="mb-2 font-semibold">
            {usage.mirror_mode ? "Miroir (lecture seule)" : "Sources de recherche"}
          </p>
          {usage.mirror_mode ? (
            <p className="text-neutral-500">
              Ce site est un miroir : il affiche les résultats poussés par le
              boîtier. Les recherches reprennent quand le boîtier et le LLM sont
              de nouveau actifs.
            </p>
          ) : (
            <>
              <p className="mb-1 text-neutral-500">
                Ordre : {usage.fallback_order.join(" → ")}
              </p>
              <ul className="space-y-1">
                {usage.fallback_order.map((name) => {
                  const on =
                    usage.enabled[name.toLowerCase() as keyof Usage["enabled"]];
                  return (
                    <li key={name} className="flex items-center justify-between">
                      <span>{name}</span>
                      <span className={on ? "text-emerald-600" : "text-neutral-400"}>
                        {on ? "active" : "inactif"}
                      </span>
                    </li>
                  );
                })}
              </ul>
              {balance != null && (
                <p className="mt-2 border-t border-neutral-200 pt-2 text-neutral-500 dark:border-neutral-700">
                  Serper : {balance.toLocaleString("fr-FR")} credits restants (stock
                  unique, non renouvelable).
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
