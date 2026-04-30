import { useTranslation } from 'react-i18next';
import styles from './LanguageSwitcher.module.css';

const LANGUAGES = [
  { code: 'en', label: 'EN' },
  { code: 'zh', label: '中文' },
];

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();

  return (
    <div className={styles.switcher}>
      {LANGUAGES.map((lang, i) => (
        <span key={lang.code}>
          {i > 0 && <span className={styles.separator}>|</span>}
          <button
            className={`${styles.langBtn} ${i18n.language.startsWith(lang.code) ? styles.active : ''}`}
            onClick={() => i18n.changeLanguage(lang.code)}
          >
            {lang.label}
          </button>
        </span>
      ))}
    </div>
  );
}
