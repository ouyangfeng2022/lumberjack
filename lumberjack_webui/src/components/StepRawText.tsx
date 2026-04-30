import { useTranslation } from 'react-i18next';
import type { RawTextInfo } from '../types/pipeline';
import styles from './StepRawText.module.css';

interface Props {
  data: RawTextInfo;
}

export default function StepRawText({ data }: Props) {
  const { t } = useTranslation();
  const lines = data.full_text.split('\n');

  return (
    <div>
      <div className={styles.stats}>
        <span className={styles.statBadge}>
          <span className={styles.statValue}>{data.char_count.toLocaleString()}</span>
          <span className={styles.statLabel}>{t('stats_characters')}</span>
        </span>
        <span className={styles.statBadge}>
          <span className={styles.statValue}>{data.line_count.toLocaleString()}</span>
          <span className={styles.statLabel}>{t('stats_lines')}</span>
        </span>
        <span className={styles.statBadge}>
          <span className={styles.statValue}>{data.word_count.toLocaleString()}</span>
          <span className={styles.statLabel}>{t('stats_words')}</span>
        </span>
      </div>

      <div className={styles.sourceView}>
        {lines.map((line, i) => (
          <div key={i} className={styles.line}>
            <span className={styles.lineNum}>{i + 1}</span>
            <span className={styles.lineContent}>{line}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
