import { useTranslation } from 'react-i18next';
import type { SplitterName } from '../types/chunk';
import { ALL_SPLITTERS, type ComparePreset } from '../lib/compare';
import styles from './CompareControls.module.css';

interface Props {
  enabled: boolean;
  preset: ComparePreset;
  customSplitters: SplitterName[];
  onToggle: (enabled: boolean) => void;
  onPresetChange: (preset: ComparePreset) => void;
  onCustomChange: (splitters: SplitterName[]) => void;
}

export default function CompareControls({
  enabled,
  preset,
  customSplitters,
  onToggle,
  onPresetChange,
  onCustomChange,
}: Props) {
  const { t } = useTranslation();

  const toggleCustom = (name: SplitterName) => {
    if (customSplitters.includes(name)) {
      onCustomChange(customSplitters.filter((s) => s !== name));
    } else {
      onCustomChange([...customSplitters, name]);
    }
  };

  return (
    <div className={styles.container}>
      <label className={styles.toggleRow}>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
        />
        <span>{t('compare_toggle')}</span>
      </label>
      {enabled && (
        <>
          <div className={styles.presetRow}>
            <span className={styles.presetLabel}>{t('compare_preset')}</span>
            <select
              className={styles.select}
              value={preset}
              onChange={(e) => onPresetChange(e.target.value as ComparePreset)}
            >
              <option value="topology">{t('compare_preset_topology')}</option>
              <option value="counting">{t('compare_preset_counting')}</option>
              <option value="custom">{t('compare_preset_custom')}</option>
            </select>
          </div>
          {preset === 'custom' && (
            <div className={styles.customGrid}>
              {ALL_SPLITTERS.map((name) => (
                <label key={name} className={styles.customChip}>
                  <input
                    type="checkbox"
                    checked={customSplitters.includes(name)}
                    onChange={() => toggleCustom(name)}
                  />
                  <span>{name}</span>
                </label>
              ))}
              <span className={styles.customHint}>{t('compare_custom_hint')}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
