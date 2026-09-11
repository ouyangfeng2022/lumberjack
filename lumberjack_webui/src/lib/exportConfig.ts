import type { SplitOptions, SplitterName, TokenizerName } from '../types/chunk';

const SPLITTER_CLASSES: Record<SplitterName, string> = {
  sibling: 'SiblingSplitter',
  'exact-sibling': 'ExactSiblingSplitter',
  'incremental-sibling': 'SiblingSplitter',
  subtree: 'SubtreeSplitter',
  'exact-subtree': 'ExactSubtreeSplitter',
  'incremental-subtree': 'SubtreeSplitter',
  section: 'SectionSplitter',
  'exact-section': 'ExactSectionSplitter',
  'incremental-section': 'SectionSplitter',
  record: 'RecordSplitter',
};

const TOKENIZER_CLASSES: Record<TokenizerName, string> = {
  approx: 'ApproxByteTokenizer',
  tiktoken: 'TiktokenTokenizer',
  transformers: 'TransformersTokenizer',
};

function formatBool(value: boolean): string {
  return value ? 'True' : 'False';
}

export function buildPythonSnippet(options: SplitOptions): string {
  const splitterClass = SPLITTER_CLASSES[options.splitter];
  const tokenizerClass = TOKENIZER_CLASSES[options.tokenizer];
  const blockComment = options.block_configs
    ? [
        '',
        '# Block handling (see lumberjack.block for the typed configuration):',
        ...Object.entries(options.block_configs).map(
          ([kind, cfg]) => `#   ${kind}: ${JSON.stringify(cfg)}`,
        ),
      ].join('\n')
    : '';

  return `from lumberjack import Document, Lumberjack
from lumberjack.splitter import ${splitterClass}
from lumberjack.tokenizer import ${tokenizerClass}

splitter = ${splitterClass}(
    ${tokenizerClass}(),
    max_tokens=${options.max_tokens},
    ideal_max_tokens_ratio=${options.ideal_max_tokens_ratio},
    merge_below_ratio=${options.merge_below_ratio},
    skip_empty_sections=${formatBool(options.skip_empty_sections)},
    heading_sensitive=${formatBool(options.heading_sensitive)},
)

result = Lumberjack(splitter=splitter, max_tokens=${options.max_tokens}).saw(
    Document(source="document.md", format="markdown")
)
for chunk in result.chunks:
    print(chunk.chunk_id, chunk.token_count)${blockComment}`;
}

export function buildCliSnippet(options: SplitOptions): string {
  const flags = [
    '--input-format markdown',
    `--splitter ${options.splitter}`,
    `--tokenizer ${options.tokenizer}`,
    `--max-tokens ${options.max_tokens}`,
    `--ideal-max-tokens-ratio ${options.ideal_max_tokens_ratio}`,
    `--merge-below-ratio ${options.merge_below_ratio}`,
  ];
  if (!options.skip_empty_sections) flags.push('--no-skip-empty-sections');
  if (!options.heading_sensitive) flags.push('--no-heading-sensitive');

  const blockFlags: string[] = [];
  if (options.block_configs) {
    for (const [kind, cfg] of Object.entries(options.block_configs)) {
      const settings: string[] = [];
      if (cfg.isolated) settings.push('isolated=true');
      if (cfg.split === false) settings.push('split=false');
      if (cfg.repeat_header === false) settings.push('repeat-header=false');
      if (settings.length > 0) blockFlags.push(`--block ${kind}:${settings.join(',')}`);
    }
  }

  return ['lumber document.md', ...flags, ...blockFlags].join(' \\\n    ');
}

export function splitterClassName(name: SplitterName): string {
  return SPLITTER_CLASSES[name];
}
