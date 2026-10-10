import { useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  ACCEPTED_FILES,
  FORMATS,
  TEXT_FORMATS,
  isBinaryFormat,
  resolvedFormat,
  type DocumentInput,
  type FileFormat,
} from "../lib/formats";
import styles from "../App.module.css";

export default function MarkdownInput({
  input,
  onChange,
}: {
  input: DocumentInput;
  onChange: (input: DocumentInput) => void;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLInputElement>(null);
  const binary = !!input.file && isBinaryFormat(resolvedFormat(input));
  const updateFile = (file: File | null) => {
    if (!file) {
      onChange({ text: "", file: null, format: "markdown" });
      return;
    }
    const next: DocumentInput = { text: "", file, format: "auto" };
    onChange(next);
  };
  return (
    <div className={styles.editor}>
      <div className={styles.toolbar}>
        <label className={styles.formatField}>
          {t("ws_format")}
          <select
            aria-label={t("ws_format")}
            value={input.format}
            onChange={(event) =>
              onChange({ ...input, format: event.target.value as FileFormat })
            }
          >
            {input.file && <option value="auto">{t("ws_auto")}</option>}
            {(input.file ? FORMATS : TEXT_FORMATS).map((format) => (
              <option key={format} value={format}>
                {format}
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => ref.current?.click()}>{t("ws_upload")}</button>
        <input
          ref={ref}
          type="file"
          accept={ACCEPTED_FILES}
          hidden
          onChange={(event) => {
            void updateFile(event.target.files?.[0] ?? null);
            event.target.value = "";
          }}
        />
        {input.file && (
          <button onClick={() => void updateFile(null)}>{t("md_clear")}</button>
        )}
      </div>
      {input.file && (
        <div className={styles.fileInfo}>
          <strong>{input.file.name}</strong>
          <span>
            {(input.file.size / 1024).toFixed(1)} KB · {resolvedFormat(input)}
          </span>
        </div>
      )}
      {binary ? (
        <div className={styles.empty}>
          <IconDocument />
          <h3>{t("ws_binary")}</h3>
          <p>{t("ws_binary_hint")}</p>
        </div>
      ) : (
        <textarea
          aria-label={t("ws_input")}
          value={input.text}
          readOnly={!!input.file}
          spellCheck={false}
          placeholder={t("ws_input_hint")}
          onChange={(event) => onChange({ ...input, text: event.target.value })}
        />
      )}
    </div>
  );
}
function IconDocument() {
  return (
    <span aria-hidden="true" style={{ fontSize: 40 }}>
      ▤
    </span>
  );
}
