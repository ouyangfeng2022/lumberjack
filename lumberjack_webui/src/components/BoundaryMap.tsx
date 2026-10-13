import { useTranslation } from "react-i18next";
import type { ChunkData, SplitOptions } from "../types/chunk";
import { budgetCount, chunkBudget } from "../lib/workspace";
import styles from "../App.module.css";

export default function BoundaryMap({
  chunks,
  options,
  selected,
  onSelect,
}: {
  chunks: ChunkData[];
  options: SplitOptions;
  selected: number;
  onSelect: (index: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={styles.minimap}>
      <strong>{t("boundary_title")}</strong>
      <div className={styles.segments} aria-label={t("boundary_title")}>
        {chunks.map((chunk, index) => (
          <button
            key={chunk.chunk_id}
            aria-label={t("ws_select_chunk", { index: index + 1 })}
            aria-pressed={selected === index}
            title={
              "#" +
              (index + 1) +
              " · " +
              budgetCount(chunk, options) +
              " tokens"
            }
            onClick={() => onSelect(index)}
            style={{
              flexGrow: Math.max(1, budgetCount(chunk, options)),
              background:
                budgetCount(chunk, options) > chunkBudget(chunk, options)
                  ? "var(--warning)"
                  : "var(--primary)",
            }}
          />
        ))}
      </div>
      <span className={styles.legend}>
        <i />
        {t("ws_normal")} <i className={styles.orange} />
        {t("ws_over")}
      </span>
    </div>
  );
}
