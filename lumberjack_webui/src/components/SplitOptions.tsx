import { useState } from 'react';
import type { SplitOptions as Options } from '../types/chunk';
import styles from './SplitOptions.module.css';

interface Props {
  options: Options;
  onChange: (options: Options) => void;
}

const SPLIT_BLOCK_OPTIONS = [
  'paragraph',
  'blockquote',
  'list',
  'table',
  'code_block',
  'code_fence',
  'html_block',
];

export default function SplitOptions({ options, onChange }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);

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
      <label className={styles.label}>Split Options</label>

      <div className={styles.row}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Max Tokens</span>
          <input
            type="number"
            className={styles.numberInput}
            value={options.max_tokens}
            onChange={(e) => update('max_tokens', Number(e.target.value))}
          />
        </label>
        <label className={styles.checkField}>
          <input
            type="checkbox"
            checked={options.retain_headings}
            onChange={(e) => update('retain_headings', e.target.checked)}
          />
          <span>Retain Headings</span>
        </label>
      </div>

      <button
        className={styles.toggleBtn}
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? '- Hide' : '+ Show'} Advanced Options
      </button>

      {showAdvanced && (
        <div className={styles.advanced}>
          <div className={styles.row}>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Min Tokens</span>
              <input
                type="number"
                className={styles.numberInput}
                value={options.min_tokens}
                onChange={(e) => update('min_tokens', Number(e.target.value))}
              />
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Overlap Tokens</span>
              <input
                type="number"
                className={styles.numberInput}
                value={options.overlap_tokens}
                onChange={(e) => update('overlap_tokens', Number(e.target.value))}
              />
            </label>
          </div>

          <label className={styles.checkField}>
            <input
              type="checkbox"
              checked={options.merge_small_chunks}
              onChange={(e) => update('merge_small_chunks', e.target.checked)}
            />
            <span>Merge Small Chunks</span>
          </label>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>Tokenizer</span>
            <select
              className={styles.select}
              value={options.tokenizer}
              onChange={(e) => update('tokenizer', e.target.value)}
            >
              <option value="simple">Simple</option>
              <option value="tiktoken">Tiktoken</option>
            </select>
          </div>

          <div className={styles.field}>
            <span className={styles.fieldLabel}>Split Oversized Blocks</span>
            <div className={styles.checkGroup}>
              {SPLIT_BLOCK_OPTIONS.map((block) => (
                <label key={block} className={styles.checkField}>
                  <input
                    type="checkbox"
                    checked={selectedBlocks.has(block)}
                    onChange={(e) => toggleBlock(block, e.target.checked)}
                  />
                  <span>{block}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
