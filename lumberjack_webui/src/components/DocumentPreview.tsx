import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { RunSnapshot } from "../lib/workspace";
import { chunksAtLine } from "../lib/workspace";
import { isBinaryFormat, resolvedFormat } from "../lib/formats";
import ChunkList from "./ChunkList";
import styles from "../App.module.css";

export default function DocumentPreview({
  run,
  selected,
  onSelect,
}: {
  run: RunSnapshot;
  selected: number;
  onSelect: (index: number) => void;
}) {
  const { t } = useTranslation();
  const [boundaries, setBoundaries] = useState(true);
  const [heat, setHeat] = useState(false);
  const [source, setSource] = useState(false);
  const [visibleLines, setVisibleLines] = useState(300);
  const lines = run.input.text.split(/\r\n|\r|\n/);
  const binary = !!run.input.file && isBinaryFormat(resolvedFormat(run.input));
  return (
    <section className={styles.canvas}>
      <div className={styles.toolbar}>
        <strong>{source ? t("ws_source") : t("ws_full_preview")}</strong>
        <div className={styles.previewControls}>
          {!binary && (
            <button aria-pressed={source} onClick={() => setSource(!source)}>
              {t("ws_source")}
            </button>
          )}
          <button
            aria-pressed={boundaries}
            onClick={() => setBoundaries(!boundaries)}
          >
            {t("ws_boundaries")}
          </button>
          <button aria-pressed={heat} onClick={() => setHeat(!heat)}>
            {t("ws_heat")}
          </button>
        </div>
      </div>
      {source ? (
        <div className={styles.source}>
          <p className={styles.notice}>{t("ws_source_hint")}</p>
          {lines.slice(0, visibleLines).map((line, index) => {
            const matches = chunksAtLine(run.result.chunks, index + 1);
            return (
              <div
                key={index}
                className={
                  matches.includes(selected)
                    ? styles.sourceSelected
                    : styles.sourceLine
                }
              >
                <span className={styles.lineNumber}>{index + 1}</span>
                <pre>{line || " "}</pre>
                <span>
                  {matches.map((chunkIndex) => (
                    <button
                      key={chunkIndex}
                      onClick={() => onSelect(chunkIndex)}
                    >
                      #{chunkIndex + 1}
                    </button>
                  ))}
                </span>
              </div>
            );
          })}
          {lines.length > visibleLines && (
            <button
              className={styles.loadMore}
              onClick={() => setVisibleLines(visibleLines + 300)}
            >
              {t("ws_more_lines", { count: lines.length - visibleLines })}
            </button>
          )}
        </div>
      ) : (
        <ChunkList
          key={run.revision + ":" + run.options.splitter}
          result={run.result}
          options={run.options}
          {...{ selected, onSelect, boundaries, heat }}
        />
      )}
    </section>
  );
}
