const en = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown document splitter',
  btn_split: 'Start Split',
  btn_splitting: 'Splitting...',
  html_title: 'Lumberjack - Markdown Splitter',
  panel_results_title: 'Split Results',
  result_budget_use: 'Largest chunk budget use',
  empty_split_title: 'Ready to split',
  empty_split_body: 'Paste Markdown or upload a file, adjust the token budget, then run the splitter to preview chunked output.',

  // Markdown Input
  md_label: 'Markdown Input',
  md_placeholder: 'Paste your Markdown here...',
  md_upload: 'Upload .md file',
  md_clear: 'Clear',
  md_text_mode: 'Editing pasted Markdown',
  md_file_ready: 'File upload will be submitted',

  // Split Options
  opts_label: 'Split Settings',
  opts_basic_section: 'Basic',
  opts_strategy_section: 'Strategy',
  opts_max_tokens: 'Max tokens',
  opts_ideal_max_tokens_ratio: 'Ideal max ratio',
  opts_show_advanced: 'Show advanced options',
  opts_hide_advanced: 'Hide advanced options',
  opts_merge_below_tokens: 'Merge below tokens',
  opts_merge_small: 'Merge small chunks',
  opts_skip_empty_sections: 'Skip empty sections',
  opts_disable_lheading: 'Disable Setext headings',
  opts_splitter: 'Splitter',
  opts_splitter_recursive: 'Recursive',
  opts_splitter_section: 'Section',
  opts_recursive_split: 'Recursively split oversized sections',
  opts_tokenizer: 'Tokenizer',
  opts_tokenizer_simple: 'Simple',
  opts_tokenizer_tiktoken: 'Tiktoken',
  opts_block_handling: 'Block handling',
  opts_isolated: 'Isolated',
  opts_isolated_desc: 'Prevent block from merging with adjacent content',
  opts_nosplit: 'No split',
  opts_nosplit_desc: 'Keep block intact even if it exceeds token budget',
  opts_block_paragraph: 'Paragraph',
  opts_block_blockquote: 'Blockquote',
  opts_block_list: 'List',
  opts_block_table: 'Table',
  opts_block_html_table: 'HTML Table',
  opts_block_code_block: 'Code block',
  opts_block_code_fence: 'Code fence',
  opts_block_html_block: 'HTML block',
  opts_block_front_matter: 'Front matter',

  // Chunk Result
  chunk_tokens: '{{count}} tokens',
  chunk_lines: 'Lines {{from}}-{{to}}',

  // Chunk List
  chunks_count: '{{count}} chunk',
  chunks_count_plural: '{{count}} chunks',
  chunks_total_tokens: '{{count}} total tokens',

  // Stats
  stats_characters: 'Characters',
  stats_lines: 'Lines',
};

export default en;
