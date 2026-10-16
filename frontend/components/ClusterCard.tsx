import { useState } from "react";
import type { Article, Cluster } from "@/lib/types";

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "à l'instant";
  if (mins < 60) return `il y a ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.floor(hours / 24);
  return `il y a ${days} j`;
}

// Date courte lisible (ex. « 14 oct. » ou « 14 oct. 2025 » si autre année).
function shortDate(iso: string): string {
  const d = new Date(iso);
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return d.toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

// Date de parution la plus recente parmi les articles du cluster.
function newestPublished(cluster: Cluster): string | null {
  const dates = cluster.articles
    .map((a) => a.published_at)
    .filter((d): d is string => Boolean(d))
    .sort();
  return dates.length ? dates[dates.length - 1] : null;
}

// Corps texte répliqué de l'article : paragraphe par ligne vide. trafilatura
// renvoie du texte brut (pas de HTML) -> aucun risque d'injection, on rend des
// <p> à partir des sauts de ligne. Lien vers la source d'origine en bas.
function ArticleBody({ article }: { article: Article }) {
  const paragraphs = article.content
    .split(/\n{2,}|\r\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  return (
    <div className="mt-2 space-y-2 border-t border-neutral-100 pt-3 text-sm leading-relaxed text-neutral-700 dark:border-neutral-800 dark:text-neutral-300">
      {paragraphs.map((p, i) => (
        <p key={i}>{p}</p>
      ))}
      <p className="pt-1">
        <a
          href={article.url}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-sky-600 hover:underline"
        >
          Lire l&apos;article complet sur {article.source} →
        </a>
      </p>
    </div>
  );
}

export default function ClusterCard({ cluster }: { cluster: Cluster }) {
  const lead = cluster.articles[0];
  const extra = cluster.articles.slice(1);
  const published = newestPublished(cluster);
  // Ids des articles dont le texte répliqué est déplié.
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());

  function toggle(id: number) {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <article className="overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <div className="p-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold leading-snug">
            <a href={lead?.url} target="_blank" rel="noreferrer" className="hover:underline">
              {cluster.title}
            </a>
          </h2>
          <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
            {cluster.summary}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-500">
            {lead && <span className="font-medium text-sky-600">{lead.source}</span>}
            {published ? (
              <span title={new Date(published).toLocaleString("fr-FR")}>
                {timeAgo(published)} · {shortDate(published)}
              </span>
            ) : (
              <span>{timeAgo(cluster.created_at)}</span>
            )}
            <span>{cluster.articles.length} source{cluster.articles.length > 1 ? "s" : ""}</span>
          </div>

          {/* Texte répliqué de l'article principal (dépliable). */}
          {lead?.content && (
            <div className="mt-3">
              <button
                onClick={() => toggle(lead.id)}
                className="rounded-md border border-neutral-300 px-2.5 py-1 text-xs font-medium text-neutral-600 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
              >
                {openIds.has(lead.id) ? "Masquer le texte" : "Lire le texte"}
              </button>
              {openIds.has(lead.id) && <ArticleBody article={lead} />}
            </div>
          )}
        </div>
      </div>
      {extra.length > 0 && (
        <ul className="border-t border-neutral-100 bg-neutral-50 px-4 py-2 dark:border-neutral-800 dark:bg-neutral-950/40">
          {extra.map((a) => (
            <li key={a.id} className="py-1">
              <div className="flex items-center gap-2 text-sm">
                <span className="rounded bg-neutral-200 px-1.5 py-0.5 text-xs font-medium text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">
                  {a.source}
                </span>
                <a
                  href={a.url}
                  target="_blank"
                  rel="noreferrer"
                  className="truncate text-neutral-600 hover:text-sky-600 hover:underline dark:text-neutral-400"
                >
                  {a.title}
                </a>
                {a.published_at && (
                  <span className="ml-auto flex-shrink-0 text-xs text-neutral-400">
                    {shortDate(a.published_at)}
                  </span>
                )}
                {a.content && (
                  <button
                    onClick={() => toggle(a.id)}
                    className="flex-shrink-0 rounded border border-neutral-300 px-1.5 py-0.5 text-xs text-neutral-500 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  >
                    {openIds.has(a.id) ? "−" : "Lire"}
                  </button>
                )}
              </div>
              {openIds.has(a.id) && <ArticleBody article={a} />}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
