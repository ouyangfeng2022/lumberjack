import { useRef, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './MarkdownInput.module.css';

interface Props {
  text: string;
  file: File | null;
  onTextChange: (text: string) => void;
  onFileChange: (file: File | null) => void;
}

export default function MarkdownInput({ text, file, onTextChange, onFileChange }: Props) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileContent, setFileContent] = useState('');

  useEffect(() => {
    if (file) {
      file.text().then(setFileContent);
    } else {
      setFileContent('');
    }
  }, [file]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    onFileChange(selected);
  };

  const clearFile = () => {
    onFileChange(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className={styles.container}>
      <textarea
        className={styles.textarea}
        value={file ? fileContent : text}
        readOnly={!!file}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder={t('md_placeholder')}
      />
      <div className={styles.fileRow}>
        <span className={styles.fileMeta}>
          {file ? t('md_file_ready') : t('md_text_mode')}
        </span>
        <label className={styles.fileLabel}>
          {file ? file.name : t('md_upload')}
          <input
            ref={inputRef}
            type="file"
            accept=".md,.markdown,.txt"
            onChange={handleFileSelect}
            className={styles.fileInput}
          />
        </label>
        {file && (
          <button className={styles.clearBtn} onClick={clearFile}>
            {t('md_clear')}
          </button>
        )}
      </div>
    </div>
  );
}
