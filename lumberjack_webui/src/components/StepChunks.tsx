import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ChunksStage } from '../types/pipeline';
import styles from './StepChunks.module.css';

interface Props {
  data: ChunksStage;
}

export default function StepChunks({ data }: Props) {
  const { t } = useTranslation();
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());
  const totalTokens = data.chunks.reduce((sum, c) => sum + c.token_count, 0);
  const maxTokens = Math.max(...data.chunks.map((c) => c.token_count), 1);

  const toggleChunk = (idx: number) =>
    setExpandedChunks((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });

  return (
    <div>
      <div className={styles.summary}>
        <span className={styles.statBadge}>
          <span className={styles.statValue}>{data.chunk_count}</span>
          <span className={styles.statLabel}>{t('step_chunks_label')}</span>
        </span>
        <span className={styles.statBadge}>
          <span className={styles.statValue}>{totalTokens.toLocaleString()}</span>
          <span className={styles.statLabel}>{t('step_total_tokens')}</span>
        </span>
        <span className={styles.statBadge}>
          <span className={styles.statValue}>{data.document}</span>
          <span className={styles.statLabel}>{t('step_document')}</span>
        </span>
      </div>

      <div className={styles.chunkList}>
        {data.chunks.map((chunk, i) => {
          const fill = (chunk.token_count / maxTokens) * 100;
          const isExpanded = expandedChunks.has(i);
          const heading = chunk.headings.map(([, t]) => t).join(' > ');

          return (
            <div key={chunk.chunk_id} className={styles.chunkCard}>
              <div className={styles.chunkHeader} onClick={() => toggleChunk(i)}>
                <div className={styles.chunkInfo}>
                  <span className={styles.chunkIndex}>#{i + 1}</span>
                  {heading && <span className={styles.chunkHeading}>{heading}</span>}
                </div>
                <div className={styles.chunkMeta}>
                  <span className={styles.chunkTokenBadge}>{t('chunk_tokens', { count: chunk.token_count })}</span>
                  {chunk.start_line != null && (
                    <span className={styles.chunkLines}>
                      L{chunk.start_line}
                      {chunk.end_line != null && `-${chunk.end_line}`}
                    </span>
                  )}
                  <span className={`${styles.expandIcon} ${isExpanded ? styles.expandOpen : ''}`}>
                    ▶
                  </span>
                </div>
              </div>
              <div className={styles.budgetBar}>
                <div className={styles.budgetFill} style={{ width: `${fill}%` }} />
              </div>
              {isExpanded && (
                <div className={styles.chunkBody}>
                  <pre className={styles.chunkText}>{chunk.text}</pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
