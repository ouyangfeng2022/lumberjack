import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import type { SplitOptions } from '../types/chunk';
import { buildCliSnippet, buildPythonSnippet } from '../lib/exportConfig';
import styles from './ConfigExport.module.css';

interface Props {
  options: SplitOptions;
}

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement('textarea');
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <button className={styles.copyBtn} onClick={copy}>
      {copied ? t('export_copied') : t('export_copy')}
    </button>
  );
}

export default function ConfigExport({ options }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<'python' | 'cli'>('python');

  const snippet = tab === 'python' ? buildPythonSnippet(options) : buildCliSnippet(options);

  return (
    <div className={styles.container}>
      <button className={styles.toggle} onClick={() => setOpen(!open)}>
        {open ? t('export_hide') : t('export_title')}
      </button>
      {open && (
        <div className={styles.body}>
          <div className={styles.tabs}>
            <button
              className={`${styles.tab} ${tab === 'python' ? styles.tabActive : ''}`}
              onClick={() => setTab('python')}
            >
              {t('export_python')}
            </button>
            <button
              className={`${styles.tab} ${tab === 'cli' ? styles.tabActive : ''}`}
              onClick={() => setTab('cli')}
            >
              {t('export_cli')}
            </button>
            <CopyButton text={snippet} />
          </div>
          <pre className={styles.snippet}>{snippet}</pre>
        </div>
      )}
    </div>
  );
}
