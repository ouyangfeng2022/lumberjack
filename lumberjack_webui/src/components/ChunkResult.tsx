import { useState } from 'react';
import type { ChunkData } from '../types/chunk';
import styles from './ChunkResult.module.css';

interface Props {
  chunk: ChunkData;
  index: number;
}

export default function ChunkResult({ chunk, index }: Props) {
  const [showBody, setShowBody] = useState(false);

  const headingBreadcrumb = chunk.headings
    .map(([, title]) => title)
    .join(' > ');

  const lineRange =
    chunk.start_line != null && chunk.end_line != null
      ? `Lines ${chunk.start_line}–${chunk.end_line}`
      : null;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.index}>#{index + 1}</span>
          <span className={styles.tokenBadge}>{chunk.token_count} tokens</span>
          {lineRange && <span className={styles.lineRange}>{lineRange}</span>}
        </div>
        <button
          className={styles.toggleBtn}
          onClick={() => setShowBody(!showBody)}
        >
          {showBody ? 'Show full text' : 'Show body only'}
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
