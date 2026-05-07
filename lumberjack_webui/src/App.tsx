import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import MarkdownInput from './components/MarkdownInput';
import SplitOptions from './components/SplitOptions';
import ChunkList from './components/ChunkList';
import PipelineView from './components/PipelineView';
import LanguageSwitcher from './components/LanguageSwitcher';
import { splitMarkdown } from './api/split';
import { fetchPipeline } from './api/pipeline';
import type { SplitResponse, SplitOptions as Options } from './types/chunk';
import type { PipelineResponse } from './types/pipeline';
import styles from './App.module.css';

const DEFAULT_OPTIONS: Options = {
  max_tokens: 1200,
  merge_below_tokens: 50,
  overlap_tokens: 0,
  retain_headings: true,
  include_common_headings: true,
  merge_small_chunks: true,
  isolate_front_matter: true,
  split_oversized_blocks: 'paragraph,blockquote,html_block',
  tokenizer: 'simple',
  document_title: 'document.md',
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
  apiKey: process.env.API_KEY,
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

type View = 'split' | 'pipeline';

export default function App() {
  const { t, i18n } = useTranslation();
  const [view, setView] = useState<View>('split');
  const [text, setText] = useState(SAMPLE_MD);
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<Options>(DEFAULT_OPTIONS);
  const [result, setResult] = useState<SplitResponse | null>(null);
  const [splitElapsedMs, setSplitElapsedMs] = useState<number | null>(null);
  const [pipelineResult, setPipelineResult] = useState<PipelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    document.documentElement.lang = i18n.language;
    document.title = t('html_title');
  }, [i18n.language, t]);

  const canSubmit = !!file || text.trim().length > 0;
  const inputStats = useMemo(() => {
    const sourceText = file ? '' : text;
    return {
      lines: sourceText ? sourceText.split(/\r\n|\r|\n/).length : 0,
      characters: sourceText.length,
      name: file?.name ?? options.document_title,
      tokens: sourceText.trim() ? sourceText.trim().split(/\s+/).length : 0,
    };
  }, [file, options.document_title, text]);

  const resultStats = useMemo(() => {
    if (!result) return null;
    const largestChunk = result.chunks.reduce(
      (max, chunk) => Math.max(max, chunk.token_count),
      0,
    );
    const budgetUse = Math.min(100, Math.round((largestChunk / options.max_tokens) * 100));

    return {
      budgetUse,
    };
  }, [options.max_tokens, result]);

  const handleSubmit = async () => {
    setError(null);
    if (view === 'split') {
      setResult(null);
      setSplitElapsedMs(null);
    } else {
      setPipelineResult(null);
    }
    setLoading(true);

    try {
      const opts = { ...options, document_title: file?.name ?? options.document_title };
      if (view === 'split') {
        const startedAt = performance.now();
        const data = await splitMarkdown(text, file, opts);
        const elapsedMs = Math.max(0, performance.now() - startedAt);
        if ('error' in data) {
          setError((data as { error: string }).error);
        } else {
          setSplitElapsedMs(elapsedMs);
          setResult(data as SplitResponse);
        }
      } else {
        const data = await fetchPipeline(text, file, opts);
        if ('error' in data) {
          setError((data as { error: string }).error);
        } else {
          setPipelineResult(data as PipelineResponse);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const handleViewChange = (v: View) => {
    setView(v);
    setError(null);
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.logoMark}>L</span>
          <div>
            <h1 className={styles.title}>{t('app_title')}</h1>
            <p className={styles.subtitle}>{t('app_subtitle')}</p>
          </div>
        </div>
        <div className={styles.headerActions}>
          <div className={styles.tabBar} aria-label={t('view_tabs')}>
            <button
              className={`${styles.tab} ${view === 'split' ? styles.tabActive : ''}`}
              onClick={() => handleViewChange('split')}
            >
              {t('tab_split')}
            </button>
            <button
              className={`${styles.tab} ${view === 'pipeline' ? styles.tabActive : ''}`}
              onClick={() => handleViewChange('pipeline')}
            >
              {t('tab_pipeline')}
            </button>
          </div>
          <LanguageSwitcher />
        </div>
      </header>

      <main className={styles.main}>
        <div className={styles.controlsGrid}>
          <section className={`${styles.panel} ${styles.inputPanel}`}>
            <div className={styles.panelHeader}>
              <div>
                <p className={styles.kicker}>{t('panel_input_kicker')}</p>
                <h2 className={styles.panelTitle}>{t('md_label')}</h2>
              </div>
              <div className={styles.inputStats}>
                <span>{t('stats_lines')}: {inputStats.lines}</span>
                <span>{t('stats_characters')}: {inputStats.characters}</span>
              </div>
            </div>
            <MarkdownInput
              text={text}
              file={file}
              onTextChange={setText}
              onFileChange={setFile}
            />
          </section>

          <aside className={`${styles.panel} ${styles.optionsPanel}`}>
            <div className={styles.panelHeader}>
              <div>
                <p className={styles.kicker}>{t('panel_options_kicker')}</p>
                <h2 className={styles.panelTitle}>{t('opts_label')}</h2>
              </div>
            </div>
            <SplitOptions options={options} onChange={setOptions} />
            <button
              className={styles.splitBtn}
              disabled={!canSubmit || loading}
              onClick={handleSubmit}
            >
              {loading
                ? view === 'split'
                  ? t('btn_splitting')
                  : t('btn_running')
                : view === 'split'
                  ? t('btn_split')
                  : t('btn_pipeline')}
            </button>
            <div className={styles.optionHint}>
              <span>{inputStats.name}</span>
              <span>{inputStats.tokens.toLocaleString()} {t('split_tokens')}</span>
            </div>
          </aside>
        </div>

        <section className={`${styles.panel} ${styles.resultsPanel}`}>
          <div className={styles.panelHeader}>
            <div>
              <p className={styles.kicker}>{t('panel_results_kicker')}</p>
              <h2 className={styles.panelTitle}>{t('panel_results_title')}</h2>
            </div>
            {resultStats && view === 'split' && (
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

          {error && <div className={styles.error}>{error}</div>}

          {view === 'split' && result && (
            <ChunkList result={result} elapsedMs={splitElapsedMs} />
          )}
          {view === 'pipeline' && pipelineResult && <PipelineView data={pipelineResult} />}

          {view === 'split' && !result && !error && (
            <div className={styles.emptyState}>
              <span className={styles.emptyIndex}>01</span>
              <h3>{t('empty_split_title')}</h3>
              <p>{t('empty_split_body')}</p>
            </div>
          )}
          {view === 'pipeline' && !pipelineResult && !error && (
            <div className={styles.emptyState}>
              <span className={styles.emptyIndex}>05</span>
              <h3>{t('empty_pipeline_title')}</h3>
              <p>{t('empty_pipeline_body')}</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
