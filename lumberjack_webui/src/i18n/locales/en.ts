const en = {
  // App
  app_title: 'Lumberjack',
  app_subtitle: 'Markdown document splitter',
  tab_split: 'Split',
  tab_pipeline: 'Pipeline',
  btn_split: 'Split Document',
  btn_pipeline: 'Run Pipeline',
  btn_splitting: 'Splitting...',
  btn_running: 'Running...',
  html_title: 'Lumberjack - Markdown Splitter',

  // Markdown Input
  md_label: 'Markdown Input',
  md_placeholder: 'Paste your Markdown here...',
  md_upload: 'Upload .md file',
  md_clear: 'Clear',

  // Split Options
  opts_label: 'Split Options',
  opts_max_tokens: 'Max Tokens',
  opts_retain_headings: 'Retain Headings',
  opts_show_advanced: '+ Show Advanced Options',
  opts_hide_advanced: '- Hide Advanced Options',
  opts_min_tokens: 'Min Tokens',
  opts_overlap_tokens: 'Overlap Tokens',
  opts_merge_small: 'Merge Small Chunks',
  opts_tokenizer: 'Tokenizer',
  opts_tokenizer_simple: 'Simple',
  opts_tokenizer_tiktoken: 'Tiktoken',
  opts_split_oversized: 'Split Oversized Blocks',
  opts_block_paragraph: 'paragraph',
  opts_block_blockquote: 'blockquote',
  opts_block_list: 'list',
  opts_block_table: 'table',
  opts_block_code_block: 'code_block',
  opts_block_code_fence: 'code_fence',
  opts_block_html_block: 'html_block',

  // Chunk Result
  chunk_tokens: '{{count}} tokens',
  chunk_lines: 'Lines {{from}}–{{to}}',
  chunk_show_full: 'Show full text',
  chunk_show_body: 'Show body only',

  // Chunk List
  chunks_count: '{{count}} chunk',
  chunks_count_plural: '{{count}} chunks',
  chunks_total_tokens: '{{count}} total tokens',

  // Pipeline View
  step_raw_text: 'Raw Text',
  step_tokens: 'Tokens',
  step_ast: 'AST',
  step_splitting: 'Splitting',
  step_chunks: 'Chunks',
  nav_previous: 'Previous',
  nav_next: 'Next',

  // Step Raw Text
  stats_characters: 'Characters',
  stats_lines: 'Lines',
  stats_words: 'Words',

  // Step Tokens
  tokens_produced_suffix: 'tokens produced by markdown-it parser',
  tok_col_index: '#',
  tok_col_type: 'Type',
  tok_col_tag: 'Tag',
  tok_col_nesting: 'Nesting',
  tok_col_content: 'Content',
  tok_col_lines: 'Lines',

  // Step AST
  ast_blocks: '{{count}} blocks',
  ast_children: '{{count}} children',

  // Step Split
  split_budget: 'Budget',
  split_tokens: 'tokens',
  split_overlap: 'Overlap',
  split_entries: 'Entries',
  split_draft_chunks: 'Draft Chunks',
  split_over_budget: 'over budget',
  split_entry_label: 'Entry {{index}}',
  split_chunk_label: 'Chunk {{index}}',

  // Step Chunks
  step_chunks_label: 'Chunks',
  step_total_tokens: 'Total Tokens',
  step_document: 'Document',
};

export default en;
