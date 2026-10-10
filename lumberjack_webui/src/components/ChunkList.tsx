import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { SplitResponse, SplitOptions } from "../types/chunk";
import ChunkResult from "./ChunkResult";
import styles from "../App.module.css";

export default function ChunkList({
  result,
  options,
  selected,
  onSelect,
  boundaries,
  heat,
}: {
  result: SplitResponse;
  options: SplitOptions;
  selected: number;
  onSelect: (index: number) => void;
  boundaries: boolean;
  heat: boolean;
}) {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(30);
  const ref = useRef<HTMLDivElement>(null);
  const count = Math.max(visible, selected + 1);
  useEffect(() => {
    ref.current
      ?.querySelector('[data-chunk-index="' + selected + '"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  return (
    <div ref={ref} className={styles.chunkList}>
      {result.chunks.slice(0, count).map((chunk, index) => (
        <ChunkResult
          key={chunk.chunk_id}
          {...{ chunk, index, options, boundaries, heat }}
          selected={index === selected}
          onSelect={() => onSelect(index)}
        />
      ))}
      {result.chunks.length > count && (
        <button
          className={styles.loadMore}
          onClick={() => setVisible(count + 30)}
        >
          {t("ws_more", { count: result.chunks.length - count })}
        </button>
      )}
      <p className={styles.end}>
        {t("ws_document_end", { count: result.chunks.length })}
      </p>
    </div>
  );
}
