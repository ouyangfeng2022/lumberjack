import { useTranslation } from "react-i18next";
import type { ChunkData, SplitOptions } from "../types/chunk";
import { budgetCount, chunkBudget } from "../lib/workspace";
import styles from "../App.module.css";

export default function ChunkResult({
  chunk,
  index,
  options,
  selected,
  onSelect,
  boundaries,
  heat,
}: {
  chunk: ChunkData;
  index: number;
  options: SplitOptions;
  selected: boolean;
  onSelect: () => void;
  boundaries: boolean;
  heat: boolean;
}) {
  const { t } = useTranslation();
  const count = budgetCount(chunk, options);
  const budget = chunkBudget(chunk, options);
  const over = count > budget;
  return (
    <article
      className={[
        styles.chunk,
        selected ? styles.selected : "",
        over ? styles.over : "",
      ].join(" ")}
      style={
        heat
          ? {
              background: over
                ? "var(--warning-bg)"
                : "color-mix(in srgb, var(--primary) " +
                  Math.min(15, Math.max(2, (count / budget) * 15)) +
                  "%, var(--surface))",
            }
          : undefined
      }
      data-chunk-index={index}
    >
      <button
        className={styles.chunkSelect}
        aria-label={t("ws_select_chunk", { index: index + 1 })}
        aria-pressed={selected}
        onClick={onSelect}
      >
        <span className={styles.chunkHeading}>
          {[
            ...chunk.ancestor_headings,
            ...(chunk.own_heading ? [chunk.own_heading] : []),
          ]
            .map(([, title]) => title)
            .join(" / ") || t("ws_untitled")}
        </span>
        <span className={over ? styles.warning : styles.muted}>
          #{index + 1} · {count} / {budget} tokens{" "}
          {over ? "· " + t("ws_over") : ""}
        </span>
      </button>
      <pre>{chunk.body || t("ws_heading_only")}</pre>
      {chunk.protected && (
        <p className={styles.warning}>
          {t("chunk_protected")} · {t("ws_protected_hint")}
        </p>
      )}
      {boundaries && (
        <div className={styles.boundary}>
          <span>
            ✂ #{index + 1} · {count} / {budget} tokens
          </span>
        </div>
      )}
    </article>
  );
}
