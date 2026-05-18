import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SplitOptions as Options } from '../types/chunk';
import styles from './SplitOptions.module.css';

interface Props {
  options: Options;
  onChange: (options: Options) => void;
}

const SPLIT_BLOCK_OPTIONS = [
  'blockquote',
  'list',
  'table',
  'code_block',
  'code_fence',
  'html_block',
];

export default function SplitOptions({ options, onChange }: Props) {
  const { t } = useTranslation();
  const [showAdvanced, setShowAdvanced] = useState(true);

  const BLOCK_LABELS: Record<string, string> = {
    paragraph: t('opts_block_paragraph'),
    blockquote: t('opts_block_blockquote'),
    list: t('opts_block_list'),
    table: t('opts_block_table'),
    code_block: t('opts_block_code_block'),
    code_fence: t('opts_block_code_fence'),
    html_block: t('opts_block_html_block'),
  };

  const update = <K extends keyof Options>(key: K, value: Options[K]) => {
    onChange({ ...options, [key]: value });
  };

  const toggleBlock = (block: string, checked: boolean) => {
    const current = options.split_oversized_blocks
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    const next = checked
      ? [...current, block]
      : current.filter((b) => b !== block);
    update('split_oversized_blocks', next.join(','));
  };

  const selectedBlocks = new Set(
    options.split_oversized_blocks.split(',').map((s) => s.trim()),
  );

  return (
    <div className={styles.container}>
      <div className={styles.sectionTitle}>{t('opts_basic_section')}</div>
      <div className={styles.basicRow}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>{t('opts_max_tokens')}</span>
          <input
            type="number"
            className={styles.numberInput}
            value={options.max_tokens}
            onChange={(e) => update('max_tokens', Number(e.target.value))}
          />
        </label>
        <div className={styles.checkLine} >
          <label className={styles.checkField}>
            <input
              type="checkbox"
              checked={options.retain_headings}
              onChange={(e) => update('retain_headings', e.target.checked)}
            />
            <span>{t('opts_retain_headings')}</span>
          </label>
          <label
            className={`${styles.checkField} ${!options.retain_headings ? styles.checkDisabled : ''}`}
          >
            <input
              type="checkbox"
              checked={options.include_common_headings}
              disabled={!options.retain_headings}
              onChange={(e) => update('include_common_headings', e.target.checked)}
            />
            <span>{t('opts_include_common_headings')}</span>
          </label>
        </div>
      </div>

      <button
        className={styles.toggleBtn}
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? t('opts_hide_advanced') : t('opts_show_advanced')}
      </button>

      {showAdvanced && (
        <div className={styles.advanced}>
          <div className={styles.sectionTitle}>{t('opts_strategy_section')}</div>
          <div className={styles.row}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t('opts_merge_below_tokens')}</span>
              <input
                type="number"
                className={styles.numberInput}
                value={options.merge_below_tokens}
                onChange={(e) => update('merge_below_tokens', Number(e.target.value))}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t('opts_overlap_tokens')}</span>
              <input
                type="number"
                className={styles.numberInput}
                value={options.overlap_tokens}
                onChange={(e) => update('overlap_tokens', Number(e.target.value))}
              />
            </label>
          </div>

          <div className={styles.checkRow}>
            <label className={styles.checkField}>
              <input
                type="checkbox"
                checked={options.merge_small_chunks}
                onChange={(e) => update('merge_small_chunks', e.target.checked)}
              />
              <span>{t('opts_merge_small')}</span>
            </label>

            <label className={styles.checkField}>
              <input
                type="checkbox"
                checked={options.isolate_front_matter}
                onChange={(e) => update('isolate_front_matter', e.target.checked)}
              />
              <span>{t('opts_isolate_front_matter')}</span>
            </label>

            <label className={styles.checkField}>
              <input
                type="checkbox"
                checked={options.disable_lheading}
                onChange={(e) => update('disable_lheading', e.target.checked)}
              />
              <span>{t('opts_disable_lheading')}</span>
            </label>
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t('opts_tokenizer')}</span>
            <select
              className={styles.select}
              value={options.tokenizer}
              onChange={(e) => update('tokenizer', e.target.value)}
            >
              <option value="simple">{t('opts_tokenizer_simple')}</option>
              <option value="tiktoken">{t('opts_tokenizer_tiktoken')}</option>
            </select>
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t('opts_split_oversized')}</span>
            <div className={styles.checkGroup}>
              {SPLIT_BLOCK_OPTIONS.map((block) => (
                <label key={block} className={styles.checkField}>
                  <input
                    type="checkbox"
                    checked={selectedBlocks.has(block)}
                    onChange={(e) => toggleBlock(block, e.target.checked)}
                  />
                  <span>{BLOCK_LABELS[block]}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
