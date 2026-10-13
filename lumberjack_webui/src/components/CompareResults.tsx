import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { CompareColumn } from "../types/chunk";
import { summarize } from "../lib/workspace";
import type { DocumentInput } from "../lib/formats";
import ChunkList from "./ChunkList";
import styles from "../App.module.css";

export default function CompareResults({
  columns,
  input,
  stale,
  loading,
  onAdopt,
}: {
  columns: CompareColumn[];
  input: DocumentInput;
  stale: boolean;
  loading: boolean;
  onAdopt: (column: CompareColumn) => void;
}) {
  const { t } = useTranslation();
  const [active, setActive] = useState(0);
  const [selected, setSelected] = useState<Record<string, number>>({});
  const [base, other] = columns;
  const a = base?.result ? summarize(base.result, base.options) : null;
  const b = other?.result ? summarize(other.result, other.options) : null;
  const comparable = base?.options.tokenizer === other?.options.tokenizer;
  return (
    <>
      <div className={styles.mobileTabs}>
        {columns.map((column, index) => (
          <button
            key={column.id}
            aria-pressed={active === index}
            onClick={() => setActive(index)}
          >
            {column.id} · {column.splitter}
          </button>
        ))}
      </div>
      <div className={styles.compareGrid}>
        {columns.map((column, index) => {
          const stats =
            column.result && summarize(column.result, column.options);
          return (
            <section
              key={column.id}
              className={
                styles.comparePane +
                " " +
                (active === index ? styles.activePane : "")
              }
            >
              <header className={styles.toolbar}>
                <strong>
                  <span className={styles.planBadge}>{column.id}</span>{" "}
                  {column.splitter}
                </strong>
                {stats && (
                  <span className={styles.muted}>
                    {stats.count} {t("ws_chunks")} ·{" "}
                    {stats.total.toLocaleString()} tokens
                  </span>
                )}
              </header>
              {column.error && (
                <p role="alert" className={styles.error}>
                  {column.error}
                </p>
              )}
              {!column.result && !column.error && (
                <div className={styles.empty}>
                  {loading ? t("ws_waiting") : t("ws_no_result")}
                </div>
              )}
              {column.result && (
                <ChunkList
                  key={column.result.chunks[0]?.chunk_id ?? "empty"}
                  result={column.result}
                  options={column.options}
                  selected={selected[column.id] ?? 0}
                  onSelect={(value) =>
                    setSelected({ ...selected, [column.id]: value })
                  }
                  boundaries
                  heat={false}
                />
              )}
              {stats && (
                <footer className={styles.compareFooter}>
                  <span>
                    {stats.over} {t("ws_over")} · {t("ws_largest")}{" "}
                    {stats.largest} · {Math.round(column.elapsedMs ?? 0)} ms
                  </span>
                  <button
                    disabled={stale || loading}
                    onClick={() => onAdopt(column)}
                  >
                    {t("ws_adopt", { id: column.id })}
                  </button>
                </footer>
              )}
            </section>
          );
        })}
      </div>
      <div className={styles.compareSummary}>
        {a && b ? (
          <>
            <span>A → B</span>
            <span>
              {t("ws_chunk_count")}{" "}
              <b>
                {a.count} → {b.count}
              </b>
            </span>
            <span>
              {t("ws_total_tokens")}{" "}
              <b>
                {a.total.toLocaleString()} → {b.total.toLocaleString()}
              </b>{" "}
              {comparable && a.total > 0
                ? "(" + Math.round(((b.total - a.total) / a.total) * 100) + "%)"
                : ""}
            </span>
            <span>
              {t("ws_largest")}{" "}
              <b>
                {a.largest} → {b.largest}
              </b>
            </span>
            {!comparable && (
              <span className={styles.warning}>
                {t("ws_tokenizers_differ")}
              </span>
            )}
          </>
        ) : (
          <span>{t("ws_compare_hint")}</span>
        )}
        <span className={styles.muted}>{input.file?.name ?? input.format}</span>
      </div>
    </>
  );
}
