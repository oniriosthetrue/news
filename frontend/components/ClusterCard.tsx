import type { Cluster } from "@/lib/types";

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

export default function ClusterCard({ cluster }: { cluster: Cluster }) {
  const lead = cluster.articles[0];
  const extra = cluster.articles.slice(1);
  const published = newestPublished(cluster);

  return (
    <article className="overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex gap-4 p-4">
        {lead?.image_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={lead.image_url}
            alt=""
            className="h-24 w-24 flex-shrink-0 rounded-lg object-cover"
          />
        )}
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
        </div>
      </div>
      {extra.length > 0 && (
        <ul className="border-t border-neutral-100 bg-neutral-50 px-4 py-2 dark:border-neutral-800 dark:bg-neutral-950/40">
          {extra.map((a) => (
            <li key={a.id} className="flex items-center gap-2 py-1 text-sm">
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
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
