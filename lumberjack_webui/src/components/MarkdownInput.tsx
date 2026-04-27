import { useRef } from 'react';
import styles from './MarkdownInput.module.css';

interface Props {
  text: string;
  file: File | null;
  onTextChange: (text: string) => void;
  onFileChange: (file: File | null) => void;
}

export default function MarkdownInput({ text, file, onTextChange, onFileChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

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
      <label className={styles.label}>Markdown Input</label>
      <textarea
        className={styles.textarea}
        value={file ? '' : text}
        disabled={!!file}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder="Paste your Markdown here..."
      />
      <div className={styles.fileRow}>
        <label className={styles.fileLabel}>
          {file ? file.name : 'Upload .md file'}
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
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
