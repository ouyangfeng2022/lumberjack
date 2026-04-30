import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ChunkData } from '../types/chunk';
import styles from './ChunkResult.module.css';

interface Props {
  chunk: ChunkData;
  index: number;
}

export default function ChunkResult({ chunk, index }: Props) {
  const { t } = useTranslation();
  const [showBody, setShowBody] = useState(false);

  const headingBreadcrumb = chunk.headings
    .map(([, title]) => title)
    .join(' > ');

  const lineRange =
    chunk.start_line != null && chunk.end_line != null
      ? t('chunk_lines', { from: chunk.start_line, to: chunk.end_line })
      : null;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.index}>#{index + 1}</span>
          <span className={styles.tokenBadge}>{t('chunk_tokens', { count: chunk.token_count })}</span>
          {lineRange && <span className={styles.lineRange}>{lineRange}</span>}
        </div>
        <button
          className={styles.toggleBtn}
          onClick={() => setShowBody(!showBody)}
        >
          {showBody ? t('chunk_show_full') : t('chunk_show_body')}
        </button>
      </div>
      {headingBreadcrumb && (
        <div className={styles.breadcrumb}>{headingBreadcrumb}</div>
      )}
      <pre className={styles.content}>
        {showBody ? chunk.body || chunk.text : chunk.text}
      </pre>
    </div>
  );
}
