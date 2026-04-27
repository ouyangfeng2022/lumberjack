import { useState } from 'react';
import MarkdownInput from './components/MarkdownInput';
import SplitOptions from './components/SplitOptions';
import ChunkList from './components/ChunkList';
import { splitMarkdown } from './api/split';
import type { SplitResponse, SplitOptions as Options } from './types/chunk';
import styles from './App.module.css';

const DEFAULT_OPTIONS: Options = {
  max_tokens: 1200,
  min_tokens: 50,
  overlap_tokens: 0,
  retain_headings: true,
  merge_small_chunks: true,
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

export default function App() {
  const [text, setText] = useState(SAMPLE_MD);
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<Options>(DEFAULT_OPTIONS);
  const [result, setResult] = useState<SplitResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const canSplit = !!file || text.trim().length > 0;

  const handleSplit = async () => {
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      const data = await splitMarkdown(text, file, {
        ...options,
        document_title: file?.name ?? options.document_title,
      });
      if ('error' in data) {
        setError((data as { error: string }).error);
      } else {
        setResult(data as SplitResponse);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Lumberjack</h1>
        <p className={styles.subtitle}>Markdown document splitter</p>
      </header>

      <main className={styles.main}>
        <section className={styles.inputSection}>
          <MarkdownInput
            text={text}
            file={file}
            onTextChange={setText}
            onFileChange={setFile}
          />
          <SplitOptions options={options} onChange={setOptions} />
        </section>

        <button
          className={styles.splitBtn}
          disabled={!canSplit || loading}
          onClick={handleSplit}
        >
          {loading ? 'Splitting...' : 'Split Document'}
        </button>

        {error && <div className={styles.error}>{error}</div>}

        {result && <ChunkList result={result} />}
      </main>
    </div>
  );
}
