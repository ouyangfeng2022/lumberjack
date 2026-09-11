import { useTranslation } from 'react-i18next';
import { useMemo, useState } from 'react';
import type { ChunkData } from '../types/chunk';
import styles from './BoundaryMap.module.css';

interface Props {
  sourceText: string;
  chunks: ChunkData[];
  defaultOpen?: boolean;
}

const MAX_RENDERED_LINES = 1500;

export default function BoundaryMap({ sourceText, chunks, defaultOpen = true }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);

  const lines = useMemo(() => sourceText.split(/\r\n|\r|\n/), [sourceText]);

  const assignment = useMemo(() => {
    // lineIndex -> chunk index covering it (-1 when uncovered)
    const mapped = new Int32Array(lines.length).fill(-1);
    chunks.forEach((chunk, chunkIndex) => {
      if (chunk.start_line == null || chunk.end_line == null) return;
      const start = Math.max(0, chunk.start_line - 1);
      const end = Math.min(lines.length - 1, chunk.end_line - 1);
      for (let i = start; i <= end; i += 1) mapped[i] = chunkIndex;
    });
    return mapped;
  }, [chunks, lines.length]);

  const uncovered = useMemo(() => {
    let count = 0;
    for (let i = 0; i < lines.length; i += 1) {
      if (assignment[i] === -1) count += 1;
    }
    return count;
  }, [assignment, lines.length]);

  const renderedLines = Math.min(lines.length, MAX_RENDERED_LINES);
  const truncated = lines.length > MAX_RENDERED_LINES;

  return (
    <div className={styles.container}>
      <button className={styles.toggle} onClick={() => setOpen(!open)}>
        <span className={`${styles.caret} ${open ? styles.caretOpen : ''}`} aria-hidden>
          ▸
        </span>
        {t('boundary_title')}
        <span className={styles.meta}>
          {t('boundary_uncovered', { count: uncovered })}
        </span>
      </button>
      {open && (
        <div className={styles.map}>
          {Array.from({ length: renderedLines }, (_, i) => {
            const chunkIndex = assignment[i];
            const isStart =
              chunkIndex !== -1 &&
              (i === 0 || assignment[i - 1] !== chunkIndex);
            const cls =
              chunkIndex === -1
                ? styles.uncovered
                : chunkIndex % 2 === 0
                  ? styles.chunkA
                  : styles.chunkB;
            return (
              <div key={i} className={`${styles.line} ${cls} ${isStart ? styles.chunkStart : ''}`}>
                <span className={styles.lineNo}>{i + 1}</span>
                {isStart && (
                  <span className={styles.chunkBadge}>#{chunkIndex + 1}</span>
                )}
                <span className={styles.lineText}>{lines[i] || ' '}</span>
              </div>
            );
          })}
          {truncated && (
            <div className={styles.truncated}>
              {t('boundary_truncated', { count: lines.length })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
