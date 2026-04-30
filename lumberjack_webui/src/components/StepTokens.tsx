import { useTranslation } from 'react-i18next';
import type { TokensStage, TokenData } from '../types/pipeline';
import styles from './StepTokens.module.css';

const TYPE_COLORS: Record<string, string> = {
  heading: '#7c3aed',
  paragraph: '#059669',
  code: '#d97706',
  fence: '#d97706',
  inline: '#3b82f6',
  bullet_list: '#0d9488',
  ordered_list: '#0d9488',
  list: '#0d9488',
  blockquote: '#6366f1',
  table: '#ec4899',
  hr: '#94a3b8',
  html: '#ef4444',
};

function getTokenColor(type: string): string {
  const base = type.replace(/_open$/, '').replace(/_close$/, '').replace(/_inline$/, '');
  for (const [key, color] of Object.entries(TYPE_COLORS)) {
    if (base.includes(key)) return color;
  }
  return '#64748b';
}

function isFlatToken(t: TokenData): boolean {
  return !t.children || t.children.length === 0;
}

interface Props {
  data: TokensStage;
}

export default function StepTokens({ data }: Props) {
  const { t } = useTranslation();
  const flatTokens: { token: TokenData; depth: number }[] = [];

  function flatten(tokens: TokenData[], depth: number) {
    for (const t of tokens) {
      flatTokens.push({ token: t, depth });
      if (t.children) {
        flatten(t.children, depth + 1);
      }
    }
  }
  flatten(data.tokens, 0);

  return (
    <div>
      <div className={styles.summary}>
        <span className={styles.summaryText}>
          <strong>{data.count}</strong> {t('tokens_produced_suffix')}
        </span>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.colIdx}>{t('tok_col_index')}</th>
              <th className={styles.colType}>{t('tok_col_type')}</th>
              <th className={styles.colTag}>{t('tok_col_tag')}</th>
              <th className={styles.colNesting}>{t('tok_col_nesting')}</th>
              <th className={styles.colContent}>{t('tok_col_content')}</th>
              <th className={styles.colLines}>{t('tok_col_lines')}</th>
            </tr>
          </thead>
          <tbody>
            {flatTokens.map(({ token, depth }, i) => {
              const color = getTokenColor(token.type);
              const nestingSymbol =
                token.nesting === 1 ? '▸' : token.nesting === -1 ? '▿' : '·';
              return (
                <tr key={i} className={isFlatToken(token) ? styles.rowFlat : ''}>
                  <td className={styles.colIdx}>{i + 1}</td>
                  <td
                    className={styles.colType}
                    style={{ paddingLeft: `${depth * 16 + 12}px` }}
                  >
                    <span
                      className={styles.typeBadge}
                      style={{ background: `${color}18`, color }}
                    >
                      {token.type}
                    </span>
                  </td>
                  <td className={styles.colTag}>{token.tag || '—'}</td>
                  <td className={styles.colNesting}>
                    <span className={styles.nestingSymbol}>{nestingSymbol}</span>
                    {token.nesting}
                  </td>
                  <td className={styles.colContent} title={token.content}>
                    {token.content ? (
                      token.content.length > 60 ? (
                        token.content.slice(0, 60) + '...'
                      ) : (
                        token.content
                      )
                    ) : (
                      <span className={styles.empty}>—</span>
                    )}
                  </td>
                  <td className={styles.colLines}>
                    {token.map ? `${token.map[0] + 1}-${token.map[1]}` : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
