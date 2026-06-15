import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { BlockConfigState, SplitOptions as Options } from '../types/chunk';
import styles from './SplitOptions.module.css';

interface Props {
  options: Options;
  onChange: (options: Options) => void;
}

const BLOCK_KINDS = [
  'paragraph',
  'blockquote',
  'list',
  'table',
  'html_table',
  'code_block',
  'code_fence',
  'html_block',
  'front_matter',
] as const;

interface BlockState {
  isolated: boolean;
  split: boolean;
}

const DEFAULT_BLOCK_STATE: BlockState = { isolated: false, split: true };

function getBlockStates(block_configs: Options['block_configs']): Record<string, BlockState> {
  const result: Record<string, BlockState> = {};
  for (const kind of BLOCK_KINDS) {
    const cfg = block_configs?.[kind];
    result[kind] = {
      isolated: cfg?.isolated ?? false,
      split: cfg?.split ?? true,
    };
  }
  return result;
}

export default function SplitOptions({ options, onChange }: Props) {
  const { t } = useTranslation();
  const [showAdvanced, setShowAdvanced] = useState(true);

  const BLOCK_LABELS: Record<string, string> = {
    paragraph: t('opts_block_paragraph'),
    blockquote: t('opts_block_blockquote'),
    list: t('opts_block_list'),
    table: t('opts_block_table'),
    html_table: t('opts_block_html_table'),
    code_block: t('opts_block_code_block'),
    code_fence: t('opts_block_code_fence'),
    html_block: t('opts_block_html_block'),
    front_matter: t('opts_block_front_matter'),
  };

  const update = <K extends keyof Options>(key: K, value: Options[K]) => {
    onChange({ ...options, [key]: value });
  };

  const blockStates = getBlockStates(options.block_configs);

  const setBlockIsolated = (kind: string, isolated: boolean) => {
    const updated = { ...blockStates, [kind]: { ...blockStates[kind], isolated } };
    const cfg: Record<string, BlockConfigState> = {};
    for (const k of BLOCK_KINDS) {
      const s = updated[k] ?? DEFAULT_BLOCK_STATE;
      if (s.isolated || !s.split) {
        const entry: BlockConfigState = {};
        if (s.isolated) entry.isolated = true;
        if (!s.split) entry.split = false;
        cfg[k] = entry;
      }
    }
    update('block_configs', Object.keys(cfg).length > 0 ? cfg : null);
  };

  const toggleSplit = (kind: string) => {
    const prev = blockStates[kind] ?? DEFAULT_BLOCK_STATE;
    const updated = { ...blockStates, [kind]: { ...prev, split: !prev.split } };
    const cfg: Record<string, BlockConfigState> = {};
    for (const k of BLOCK_KINDS) {
      const s = updated[k] ?? DEFAULT_BLOCK_STATE;
      if (s.isolated || !s.split) {
        const entry: BlockConfigState = {};
        if (s.isolated) entry.isolated = true;
        if (!s.split) entry.split = false;
        cfg[k] = entry;
      }
    }
    update('block_configs', Object.keys(cfg).length > 0 ? cfg : null);
  };

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
              <span className={styles.fieldLabel}>{t('opts_ideal_max_tokens_ratio')}</span>
              <input
                type="number"
                min="0.01"
                max="1"
                step="0.05"
                className={styles.numberInput}
                value={options.ideal_max_tokens_ratio}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  if (!isNaN(val)) update('ideal_max_tokens_ratio', val);
                }}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>{t('opts_merge_below_tokens')}</span>
              <input
                type="number"
                className={styles.numberInput}
                value={options.merge_below_tokens}
                onChange={(e) => update('merge_below_tokens', Number(e.target.value))}
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
                checked={options.skip_empty_sections}
                onChange={(e) => update('skip_empty_sections', e.target.checked)}
              />
              <span>{t('opts_skip_empty_sections')}</span>
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
            <span className={styles.fieldLabel}>{t('opts_splitter')}</span>
            <select
              className={styles.select}
              value={options.splitter}
              onChange={(e) => update('splitter', e.target.value)}
            >
              <option value="recursive">{t('opts_splitter_recursive')}</option>
              <option value="section">{t('opts_splitter_section')}</option>
            </select>
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

          <div className={styles.checkRow}>
            <label
              className={`${styles.checkField} ${options.splitter !== 'section' ? styles.checkDisabled : ''}`}
            >
              <input
                type="checkbox"
                checked={options.recursive_split}
                disabled={options.splitter !== 'section'}
                onChange={(e) => update('recursive_split', e.target.checked)}
              />
              <span>{t('opts_recursive_split')}</span>
            </label>
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>{t('opts_block_handling')}</span>
            <div className={styles.blockHandlingGrid}>
              <div className={styles.blockHandlingHeader}>
                <span className={styles.blockKindLabel} />
                <span
                  className={styles.blockHeaderLabel}
                  title={t('opts_isolated_desc')}
                >
                  {t('opts_isolated')}
                </span>
                <span
                  className={styles.blockHeaderLabel}
                  title={t('opts_nosplit_desc')}
                >
                  {t('opts_nosplit')}
                </span>
              </div>
              {BLOCK_KINDS.map((kind) => {
                const state = blockStates[kind] ?? DEFAULT_BLOCK_STATE;
                return (
                  <div key={kind} className={styles.blockHandlingRow}>
                    <span className={styles.blockKindLabel}>{BLOCK_LABELS[kind]}</span>
                    <input
                      className={styles.blockNosplit}
                      type="checkbox"
                      checked={state.isolated}
                      onChange={(e) => setBlockIsolated(kind, e.target.checked)}
                    />
                    <input
                      className={styles.blockNosplit}
                      type="checkbox"
                      checked={!state.split}
                      onChange={() => toggleSplit(kind)}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
