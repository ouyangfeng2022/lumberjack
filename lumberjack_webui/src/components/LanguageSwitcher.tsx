import { useTranslation } from 'react-i18next';
import styles from './LanguageSwitcher.module.css';

const LANGUAGES = [
  { code: 'zh', label: '中文' },
  { code: 'en', label: 'EN' },
];

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();

  return (
    <div className={styles.switcher}>
      {LANGUAGES.map((lang) => (
        <button
          key={lang.code}
          className={`${styles.langBtn} ${i18n.language.startsWith(lang.code) ? styles.active : ''}`}
          onClick={() => i18n.changeLanguage(lang.code)}
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}
