import { useTranslation } from 'react-i18next';
import type { ChunkData, SourceLocation } from '../types/chunk';
import styles from './ChunkResult.module.css';

interface Props {
  chunk: ChunkData;
  index: number;
}

function formatPercent(value: number): string {
  const rounded = Math.abs(value) >= 10 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${value >= 0 ? '+' : ''}${rounded}%`;
}

function locationSummary(location: SourceLocation): string | null {
  const parts: string[] = [];
  if (location.page_start != null) {
    parts.push(
      location.page_end != null && location.page_end !== location.page_start
        ? `p.${location.page_start}-${location.page_end}`
        : `p.${location.page_start}`,
    );
  }
  if (location.sheet) parts.push(location.sheet);
  if (location.row_start != null) {
    parts.push(
      location.row_end != null && location.row_end !== location.row_start
        ? `r.${location.row_start}-${location.row_end}`
        : `r.${location.row_start}`,
    );
  }
  if (location.json_path) parts.push(location.json_path);
  if (location.element_id) parts.push(`#${location.element_id}`);
  return parts.length > 0 ? parts.join(' ') : null;
}

export default function ChunkResult({ chunk, index }: Props) {
  const { t } = useTranslation();

  const headingBreadcrumb = [
    ...chunk.ancestor_headings,
    ...(chunk.own_heading ? [chunk.own_heading] : []),
  ]
    .map(([, title]) => title)
    .join(' > ');

  const lineRange =
    chunk.start_line != null && chunk.end_line != null
      ? t('chunk_lines', { from: chunk.start_line, to: chunk.end_line })
      : null;

  const estimateDelta =
    chunk.token_count > 0
      ? ((chunk.estimated_token_count - chunk.token_count) / chunk.token_count) * 100
      : null;

  const extraLocations = Array.from(
    new Set(
      chunk.source_locations
        .map(locationSummary)
        .filter((value): value is string => value !== null),
    ),
  ).slice(0, 3);

  return (
    <div className={`${styles.card} ${chunk.protected ? styles.protectedCard : ''}`}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.index}>#{index + 1}</span>
          <span className={styles.tokenBadge}>
            {t('chunk_tokens', { count: chunk.token_count })}
            {` (${chunk.headings_token_count} + ${chunk.body_token_count})`}
          </span>
          <span
            className={styles.estimateBadge}
            title={t('chunk_estimated_title')}
          >
            {t('chunk_estimated', { count: chunk.estimated_token_count })}
            {estimateDelta !== null && (
              <span className={Math.abs(estimateDelta) > 5 ? styles.estimateWarn : ''}>
                {` Δ${formatPercent(estimateDelta)}`}
              </span>
            )}
          </span>
          {lineRange && <span className={styles.lineRange}>{lineRange}</span>}
        </div>
        <div className={styles.headerRight}>
          {chunk.protected && (
            <span className={styles.protectedBadge}>{t('chunk_protected')}</span>
          )}
          <span className={styles.kindBadge}>{chunk.chunk_type}</span>
        </div>
      </div>
      {headingBreadcrumb && (
        <div className={styles.breadcrumb}>{headingBreadcrumb}</div>
      )}
      {extraLocations.length > 0 && (
        <div className={styles.locations}>{extraLocations.join(' · ')}</div>
      )}
      <pre className={styles.content}>
        {chunk.body}
      </pre>
    </div>
  );
}
