import { useTranslation } from 'react-i18next';
import { BUILT_IN_SAMPLES } from '../samples';
import styles from './SamplePicker.module.css';

interface Props {
  onLoad: (text: string) => void;
}

export default function SamplePicker({ onLoad }: Props) {
  const { t } = useTranslation();

  return (
    <select
      className={styles.select}
      value=""
      onChange={(e) => {
        const sample = BUILT_IN_SAMPLES.find((s) => s.id === e.target.value);
        if (sample) onLoad(sample.text);
      }}
      aria-label={t('sample_label')}
      title={t('sample_label')}
    >
      <option value="">{t('sample_label')}</option>
      {BUILT_IN_SAMPLES.map((sample) => (
        <option key={sample.id} value={sample.id}>
          {t(sample.labelKey)}
        </option>
      ))}
    </select>
  );
}
