import { useTranslation } from 'react-i18next';
import type { CompareColumn } from '../types/chunk';
import BoundaryMap from './BoundaryMap';
import ChunkList from './ChunkList';
import styles from './CompareResults.module.css';

interface Props {
  columns: CompareColumn[];
  sourceText: string;
}

function formatElapsed(ms: number) {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}

export default function CompareResults({ columns, sourceText }: Props) {
  const { t } = useTranslation();

  return (
    <div className={styles.grid}>
      {columns.map((column) => (
        <section key={column.splitter} className={styles.column}>
          <header className={styles.header}>
            <h3 className={styles.splitterName}>{column.splitter}</h3>
            {column.elapsedMs !== null && (
              <span className={styles.elapsed}>{formatElapsed(column.elapsedMs)}</span>
            )}
          </header>
          {column.error && <div className={styles.error}>{column.error}</div>}
          {column.result && (
            <>
              <div className={styles.summary}>
                <span>{t('chunks_count', { count: column.result.chunk_count })}</span>
                <span>
                  {t('chunks_total_tokens', {
                    count: column.result.chunks.reduce((sum, c) => sum + c.token_count, 0),
                  })}
                </span>
              </div>
              <div className={styles.boundaryWrap}>
                <BoundaryMap
                  sourceText={sourceText}
                  chunks={column.result.chunks}
                  defaultOpen={false}
                />
              </div>
              <div className={styles.chunkArea}>
                <ChunkList result={column.result} elapsedMs={null} />
              </div>
            </>
          )}
        </section>
      ))}
    </div>
  );
}
