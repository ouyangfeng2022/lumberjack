import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SplitOptions as Options } from '../types/chunk';
import styles from './SplitOptions.module.css';

interface Props {
  options: Options;
  onChange: (options: Options) => void;
}

const BLOCK_HANDLING_OPTIONS = [
  'paragraph',
  'blockquote',
  'list',
  'table',
  'code_block',
  'code_fence',
  'html_block',
] as const;

type BlockPolicy = 'default' | 'isolate';

const DEFAULT_HANDLING: Record<string, BlockPolicy> = {
  paragraph: 'default',
  blockquote: 'default',
  html_block: 'default',
  table: 'default',
  code_block: 'default',
  code_fence: 'default',
};

function parseBlockHandling(raw: string): Record<string, BlockPolicy> {
  const result: Record<string, BlockPolicy> = { ...DEFAULT_HANDLING };
  if (!raw || !raw.trim()) return result;
  for (const part of raw.split(',')) {
    const trimmed = part.trim();
    if (!trimmed || !trimmed.includes(':')) continue;
    const colonIdx = trimmed.indexOf(':');
    const kind = trimmed.slice(0, colonIdx).trim().toLowerCase();
    const policy = trimmed.slice(colonIdx + 1).trim().toLowerCase() as BlockPolicy;
    if (kind && ['default', 'isolate'].includes(policy)) {
      result[kind] = policy;
    }
  }
  return result;
}

function serializeBlockHandling(handling: Record<string, BlockPolicy>): string {
  const entries = Object.entries(handling)
    .filter(([kind]) => BLOCK_HANDLING_OPTIONS.includes(kind as typeof BLOCK_HANDLING_OPTIONS[number]))
    .filter(([kind, policy]) => {
      const def = DEFAULT_HANDLING[kind];
      return def !== policy;
    });
  if (entries.length === 0) return '';
  return entries.map(([kind, policy]) => `${kind}:${policy}`).join(',');
}

function parseNosplitKinds(raw: string): Set<string> {
  if (!raw || !raw.trim()) return new Set();
  return new Set(
    raw.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean)
  );
}

function serializeNosplitKinds(kinds: Set<string>): string {
  return Array.from(kinds).join(',');
}

const POLICIES: { value: BlockPolicy; labelKey: string }[] = [
  { value: 'default', labelKey: 'opts_policy_default' },
  { value: 'isolate', labelKey: 'opts_policy_isolate' },
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

  const handlingMap = parseBlockHandling(options.block_handling);
  const nosplitSet = parseNosplitKinds(options.nosplit_kinds);

  const setBlockPolicy = (kind: string, policy: BlockPolicy) => {
    const updated = { ...handlingMap, [kind]: policy };
    update('block_handling', serializeBlockHandling(updated));
  };

  const toggleNosplit = (kind: string) => {
    const next = new Set(nosplitSet);
    if (next.has(kind)) {
      next.delete(kind);
    } else {
      next.add(kind);
    }
    update('nosplit_kinds', serializeNosplitKinds(next));
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
              <option value="default">{t('opts_splitter_default')}</option>
              <option value="section">{t('opts_splitter_section')}</option>
              <option value="recursive">{t('opts_splitter_recursive')}</option>
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
              {BLOCK_HANDLING_OPTIONS.map((kind) => (
                <div key={kind} className={styles.blockHandlingRow}>
                  <span className={styles.blockKindLabel}>{BLOCK_LABELS[kind]}</span>
                  <select
                    className={styles.blockPolicySelect}
                    value={handlingMap[kind] || 'default'}
                    onChange={(e) => setBlockPolicy(kind, e.target.value as BlockPolicy)}
                  >
                    {POLICIES.map((p) => (
                      <option key={p.value} value={p.value}>
                        {t(p.labelKey)}
                      </option>
                    ))}
                  </select>
                  <label className={styles.checkField}>
                    <input
                      type="checkbox"
                      checked={!nosplitSet.has(kind)}
                      onChange={() => toggleNosplit(kind)}
                    />
                    <span>{t('opts_nosplit')}</span>
                  </label>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
