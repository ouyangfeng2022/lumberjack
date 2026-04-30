import { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { SplitStage, EntryData } from '../types/pipeline';
import styles from './StepSplit.module.css';

const ENTRY_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

function entryColor(headings: [number, string][] | null): string {
  if (!headings || headings.length === 0) return ENTRY_COLORS[0];
  const hash = headings.reduce((sum, [, t]) => sum + t.length, 0);
  return ENTRY_COLORS[hash % ENTRY_COLORS.length];
}

function entryLabel(entry: EntryData, idx: number, t: (key: string, opts?: Record<string, unknown>) => string): string {
  if (!entry.headings || entry.headings.length === 0) return t('split_entry_label', { index: idx + 1 });
  return entry.headings.map(([, t]) => t).join(' > ');
}

interface Props {
  data: SplitStage;
}

export default function StepSplit({ data }: Props) {
  const { t } = useTranslation();
  const [selectedEntry, setSelectedEntry] = useState<number | null>(null);
  const maxTokens = data.options.max_tokens;

  const entryColorMap = useMemo(
    () => data.entries.map((e) => entryColor(e.headings)),
    [data.entries],
  );

  const entryLabelList = useMemo(
    () => data.entries.map((e, i) => entryLabel(e, i, t)),
    [data.entries, t],
  );

  const toggleEntry = useCallback(
    (idx: number) => setSelectedEntry((prev) => (prev === idx ? null : idx)),
    [],
  );

  return (
    <div>
      <div className={styles.budgetInfo}>
        {t('split_budget')}: <strong>{maxTokens}</strong> {t('split_tokens')} | {t('split_overlap')}: <strong>{data.options.overlap_tokens}</strong> {t('split_tokens')}
      </div>

      <div className={styles.grid}>
        <div className={styles.panel}>
          <div className={styles.panelTitle}>
          {t('split_entries')} ({data.entries.length})
          </div>
          <div className={styles.entryList}>
            {data.entries.map((entry, i) => (
              <div
                key={i}
                className={`${styles.entryItem} ${selectedEntry === i ? styles.entryItemSelected : ''}`}
                style={{ borderLeftColor: entryColorMap[i] }}
                onClick={() => toggleEntry(i)}
              >
                <div className={styles.entryHeadings}>{entryLabelList[i]}</div>
                <div className={styles.entryPreview}>
                  {entry.body.length > 100 ? entry.body.slice(0, 100) + '...' : entry.body}
                </div>
                {entry.start_line != null && (
                  <div className={styles.entryLines}>
                    L{entry.start_line}
                    {entry.end_line != null && `-${entry.end_line}`}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className={styles.panel}>
          <div className={styles.panelTitle}>
          {t('split_draft_chunks')} ({data.drafts.length})
          </div>
          <div className={styles.draftList}>
            {data.drafts.map((draft, di) => {
              const fill = Math.min((draft.token_count / maxTokens) * 100, 100);
              const isOver = draft.token_count > maxTokens;
              const containsSelected =
                selectedEntry !== null &&
                draft.entries.some(
                  (_e, ei) =>
                    ei ===
                    draft.entries.findIndex(
                      (de) =>
                        JSON.stringify(de.headings) ===
                          JSON.stringify(data.entries[selectedEntry]?.headings) &&
                        de.body === data.entries[selectedEntry]?.body,
                    ),
                );

              return (
                <div
                  key={di}
                  className={`${styles.draftCard} ${containsSelected ? styles.draftCardHighlight : ''}`}
                >
                  <div className={styles.draftHeader}>
                    <span className={styles.draftId}>{t('split_chunk_label', { index: di + 1 })}</span>
                    <span className={`${styles.draftTokens} ${isOver ? styles.draftTokensOver : ''}`}>
                      {t('chunk_tokens', { count: draft.token_count })}
                      {isOver && ` (${t('split_over_budget')})`}
                    </span>
                  </div>
                  <div className={styles.budgetBar}>
                    <div
                      className={`${styles.budgetFill} ${isOver ? styles.budgetFillOver : ''}`}
                      style={{ width: `${Math.min(fill, 100)}%` }}
                    />
                  </div>
                  <div className={styles.draftEntries}>
                    {draft.entries.map((entry, ei) => {
                      const color = entryColor(entry.headings);
                      const label = entry.headings?.length
                        ? entry.headings[entry.headings.length - 1][1]
                        : t('split_entry_label', { index: ei + 1 });
                      return (
                        <span key={ei} className={styles.draftEntryTag} style={{ background: `${color}18`, color }}>
                          {label}
                        </span>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
