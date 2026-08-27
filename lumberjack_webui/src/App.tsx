import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import MarkdownInput from './components/MarkdownInput';
import SplitOptions from './components/SplitOptions';
import ChunkList from './components/ChunkList';
import LanguageSwitcher from './components/LanguageSwitcher';
import SamplePicker from './components/SamplePicker';
import CompareControls from './components/CompareControls';
import CompareResults from './components/CompareResults';
import ConfigExport from './components/ConfigExport';
import BoundaryMap from './components/BoundaryMap';
import { splitMarkdown } from './api/split';
import { downloadChunksJsonl, downloadResultJson } from './lib/download';
import { resolveCompareSplitters, type ComparePreset } from './lib/compare';
import type {
  CompareColumn,
  SplitResponse,
  SplitOptions as Options,
  SplitterName,
} from './types/chunk';
import logo from './assets/lumberjack.png';
import styles from './App.module.css';

const DEFAULT_OPTIONS: Options = {
  max_tokens: 1200,
  ideal_max_tokens_ratio: 0.8,
  merge_below_ratio: 0.125,
  skip_empty_sections: true,
  heading_sensitive: true,
  block_configs: null,
  tokenizer: 'approx',
  splitter: 'section',
};

const SAMPLE_MD = `# Getting Started

This guide walks you through the basics of using our platform.

## Installation

First, install the required packages using your preferred package manager.

\`\`\`bash
npm install my-package
\`\`\`

## Configuration

Create a config file in your project root:

\`\`\`json
{
  "theme": "dark",
  "language": "en"
}
\`\`\`

### Advanced Settings

For production deployments, you should also set the following environment variables:

- \`API_KEY\`: Your API key
- \`BASE_URL\`: The base URL of your instance
- \`LOG_LEVEL\`: Logging verbosity (debug, info, warn, error)

## Usage

Import the library and initialize it with your configuration:

\`\`\`javascript
import { createClient } from 'my-package';

const client = createClient({
  apiKey: 'your-api-key',
});
\`\`\`

### Making Requests

Once initialized, you can make requests to the API:

\`\`\`javascript
const result = await client.query({
  text: "Hello, world!",
  maxTokens: 100,
});
\`\`\`

## Troubleshooting

If you encounter issues, check the following:

1. Verify your API key is valid
2. Ensure your network allows outbound HTTPS connections
3. Check the service status page for any ongoing incidents

For more help, consult the FAQ or open a GitHub issue.
`;

export default function App() {
  const { t, i18n } = useTranslation();
  const [text, setText] = useState(SAMPLE_MD);
  const [file, setFile] = useState<File | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [options, setOptions] = useState<Options>(DEFAULT_OPTIONS);
  const [result, setResult] = useState<SplitResponse | null>(null);
  const [splitElapsedMs, setSplitElapsedMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [compareEnabled, setCompareEnabled] = useState(false);
  const [comparePreset, setComparePreset] = useState<ComparePreset>('topology');
  const [customSplitters, setCustomSplitters] = useState<SplitterName[]>([
    'incremental-section',
    'incremental-sibling',
  ]);
  const [compareColumns, setCompareColumns] = useState<CompareColumn[]>([]);
  const [showBoundary, setShowBoundary] = useState(false);

  useEffect(() => {
    document.documentElement.lang = i18n.language;
    document.title = t('html_title');
  }, [i18n.language, t]);

  const canSubmit = !!file || text.trim().length > 0;
  const sourceText = file ? fileContent : text;

  const inputStats = useMemo(() => {
    return {
      lines: sourceText ? sourceText.split(/\r\n|\r|\n/).length : 0,
      characters: sourceText.length,
      name: file?.name ?? 'document.md',
    };
  }, [file, sourceText]);

  const resultStats = useMemo(() => {
    if (!result) return null;
    const largestChunk = result.chunks.reduce(
      (max, chunk) =>
        Math.max(
          max,
          options.heading_sensitive ? chunk.token_count : chunk.body_token_count,
        ),
      0,
    );
    const budgetUse = Math.min(100, Math.round((largestChunk / options.max_tokens) * 100));

    return {
      budgetUse,
    };
  }, [options.heading_sensitive, options.max_tokens, result]);

  const loadSample = (sampleText: string) => {
    setFile(null);
    setFileContent('');
    setText(sampleText);
  };

  const handleSubmit = async () => {
    setError(null);
    setResult(null);
    setSplitElapsedMs(null);
    setCompareColumns([]);
    setLoading(true);

    if (compareEnabled) {
      const splitters = resolveCompareSplitters(comparePreset, customSplitters);
      const columns: CompareColumn[] = splitters.map((splitter) => ({
        splitter,
        options: { ...options, splitter },
        result: null,
        error: null,
        elapsedMs: null,
      }));
      // Sequential on purpose: keeps concurrent splits bounded and stays
      // friendly to the demo server's rate limit.
      for (let i = 0; i < columns.length; i += 1) {
        const column = columns[i];
        const startedAt = performance.now();
        try {
          const data = await splitMarkdown(text, file, {
            ...options,
            splitter: column.splitter,
          });
          column.elapsedMs = Math.max(0, performance.now() - startedAt);
          if ('error' in data) {
            column.error = (data as { error: string }).error;
          } else {
            column.result = data as SplitResponse;
          }
        } catch (err) {
          column.error = err instanceof Error ? err.message : 'Unknown error';
        }
        setCompareColumns([...columns]);
      }
      setLoading(false);
      return;
    }

    try {
      const startedAt = performance.now();
      const data = await splitMarkdown(text, file, options);
      const elapsedMs = Math.max(0, performance.now() - startedAt);
      if ('error' in data) {
        setError((data as { error: string }).error);
      } else {
        setSplitElapsedMs(elapsedMs);
        setResult(data as SplitResponse);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const exportOptions = compareEnabled
    ? { ...options, splitter: resolveCompareSplitters(comparePreset, customSplitters)[0] }
    : options;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <img className={styles.logoMark} src={logo} alt="Lumberjack" />
          <div>
            <h1 className={styles.title}>{t('app_title')}</h1>
            <p className={styles.subtitle}>{t('app_subtitle')}</p>
          </div>
        </div>
        <div className={styles.headerActions}>
          <LanguageSwitcher />
        </div>
      </header>

      <main className={styles.main}>
        <section className={`${styles.panel} ${styles.inputPanel}`}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>{t('md_label')}</h2>
            <div className={styles.inputActions}>
              <div className={styles.inputStats}>
                <span>{t('stats_lines')}: {inputStats.lines}</span>
                <span>{t('stats_characters')}: {inputStats.characters}</span>
              </div>
              <SamplePicker onLoad={loadSample} />
            </div>
          </div>
          <MarkdownInput
            text={text}
            file={file}
            onTextChange={setText}
            onFileChange={setFile}
            onFileContentChange={setFileContent}
          />
        </section>

        <aside className={`${styles.panel} ${styles.optionsPanel}`}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>{t('opts_label')}</h2>
          </div>
          <div className={styles.optionsScroll}>
            <div className={styles.compareSlot}>
              <CompareControls
                enabled={compareEnabled}
                preset={comparePreset}
                customSplitters={customSplitters}
                onToggle={setCompareEnabled}
                onPresetChange={setComparePreset}
                onCustomChange={setCustomSplitters}
              />
            </div>
            <SplitOptions options={options} onChange={setOptions} />
          </div>
          <div className={styles.optionsFooter}>
            <button
              className={styles.splitBtn}
              disabled={!canSubmit || loading}
              onClick={handleSubmit}
            >
              {loading ? t('btn_splitting') : t('btn_split')}
            </button>
            <div className={styles.optionHint}>
              <span>{inputStats.name}</span>
            </div>
            <ConfigExport options={exportOptions} />
          </div>
        </aside>

        <section className={`${styles.panel} ${styles.resultsPanel}`}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>
              {compareEnabled && compareColumns.length > 0
                ? t('panel_compare_title')
                : t('panel_results_title')}
            </h2>
            <div className={styles.resultsActions}>
              {result && (
                <>
                  <button
                    className={styles.miniBtn}
                    onClick={() => setShowBoundary(!showBoundary)}
                  >
                    {showBoundary ? t('boundary_hide') : t('boundary_show')}
                  </button>
                  <button
                    className={styles.miniBtn}
                    onClick={() => downloadResultJson(result)}
                  >
                    {t('download_json')}
                  </button>
                  <button
                    className={styles.miniBtn}
                    onClick={() => downloadChunksJsonl(result)}
                  >
                    {t('download_jsonl')}
                  </button>
                </>
              )}
              {resultStats && (
                <div className={styles.resultMeter} aria-label={t('result_budget_use')}>
                  <span>{resultStats.budgetUse}%</span>
                  <div className={styles.meterTrack}>
                    <div
                      className={styles.meterFill}
                      style={{ width: `${resultStats.budgetUse}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {error && <div className={styles.error}>{error}</div>}

          {compareColumns.length > 0 && (
            <CompareResults columns={compareColumns} sourceText={sourceText} />
          )}

          {!compareEnabled && result && (
            <>
              {showBoundary && (
                <div className={styles.boundarySlot}>
                  <BoundaryMap sourceText={sourceText} chunks={result.chunks} />
                </div>
              )}
              <ChunkList result={result} elapsedMs={splitElapsedMs} />
            </>
          )}

          {!result && !error && compareColumns.length === 0 && (
            <div className={styles.emptyState}>
              <h3>{t('empty_split_title')}</h3>
              <p>{t('empty_split_body')}</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
