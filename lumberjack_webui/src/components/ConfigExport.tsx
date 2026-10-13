import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { SplitOptions } from "../types/chunk";
import { inputFilename, type DocumentInput } from "../lib/formats";
import {
  buildCliSnippet,
  buildCurlSnippet,
  buildPythonSnippet,
} from "../lib/exportConfig";
import { triggerDownload } from "../lib/download";
import styles from "../App.module.css";

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState("");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setStatus(t("export_copied"));
    } catch {
      setStatus(t("ws_copy_failed"));
    }
  };
  return (
    <span className={styles.copyAction}>
      <button onClick={() => void copy()}>{label ?? t("export_copy")}</button>
      <span role="status">{status}</span>
    </span>
  );
}
export default function ConfigExport({
  options,
  input,
}: {
  options: SplitOptions;
  input: DocumentInput;
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState("CLI");
  const snippets: Record<string, string> = {
    CLI: buildCliSnippet(options, input),
    cURL: buildCurlSnippet(options, input, window.location.origin),
    Python: buildPythonSnippet(options, input),
  };
  return (
    <section className={styles.codeCard} aria-label={t("ws_export")}>
      <div className={styles.toolbar}>
        <div className={styles.tabs} role="tablist">
          {Object.keys(snippets).map((name) => (
            <button
              key={name}
              role="tab"
              aria-selected={tab === name}
              onClick={() => setTab(name)}
            >
              {name}
            </button>
          ))}
        </div>
        <CopyButton
          key={snippets[tab]}
          text={snippets[tab]}
          label={t("ws_copy_code")}
        />
      </div>
      {!input.file && tab === "CLI" && (
        <div className={styles.notice}>
          {t("ws_cli_input")}{" "}
          <button
            onClick={() =>
              triggerDownload(
                new Blob([input.text], { type: "text/plain" }),
                inputFilename(input),
              )
            }
          >
            {t("ws_download_input")}
          </button>
        </div>
      )}
      <pre role="tabpanel" tabIndex={0}>
        {snippets[tab]}
      </pre>
    </section>
  );
}
